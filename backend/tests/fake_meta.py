"""Deterministic offline stand-in for MetaClient. No network, ever.

Default world: one "face" privacy box on frame f01, one stable "window" box on
every image, no doors/documents/photographs. Wonder alternates living/kitchen.
Staging returns the input with a mild tint (geometry untouched). Spark cites real
ids only. Knobs flip specific failures for the verifier tests.
"""

import hashlib
import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

import meta_client

OBSERVATIONS = {
    "living": ["floor-to-ceiling windows", "stone fireplace", "wide-plank oak floors"],
    "kitchen": ["marble island", "brass fixtures"],
}


class FakeMeta(meta_client._ClientBase):
    def __init__(self, *, bad_claim: bool = False, warp_staging: bool = False,
                 face_survives: bool = False, wrong_number: bool = False,
                 fail_concept: str | None = None, fail_frame: str | None = None,
                 fail_staged_faces: bool = False, furnished_before: bool = False,
                 warp_live: bool = False, warp_live_once: bool = False,
                 fail_live_image: bool = False, warp_room: str | None = None,
                 fix_at_level: int = 1, fail_restage: bool = False):
        super().__init__()
        self.bad_claim = bad_claim
        self.warp_staging = warp_staging
        self.face_survives = face_survives
        self.wrong_number = wrong_number
        self.fail_concept = fail_concept
        self.fail_frame = fail_frame
        self.fail_staged_faces = fail_staged_faces
        self.furnished_before = furnished_before
        self.warp_live = warp_live
        self.warp_live_once = warp_live_once
        self.fail_live_image = fail_live_image
        self.warp_room = warp_room
        self.fix_at_level = fix_at_level
        self.fail_restage = fail_restage
        self.base_url = "fake://meta"
        self.spark_model = "muse-spark-1.3"
        self.wonder_model = "muse-wonder-1.0"
        self.image_model = "muse-image-1.0"
        self.sam_model = "sam-3.1"
    def _size(self, image_path) -> tuple[int, int]:
        with Image.open(image_path) as img:
            return img.size

    def _box(self, size, x1, y1, x2, y2, concept, score=0.9):
        w, h = size
        return {"concept": concept, "score": score,
                "box": [round(x1 * w), round(y1 * h), round(x2 * w), round(y2 * h)]}

    def sam_segment(self, image_path, concept: str, *, trace=None,
                    purpose: str = "sam.privacy", target: dict | None = None) -> list[dict]:
        target = target or {}

        def fn():
            if purpose in ("sam.privacy", "sam.structure") and self.fail_concept == concept \
                    and (self.fail_frame is None or target.get("frame") == self.fail_frame):
                raise meta_client.MetaError(f"boom: {concept} on {target.get('frame')}")
            if purpose == "sam.staged_faces" and self.fail_staged_faces:
                raise meta_client.MetaError("boom: staged faces")
            size = self._size(image_path)
            if purpose == "sam.privacy":
                if concept == "face" and target.get("frame") == "f01":
                    return [self._box(size, 0.60, 0.10, 0.75, 0.30, concept)], "1 face box(es)"
                return [], f"0 {concept} box(es)"
            if purpose in ("sam.staged_faces", "verify.sam.faces"):
                if self.face_survives:
                    return [self._box(size, 0.30, 0.20, 0.70, 0.70, concept)], "1 face box(es)"
                return [], "0 face box(es)"
            if purpose == "live.sam.pieces":
                piece_boxes = {
                    "sofa": (0.08, 0.55, 0.48, 0.88),
                    "table": (0.50, 0.66, 0.72, 0.86),
                    "lamp": (0.74, 0.30, 0.84, 0.62),
                    "rug": (0.05, 0.75, 0.80, 0.98),
                }
                if concept in piece_boxes:
                    return [self._box(size, *piece_boxes[concept], concept)], f"1 {concept} box(es)"
                return [], f"0 {concept} box(es)"
            if purpose == "live.sam.plate":
                if concept == "sofa" and self.furnished_before:
                    return [self._box(size, 0.08, 0.55, 0.48, 0.88, concept)], "1 sofa box(es)"
                return [], f"0 {concept} box(es)"
            if purpose in ("live.sam.faces", "live.sam.focus"):
                return [], f"0 {concept} box(es)"
            # live.sam.structure falls through to the window rule below.
            if concept == "window":
                return [self._box(size, 0.15, 0.20, 0.45, 0.60, concept)], "1 window box(es)"
            return [], f"0 {concept} box(es)"

        return self._invoke(trace, purpose, target or {"concept": concept},
                            self.sam_model, f"{concept}|{purpose}",
                            [Path(image_path).read_bytes()], fn)

    def wonder_classify(self, frames: list[dict], *, trace=None,
                        purpose: str = "wonder.classify", target: dict | None = None) -> dict:
        def fn():
            entries, order = [], []
            for i, frame in enumerate(frames):
                room_type = "living" if i % 2 == 0 else "kitchen"
                room_key = f"{room_type}_1"
                if room_key not in order:
                    order.append(room_key)
                entries.append({
                    "frame": frame["id"],
                    "room_key": room_key,
                    "room_type": room_type,
                    "usable": True,
                    "coverage": 0.8,
                    "observations": OBSERVATIONS[room_type],
                    "condition": "well kept",
                })
            return {"frames": entries, "order": order}, f"{len(entries)} frames classified"

        prompt = "classify:" + ",".join(f["id"] for f in frames)
        blobs = [Path(f["path"]).read_bytes() for f in frames if f.get("path")]
        return self._invoke(trace, purpose, target or {"frames": len(frames)},
                            self.wonder_model, prompt, blobs, fn)

    def image_stage(self, image_path, style_prompt: str, *, trace=None,
                    purpose: str = "image.stage", target: dict | None = None) -> bytes:
        def fn():
            if self.fail_live_image and purpose == "live.image.stage":
                raise meta_client.MetaError("boom: live image stage")
            if self.fail_restage and purpose == "image.restage":
                raise meta_client.MetaError("boom: image restage")
            img = Image.open(image_path).convert("RGB")
            room = (target or {}).get("room")
            if self.warp_staging and room == "room_2":
                img = ImageOps.mirror(img)
            elif (self.warp_live or (self.warp_live_once and "Critical:" not in style_prompt)) \
                    and purpose == "live.image.stage" and (target or {}).get("style") == "coastal":
                img = ImageOps.mirror(img)
            elif self.warp_room is not None and room == self.warp_room and (
                    purpose == "image.stage"
                    or (purpose == "image.restage"
                        and (target or {}).get("level", 0) < self.fix_at_level)):
                img = ImageOps.mirror(img)
            else:
                img = Image.eval(img, lambda p: min(255, int(p * 0.96 + 8)))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=90)
            data = buf.getvalue()
            return data, f"staged image, {len(data) // 1024} KB"

        return self._invoke(trace, purpose, target, self.image_model, style_prompt,
                            [Path(image_path).read_bytes()], fn)

    def spark_copy(self, *, facts: dict, observations: list[dict], trace=None,
                   purpose: str = "spark.copy", target: dict | None = None) -> dict:
        def fn():
            ev = lambda k: f"fact:{k}"
            if facts.get("name"):
                title = {"text": facts["name"], "evidence": [ev("name")]}
            elif facts.get("beds") and facts.get("city"):
                title = {"text": f"{int(facts['beds'])}-bedroom residence in {facts['city']}",
                         "evidence": [ev("beds"), ev("city")]}
            else:
                title = {"text": "Residence", "evidence": [ev("city") if facts.get("city") else "fact:address"]}
            sentences, highlights = [], []
            if facts.get("beds") and facts.get("sqft"):
                sentences.append({
                    "text": f"{int(facts['beds'])} bedrooms across {int(facts['sqft']):,} square feet.",
                    "evidence": [ev("beds"), ev("sqft")],
                })
            if observations:
                sentences.append({
                    "text": f"{observations[0]['text'].capitalize()} anchor the main living space.",
                    "evidence": [observations[0]["id"]],
                })
            if facts.get("beds"):
                highlights.append({"text": f"{int(facts['beds'])} bedrooms", "evidence": [ev("beds")]})
            if len(observations) > 1:
                highlights.append({"text": observations[1]["text"].capitalize(),
                                   "evidence": [observations[1]["id"]]})
            if self.wrong_number:
                sentences.append({"text": "The layout includes 4 bedrooms.", "evidence": [ev("beds")]})
            if self.bad_claim and observations:
                highlights.append({"text": "Private rooftop infinity pool",
                                   "evidence": [observations[0]["id"]]})
            data = {"title": title, "sentences": sentences, "highlights": highlights}
            return data, f"{len(sentences) + len(highlights) + 1} claims drafted"

        prompt = "copy:" + hashlib.sha256(
            (str(sorted(facts.items())) + str([o["id"] for o in observations])).encode()
        ).hexdigest()
        return self._invoke(trace, purpose, target or {}, self.spark_model, prompt, [], fn)

    def wonder_verify_claim(self, claim_text: str, image_paths: list, *, trace=None,
                            purpose: str = "verify.wonder.claim", target: dict | None = None) -> dict:
        def fn():
            if "rooftop" in claim_text.lower():
                return {"verdict": "unsupported", "reason": "No rooftop pool is visible."}, "unsupported"
            return {"verdict": "supported", "reason": "The feature is visible."}, "supported"

        blobs = [Path(p).read_bytes() for p in image_paths]
        return self._invoke(trace, purpose, target or {"claim": claim_text[:80]},
                            self.wonder_model, claim_text, blobs, fn)
