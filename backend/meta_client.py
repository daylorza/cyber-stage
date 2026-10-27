"""The only module that talks to the Meta Model API.

Every product-AI call goes through here, one job per model:
  Spark   -> listing copy, grounded in evidence + supplied facts only
  Wonder  -> multimodal room classification + independent claim verification
  Image   -> geometry-preserving staging (image-to-image)
  SAM 3.1 -> segmentation (privacy boxes to blur, structure boxes for geometry checks)

No other model is used as the product brain, copywriter, stager, or verifier, including
as a fallback. The API key comes from META_API_KEY and is never logged, cached, or
committed. Responses are cached on disk under data_dir/meta_cache keyed by
model + purpose + prompt + image hashes, so reruns do not re-spend credits. A per-job
call budget (VRE_META_MAX_CALLS, default 400) caps spend.
"""

import base64
import hashlib
import io
import json
import os
import re
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from openai import APIError, OpenAI
from PIL import Image

import config

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODELS = {
    "spark": "muse-spark-1.3",
    "wonder": "muse-wonder-1.0",
    "image": "muse-image-1.0",
    "sam": "sam-3.1",
}
MAX_SIDE = 1024
MAX_CLASSIFY_FRAMES = 24

BOX_RE = re.compile(r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=([\d.]+))?\|>")

ROOM_TYPES = "living, kitchen, dining, bedroom, bathroom, office, terrace, hallway, closet, exterior, other"

WONDER_PROMPT = f"""You are classifying frames from a phone walkthrough of a property. Each image is preceded by a label line naming its frame id and timestamp.

For EVERY frame, in order, return one entry:
- "frame": the frame id from its label (e.g. "f03")
- "room_key": a stable snake_case key for the room the frame shows; frames of the same room share a key (e.g. "living_1", "kitchen_1")
- "room_type": one of {ROOM_TYPES}
- "usable": false if the frame is too blurry, dark, or obstructed to show the room
- "coverage": 0..1, how much of the room the frame shows
- "observations": up to 6 short concrete VISIBLE features (e.g. "marble island", "floor-to-ceiling windows")
- "condition": short phrase on visible condition (e.g. "well kept", "dated finishes")

Also return "order": the room keys in walkthrough order.

Rules: describe only what is visible in the frame. No guesses about location, views, finishes, or amenities not in frame. Do not count anything beyond what is visible.
Reply with JSON only: {{"frames": [...], "order": [...]}}"""

SPARK_PROMPT = """You are writing luxury real-estate listing copy. Tone: refined, concise, confident. No exclamation marks, no hype.

You are given FACTS (each with id "fact:<key>") and OBSERVATIONS (each with an id like "o_f03_2", a frame id and a room id). Draft:
- "title": a short listing title
- "sentences": 3-6 description sentences
- "highlights": 3-6 short highlight phrases

Hard rules:
- Every claim (the title, each sentence, each highlight) must cite at least one evidence id that supports it: a "fact:<key>" id or an observation id.
- Numbers may only come from facts. Never invent a number.
- No neighborhood, location, view, or amenity claims unless an evidence id supports them.
- Only claim what the cited evidence supports. If unsure, leave it out.

Reply with JSON only:
{"title": {"text": "...", "evidence": ["fact:city"]},
 "sentences": [{"text": "...", "evidence": ["o_f03_2"]}],
 "highlights": [{"text": "...", "evidence": ["fact:beds"]}]}"""

VERIFY_PROMPT = """You are an independent verifier. Decide whether the claim below is visibly supported by the attached image(s). Be strict: the claim must be directly visible. If the images do not show it, verdict is "unsupported"; if it is ambiguous, "unclear".

Claim: {claim}

Reply with JSON only: {{"verdict": "supported" | "unsupported" | "unclear", "reason": "one short sentence"}}"""


class MetaError(RuntimeError):
    """A safe, short Meta Model API failure. Never contains the API key or raw payloads."""


class MetaNotConfigured(MetaError):
    pass


class MetaBudgetExceeded(MetaError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _trace_begin(trace: list[dict[str, Any]] | None, purpose: str, target: dict | None,
                 model: str) -> dict[str, Any] | None:
    if trace is None:
        return None
    entry = {
        "id": f"tr_{uuid.uuid4().hex[:10]}",
        "model": model,
        "purpose": purpose,
        "target": target or {},
        "at": _now(),
        "ms": 0,
        "ok": False,
        "error": None,
        "cached": False,
        "summary": "",
    }
    trace.append(entry)
    return entry


def _trace_end(entry: dict[str, Any] | None, started: float, *, ok: bool, summary: str = "",
               error: str | None = None, cached: bool = False) -> None:
    if entry is None:
        return
    entry["ms"] = max(0, int((time.monotonic() - started) * 1000))
    entry["ok"] = ok
    entry["summary"] = summary
    entry["error"] = error
    entry["cached"] = cached


def cache_key(model: str, purpose: str, prompt: str, images: list[bytes]) -> str:
    h = hashlib.sha256()
    for part in (model, purpose, prompt):
        h.update(part.encode())
        h.update(b"\0")
    for blob in images:
        h.update(hashlib.sha256(blob).digest())
    return h.hexdigest()


def _encode_payload(result: Any, summary: str) -> dict[str, Any]:
    if isinstance(result, (bytes, bytearray)):
        return {"summary": summary, "kind": "b64", "data": base64.b64encode(bytes(result)).decode()}
    return {"summary": summary, "kind": "json", "data": result}


def _decode_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload["data"]
    result = base64.b64decode(data) if payload["kind"] == "b64" else data
    return {"result": result, "summary": payload["summary"]}


def _load_scaled(path: str | Path, max_side: int = MAX_SIDE) -> tuple[Image.Image, int, int]:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        img.thumbnail((max_side, max_side))
    return img, w, h


def _jpeg_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _data_url(blob: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(blob).decode()


def _parse_json(text: str) -> Any:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def parse_sam_output(output_text: str, orig_w: int, orig_h: int) -> list[dict[str, Any]]:
    """Parse SAM 3.1 special-token output into pixel boxes in the ORIGINAL image's coords."""
    boxes = []
    for m in BOX_RE.finditer(output_text or ""):
        x1, y1, x2, y2 = (int(m.group(i)) for i in range(2, 6))
        w, h = int(m.group(6)), int(m.group(7))
        score = float(m.group(8)) if m.group(8) else None
        if w <= 0 or h <= 0:
            continue
        sx, sy = orig_w / w, orig_h / h
        boxes.append({
            "box": [round(x1 * sx), round(y1 * sy), round(x2 * sx), round(y2 * sy)],
            "score": score,
        })
    return boxes


class _ClientBase:
    """Shared call plumbing for the real client and the offline test fake."""

    def __init__(self) -> None:
        self.max_calls = int(os.environ.get("VRE_META_MAX_CALLS", "400"))
        self._calls = 0
        self._lock = threading.Lock()
        self._mem_cache: dict[str, dict[str, Any]] = {}

    @property
    def configured(self) -> bool:
        return True

    def _require(self) -> None:
        if not self.configured:
            raise MetaNotConfigured("Meta Model API not configured: set META_API_KEY.")

    @property
    def calls(self) -> int:
        return self._calls

    def reset_budget(self) -> None:
        with self._lock:
            self._calls = 0

    def _spend(self) -> None:
        with self._lock:
            if self._calls >= self.max_calls:
                raise MetaBudgetExceeded(
                    f"Meta call budget for this listing is exhausted ({self.max_calls} calls)."
                )
            self._calls += 1

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        payload = self._mem_cache.get(key)
        return _decode_payload(payload) if payload else None

    def _cache_put(self, key: str, payload: dict[str, Any]) -> None:
        self._mem_cache[key] = payload

    def _invoke(self, trace: list | None, purpose: str, target: dict | None, model: str,
                prompt: str, images: list[bytes], fn: Callable[[], tuple[Any, str]]) -> Any:
        entry = _trace_begin(trace, purpose, target, model)
        started = time.monotonic()
        try:
            self._require()
            key = cache_key(model, purpose, prompt, images)
            hit = self._cache_get(key)
            if hit is not None:
                _trace_end(entry, started, ok=True, summary=hit["summary"], cached=True)
                return hit["result"]
            self._spend()
            result, summary = fn()
        except MetaError as exc:
            _trace_end(entry, started, ok=False, error=str(exc))
            raise
        except APIError as exc:
            safe = f"{model} request failed ({exc.__class__.__name__})."
            _trace_end(entry, started, ok=False, error=safe)
            raise MetaError(safe) from exc
        except Exception as exc:
            safe = f"{model} returned an unexpected response ({exc.__class__.__name__})."
            _trace_end(entry, started, ok=False, error=safe)
            raise MetaError(safe) from exc
        self._cache_put(key, _encode_payload(result, summary))
        _trace_end(entry, started, ok=True, summary=summary)
        return result


_DEFAULT = object()


class MetaClient(_ClientBase):
    def __init__(self, api_key: str | None | object = _DEFAULT, base_url: str | None = None) -> None:
        super().__init__()
        self.api_key = os.environ.get("META_API_KEY") if api_key is _DEFAULT else api_key
        self.base_url = base_url or os.environ.get("META_API_BASE_URL", DEFAULT_BASE_URL)
        self.spark_model = os.environ.get("META_SPARK_MODEL", DEFAULT_MODELS["spark"])
        self.wonder_model = os.environ.get("META_WONDER_MODEL", DEFAULT_MODELS["wonder"])
        self.image_model = os.environ.get("META_IMAGE_MODEL", DEFAULT_MODELS["image"])
        self.sam_model = os.environ.get("META_SAM_MODEL", DEFAULT_MODELS["sam"])
        self._openai: OpenAI | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _client(self) -> OpenAI:
        if self._openai is None:
            self._openai = OpenAI(
                api_key=self.api_key, base_url=self.base_url, max_retries=4, timeout=180
            )
        return self._openai

    def _cache_path(self, key: str) -> Path:
        return config.settings.data_dir / "meta_cache" / f"{key}.json"

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        hit = super()._cache_get(key)
        if hit is not None:
            return hit
        path = self._cache_path(key)
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        self._mem_cache[key] = payload
        return _decode_payload(payload)

    def _cache_put(self, key: str, payload: dict[str, Any]) -> None:
        super()._cache_put(key, payload)
        path = self._cache_path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
        except OSError:
            pass

    def _json_call(self, model: str, content: list[dict[str, Any]]) -> Any:
        messages = [{"role": "user", "content": content}]
        last: Exception | None = None
        for attempt in range(2):
            if attempt:
                self._spend()  # the retry is another API request; count it
            response = self._client().responses.create(model=model, input=messages)
            try:
                return _parse_json(response.output_text)
            except (json.JSONDecodeError, ValueError) as exc:
                last = exc
                messages = messages + [{
                    "role": "user",
                    "content": [{"type": "input_text",
                                 "text": f"That reply was not valid JSON ({exc}). Reply with JSON only, no commentary, no code fences."}],
                }]
        raise MetaError(f"{model} did not return valid JSON: {last}")

    def sam_segment(self, image_path: str | Path, concept: str, *, trace: list | None = None,
                    purpose: str = "sam.privacy", target: dict | None = None) -> list[dict[str, Any]]:
        img, orig_w, orig_h = _load_scaled(image_path)
        blob = _jpeg_bytes(img)

        def fn() -> tuple[list[dict[str, Any]], str]:
            response = self._client().responses.create(
                model=self.sam_model,
                input=[{"role": "user", "content": [
                    {"type": "input_text", "text": concept},
                    {"type": "input_image", "image_url": _data_url(blob)},
                ]}],
            )
            boxes = parse_sam_output(response.output_text, orig_w, orig_h)
            for b in boxes:
                b["concept"] = concept
            return boxes, f"{len(boxes)} {concept} box(es)"

        return self._invoke(trace, purpose, target or {"concept": concept},
                            self.sam_model, concept, [blob], fn)

    def wonder_classify(self, frames: list[dict[str, Any]], *, trace: list | None = None,
                        purpose: str = "wonder.classify", target: dict | None = None) -> dict[str, Any]:
        frames = frames[:MAX_CLASSIFY_FRAMES]
        content: list[dict[str, Any]] = [{"type": "input_text", "text": WONDER_PROMPT}]
        prompt_parts = [WONDER_PROMPT]
        blobs: list[bytes] = []
        for frame in frames:
            label = f"Frame {frame['id']}"
            label += f" (t={frame['t']:g}s)" if frame.get("t") is not None else " (photo)"
            content.append({"type": "input_text", "text": label})
            prompt_parts.append(label)
            img, _, _ = _load_scaled(frame["path"])
            blob = _jpeg_bytes(img)
            blobs.append(blob)
            content.append({"type": "input_image", "image_url": _data_url(blob)})

        def fn() -> tuple[dict[str, Any], str]:
            data = self._json_call(self.wonder_model, content)
            return data, f"{len(data.get('frames', []))} frames classified"

        return self._invoke(trace, purpose, target or {"frames": len(frames)},
                            self.wonder_model, "\n".join(prompt_parts), blobs, fn)

    def image_stage(self, image_path: str | Path, style_prompt: str, *, trace: list | None = None,
                    purpose: str = "image.stage", target: dict | None = None) -> bytes:
        img, _, _ = _load_scaled(image_path)
        blob = _png_bytes(img)

        def fn() -> tuple[bytes, str]:
            handle = io.BytesIO(blob)
            handle.name = "frame.png"
            response = self._client().images.edit(
                model=self.image_model,
                image=handle,
                prompt=style_prompt,
                size=f"{img.width}x{img.height}",
                response_format="b64_json",
                n=1,
            )
            data = base64.b64decode(response.data[0].b64_json)
            return data, f"staged image, {len(data) // 1024} KB"

        return self._invoke(trace, purpose, target, self.image_model, style_prompt, [blob], fn)

    def spark_copy(self, *, facts: dict[str, Any], observations: list[dict[str, Any]],
                   trace: list | None = None, purpose: str = "spark.copy",
                   target: dict | None = None) -> dict[str, Any]:
        payload = {
            "facts": [{"id": f"fact:{k}", "value": v} for k, v in facts.items() if v is not None],
            "observations": [
                {"id": o["id"], "frame": o["frame"], "room": o.get("room_id"), "text": o["text"]}
                for o in observations
            ],
        }
        prompt = SPARK_PROMPT + "\n\nFACTS + OBSERVATIONS (JSON):\n" + json.dumps(payload)

        def fn() -> tuple[dict[str, Any], str]:
            data = self._json_call(self.spark_model, [{"type": "input_text", "text": prompt}])
            count = len(data.get("sentences", [])) + len(data.get("highlights", [])) + 1
            return data, f"{count} claims drafted"

        return self._invoke(trace, purpose, target or {}, self.spark_model, prompt, [], fn)

    def wonder_verify_claim(self, claim_text: str, image_paths: list[str | Path], *,
                            trace: list | None = None, purpose: str = "verify.wonder.claim",
                            target: dict | None = None) -> dict[str, Any]:
        prompt = VERIFY_PROMPT.format(claim=claim_text)
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        blobs: list[bytes] = []
        for path in image_paths:
            img, _, _ = _load_scaled(path)
            blob = _jpeg_bytes(img)
            blobs.append(blob)
            content.append({"type": "input_image", "image_url": _data_url(blob)})

        def fn() -> tuple[dict[str, Any], str]:
            data = self._json_call(self.wonder_model, content)
            verdict = str(data.get("verdict", "")).lower()
            if verdict not in ("supported", "unsupported", "unclear"):
                verdict = "unclear"
            return {"verdict": verdict, "reason": str(data.get("reason", ""))[:300]}, verdict

        return self._invoke(trace, purpose, target or {"claim": claim_text[:80]},
                            self.wonder_model, prompt, blobs, fn)


_client: _ClientBase | None = None


def get_client() -> _ClientBase:
    global _client
    if _client is None:
        _client = MetaClient()
    return _client


def set_client(client: _ClientBase | None) -> None:
    global _client
    _client = client


def meta_status(client: _ClientBase | None = None) -> dict[str, Any]:
    c = client or get_client()
    return {
        "configured": c.configured,
        "base_url": getattr(c, "base_url", None),
        "models": {
            "spark": getattr(c, "spark_model", DEFAULT_MODELS["spark"]),
            "wonder": getattr(c, "wonder_model", DEFAULT_MODELS["wonder"]),
            "image": getattr(c, "image_model", DEFAULT_MODELS["image"]),
            "sam": getattr(c, "sam_model", DEFAULT_MODELS["sam"]),
        },
    }
