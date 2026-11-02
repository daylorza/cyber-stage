"""Stage 2 "Live-In-It": pre-processing job for the second-act experience.

Any published listing with a main living space can be prepared (not only the Miami hero).
One gated job prepares everything the viewer needs for the rooms a buyer lives in (the main
living room first, then kitchen/bedrooms/...; bathrooms, laundry and other utility rooms are
walked past on the video, never staged): an empty plate per room, every style preset staged
per room, segmented furniture pieces, each generated image ALIGNED to the filmed frame with a
clean furniture mask (cascade.py), window/size metadata, and the live-in moments (coffee / sit /
view). It only ever writes listing["live"] — Stage 1 data (rooms, copy, comps, checklist,
verification, trace, published) is untouched.

All generated images go through the same safety path as Stage 1 staging:
write to the non-served staged_raw dir, SAM face check, blur, then publish
under media_dir. Meta calls trace into live["trace"], never listing["trace"].
"""

import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image

import cascade
import config
import db
import listings
import meta_client
from pipeline import privacy, stage
from pipeline.classify import MAIN_TYPES, is_utility
from verify import checks

log = logging.getLogger("vre.live")

# Seeded home-page residences were removed: no seed stands in on the home page,
# so every Live-In-It job is prepared without a residence link.
LIVE_RESIDENCES: set[str] = set()
NO_MAIN_ROOM = "No main living space found in this video, so there is no room to walk into."
FURNITURE_CONCEPTS = ("sofa", "chair", "table", "bed", "lamp", "rug", "plant")
PLATE_CONCEPTS = ("sofa", "chair", "table", "bed")
MOMENT_LABELS = {"coffee": "Make coffee", "sit": "Sit down", "view": "Look out at the view"}
EMPTY_PROMPT = (
    "Remove every piece of furniture, rug, lamp, plant, artwork and decor so the room is "
    "completely empty and unfurnished. " + stage.GEOMETRY_RULES
)
RETRY_RULES = (
    " Critical: keep the camera framing identical to the source image, and keep every window and "
    "door exactly as in the source: same count, same position, same size, fully visible. Do not "
    "cover windows or doors with new curtains, furniture or artwork."
)
COFFEE_PROMPT = (
    "Add one freshly poured cup of coffee on a saucer, with a thin wisp of steam, resting "
    "on the {surface} nearest the camera. Change nothing else. " + stage.GEOMETRY_RULES
)

PLATE_MIN_AREA = 0.01      # a plate concept >= 1% of the image means the room is furnished
PIECE_MIN_AREA = 0.004     # drop detections under 0.4% of the image
PIECE_MAX_AREA = 0.55      # and over 55%
PIECE_MAX_COUNT = 14
PIECE_DEDUPE_IOU = 0.6
COFFEE_FALLBACK_FOCUS = [0.3, 0.5, 0.7, 0.8]
STRUCTURE_CONCEPTS = ("window", "door")
SAM_WORKERS = 4


# ---------- small geometry/box helpers ----------

def _iou(a: list[float], b: list[float]) -> float:
    inter = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    if inter <= 0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _norm(box: list[float], size: tuple[int, int]) -> list[float]:
    w, h = size
    return [round(box[0] / w, 4), round(box[1] / h, 4), round(box[2] / w, 4), round(box[3] / h, 4)]


def _narea(box: list[float]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size


def _geometry_check(src: Path, dst: Path, align: dict[str, float] | None = None, min_corr: float | None = None) -> dict[str, Any]:
    """Code check: same aspect ratio and same edge structure as the source frame, with the
    verifier's framing correction (<= 5% stretch/shift, stated). Default threshold 0.25;
    concept styles pass an explicit loosened threshold, recorded in the reason."""
    return checks.geometry(src, dst, align, min_corr=min_corr if min_corr is not None else checks.GEOMETRY_MIN_CORR)


def _save_checked(data: bytes, pre_path: Path, dest_path: Path, meta, trace: list,
                  target: dict[str, Any]) -> None:
    """Save a generated image under media_dir only after the face check clears it.

    The image is first written to the non-served staged_raw dir; the SAM face
    check runs there and anything found is blurred before the media_dir copy.
    A MetaError from the face check propagates: nothing reaches media_dir.
    """
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.save(pre_path, "JPEG", quality=90)
    faces = meta.sam_segment(pre_path, "face", trace=trace, purpose="live.sam.faces", target=target)
    if faces:
        privacy.blur_regions(img, faces)
    img.save(dest_path, "JPEG", quality=90)


# ---------- per-room preparation ----------

def _prepare_plate(room: dict[str, Any], before_path: Path, meta, trace: list,
                   raw_dir: Path, live_dir: Path, lid: str) -> dict[str, Any]:
    """Empty plate for the cascade. If the frame already shows furniture, an
    emptied render is generated and geometry-checked; otherwise the before
    image is the plate. Any failure falls back to the before image."""
    plate = {"plate": None, "plate_source": "before", "plate_check": None}
    w, h = _size(before_path)
    image_area = w * h
    furnished = False
    plate_error: str | None = None
    for concept in PLATE_CONCEPTS:
        try:
            boxes = meta.sam_segment(
                before_path, concept, trace=trace, purpose="live.sam.plate",
                target={"room": room["id"], "concept": concept},
            )
        except meta_client.MetaError as exc:
            plate_error = plate_error or str(exc)
            continue
        for b in boxes:
            x1, y1, x2, y2 = b["box"]
            if (x2 - x1) * (y2 - y1) >= PLATE_MIN_AREA * image_area:
                furnished = True
                break
        if furnished:
            break

    plate["furnished"] = furnished
    if not furnished:
        if plate_error:
            plate["plate_check"] = {"status": "fail", "reason": plate_error, "correlation": None}
        return plate

    filename = f"{room['id']}_empty.jpg"
    try:
        data = meta.image_stage(
            before_path, EMPTY_PROMPT, trace=trace, purpose="live.image.empty",
            target={"room": room["id"]},
        )
        _save_checked(data, raw_dir / filename, live_dir / filename, meta, trace,
                      {"room": room["id"], "side": "empty"})
    except meta_client.MetaError as exc:
        plate["plate_check"] = {"status": "fail", "reason": str(exc), "correlation": None}
        return plate

    rel = f"live/{lid}/{filename}"
    check = _geometry_check(before_path, config.settings.media_dir / rel)
    plate["plate_check"] = check
    if check["status"] == "pass":
        plate["plate"] = rel
        plate["plate_source"] = "generated"
    else:
        (config.settings.media_dir / rel).unlink(missing_ok=True)
    return plate


def _structure_check(room: dict[str, Any], frame: dict[str, Any] | None, dst_path: Path,
                     meta, trace: list, style: str, before_path: Path | None = None,
                     align: dict[str, float] | None = None) -> tuple[dict[str, Any], dict[str, list]]:
    """Compare windows/doors on the style image against the Stage 1 source frame, with the
    same rules as the verifier (edge boxes not compared, framing drift <= 5% corrected,
    IoU 0.3). Windows seen through the room's glass are reported separately as outside view
    and do not make a style unavailable; the room's own windows and doors still do.

    Returns (check record, dst normalized boxes by concept). A source frame with
    no structure boxes is reported as not_checked, never as a pass.
    """
    src_boxes = (((frame or {}).get("sam") or {}).get("structure")) or []
    fw, fh = (frame or {}).get("width"), (frame or {}).get("height")
    if not src_boxes or not fw or not fh:
        return (
            {"status": "not_checked",
             "reason": "No windows or doors detected in the source frame; structure not compared."},
            {},
        )
    dw, dh = _size(dst_path)
    src_by: dict[str, list] = {}
    dst_by: dict[str, list] = {}
    for concept in STRUCTURE_CONCEPTS:
        src_by[concept] = [_norm(b["box"], (fw, fh)) for b in src_boxes if b.get("concept") == concept]
        dst = meta.sam_segment(
            dst_path, concept, trace=trace, purpose="live.sam.structure",
            target={"room": room["id"], "style": style, "concept": concept},
        )
        dst_by[concept] = [_norm(b["box"], (dw, dh)) for b in dst]
    if before_path is not None and before_path.is_file():
        # The room's own glass doors: windows seen through them are outside view. Same image and
        # concept for every style, so this is one Meta call per room (then cached).
        glass = meta.sam_segment(
            before_path, checks.GLASS_DOOR, trace=trace, purpose="live.sam.structure",
            target={"room": room["id"], "concept": checks.GLASS_DOOR, "side": "before"},
        )
        src_by[checks.GLASS_DOOR] = [_norm(b["box"], _size(before_path)) for b in glass]
    result = checks.compare_structure(src_by, dst_by, image_align=align)
    note = result["note"]
    if result["problems"]:
        record = {"status": "fail", "reason": f"Staging changed structure: {'; '.join(result['problems'])}.{note}"}
    elif result["outside"]:
        record = {"status": "pass", "reason": f"Room windows and doors preserved; outside view changed.{note}"}
    else:
        record = {"status": "pass", "reason": f"Windows and doors preserved.{note}"}
    record["outside_view"] = result["outside"]
    record["corrected"] = result["corrected"]
    return record, dst_by


def _pieces(path: Path, meta, trace: list, room_id: str, style: str) -> list[dict[str, Any]]:
    """Furniture pieces for the cascade: normalized boxes, tiny/huge dropped,
    near-duplicates deduped by IoU keeping the higher score, capped at 14."""
    w, h = _size(path)
    image_area = w * h
    found: list[dict[str, Any]] = []

    def segment(concept: str) -> list[dict[str, Any]]:
        return meta.sam_segment(
            path, concept, trace=trace, purpose="live.sam.pieces",
            target={"room": room_id, "style": style, "concept": concept},
        )

    with ThreadPoolExecutor(max_workers=SAM_WORKERS) as pool:
        results = list(pool.map(segment, FURNITURE_CONCEPTS))
    for concept, boxes in zip(FURNITURE_CONCEPTS, results):
        for b in boxes:
            x1, y1, x2, y2 = b["box"]
            area = (x2 - x1) * (y2 - y1)
            if area < PIECE_MIN_AREA * image_area or area > PIECE_MAX_AREA * image_area:
                continue
            found.append({"concept": concept, "box": _norm(b["box"], (w, h)),
                          "score": b.get("score")})
    kept: list[dict[str, Any]] = []
    for piece in sorted(found, key=lambda p: -(p["score"] or 0)):
        if all(_iou(piece["box"], k["box"]) <= PIECE_DEDUPE_IOU for k in kept):
            kept.append(piece)
    kept.sort(key=lambda p: _narea(p["box"]), reverse=True)
    return kept[:PIECE_MAX_COUNT]


def _cascade_prep(room_id: str, style_id: str, lid: str, before_path: Path, plate_path: Path,
                  plate_align: dict[str, float], style_path: Path,
                  align: dict[str, float] | None = None) -> dict[str, Any]:
    """Align the style image to the filmed frame and cut its furniture mask (no model calls)."""
    align = align or cascade.align(before_path, style_path)
    rel = f"live/{lid}/{room_id}_{style_id}_mask.png"
    info = cascade.furniture_mask(before_path, plate_path, plate_align, style_path, align,
                                  config.settings.media_dir / rel)
    return {"align": align, "mask": rel if info["usable"] else None, "mask_changed": info["changed"]}


def _prepare_room(listing: dict[str, Any], room: dict[str, Any], meta, trace: list,
                  raw_dir: Path, live_dir: Path) -> dict[str, Any]:
    s = config.settings
    lid = listing["id"]
    default_style = listing.get("style") or listings.DEFAULT_STYLE
    frames_by_id = {f["id"]: f for f in listing.get("frames") or []}
    frame = frames_by_id.get(room.get("source_frame"))
    before_rel = room.get("before")
    before_path = s.media_dir / before_rel if before_rel else None

    out: dict[str, Any] = {
        "id": room["id"],
        "name": room["name"],
        "type": room["type"],
        "main": bool(room.get("main")),
        "t": room.get("t"),
        "span": room.get("span"),
        "upload": room.get("upload"),
        "before": before_rel,
        "plate": before_rel,
        "plate_source": "before",
        "plate_check": None,
        "plate_furnished": False,
        "plate_align": dict(cascade.IDENTITY),
        "styles": {},
        "window": None,
        "size": None,
    }
    if before_path is None or not before_path.is_file():
        for style_id, preset in stage.STYLE_PRESETS.items():
            out["styles"][style_id] = {
                "label": preset["label"], "image": None, "source": "live",
                "available": False, "error": "No before image for this room.",
                "geometry": None, "structure": None, "pieces": [],
            }
        return out

    plate = _prepare_plate(room, before_path, meta, trace, raw_dir, live_dir, lid)
    if plate["plate"] is not None:
        out["plate"] = plate["plate"]
    out["plate_source"] = plate["plate_source"]
    out["plate_check"] = plate["plate_check"]
    out["plate_furnished"] = plate["furnished"] and plate["plate_source"] == "before"
    plate_path = s.media_dir / out["plate"]
    if out["plate_source"] == "generated":
        out["plate_align"] = cascade.align(before_path, plate_path)

    dst_windows: dict[str, list] = {}
    for style_id, preset in stage.STYLE_PRESETS.items():
        entry: dict[str, Any] = {
            "label": preset["label"], "image": None, "source": "live",
            "available": False, "error": None, "attempts": 0,
            "geometry": None, "structure": None, "pieces": [],
        }
        reuse = style_id == room.get("style") and room.get("after")
        # The Stage 1 image is the approved one and is never regenerated. A generated
        # style that drifts gets one retry with a stricter prompt, then stays unavailable.
        prompts = [None] if reuse else [stage.prompt_for(style_id), stage.prompt_for(style_id) + RETRY_RULES]
        try:
            for prompt in prompts:
                entry["attempts"] += 1
                if prompt is None:
                    entry["image"] = room["after"]
                    entry["source"] = "stage1"
                else:
                    data = meta.image_stage(
                        before_path, prompt, trace=trace, purpose="live.image.stage",
                        target={"room": room["id"], "style": style_id, "attempt": entry["attempts"]},
                    )
                    filename = f"{room['id']}_{style_id}.jpg"
                    _save_checked(data, raw_dir / filename, live_dir / filename, meta, trace,
                                  {"room": room["id"], "style": style_id})
                    entry["image"] = f"live/{lid}/{filename}"
                style_path = s.media_dir / entry["image"]
                entry["align"] = cascade.align(before_path, style_path)
                entry["geometry"] = _geometry_check(before_path, style_path, entry["align"])
                entry["structure"], dst_boxes = _structure_check(room, frame, style_path, meta, trace,
                                                                 style_id, before_path, entry["align"])
                dst_windows[style_id] = dst_boxes.get("window", [])
                entry["available"] = (
                    style_path.is_file()
                    and entry["geometry"]["status"] == "pass"
                    and entry["structure"]["status"] != "fail"
                )
                if entry["available"]:
                    break
            if entry["available"]:
                entry["pieces"] = _pieces(style_path, meta, trace, room["id"], style_id)
                entry.update(_cascade_prep(room["id"], style_id, lid, before_path, plate_path,
                                           out["plate_align"], style_path, entry["align"]))
        except meta_client.MetaError as exc:
            entry["available"] = False
            entry["error"] = str(exc)
        out["styles"][style_id] = entry

    # Window: prefer the source frame's structure box, else the largest window
    # seen on the default style image.
    src_windows: list[list[float]] = []
    if frame and frame.get("width") and frame.get("height"):
        fsize = (frame["width"], frame["height"])
        src_windows = [
            _norm(b["box"], fsize)
            for b in (((frame.get("sam") or {}).get("structure")) or [])
            if b.get("concept") == "window"
        ]
    windows = src_windows or dst_windows.get(default_style) or []
    if windows:
        out["window"] = max(windows, key=_narea)

    default_entry = out["styles"].get(default_style) or {}
    size_path = None
    if default_entry.get("image") and (s.media_dir / default_entry["image"]).is_file():
        size_path = s.media_dir / default_entry["image"]
    elif before_path.is_file():
        size_path = before_path
    if size_path is not None:
        w, h = _size(size_path)
        out["size"] = [w, h]
    return out


# ---------- moments ----------

def _default_pieces(room: dict[str, Any], default_style: str) -> list[dict[str, Any]]:
    entry = room["styles"].get(default_style) or {}
    if not entry.get("available"):
        return []
    return entry.get("pieces") or []


def _largest_piece(pieces: list[dict[str, Any]], concepts: tuple[str, ...]) -> list[float] | None:
    for concept in concepts:
        candidates = [p for p in pieces if p["concept"] == concept]
        if candidates:
            return max(candidates, key=lambda p: _narea(p["box"]))["box"]
    return None


def _coffee_focus(room: dict[str, Any], is_kitchen: bool, default_style: str,
                  meta, trace: list) -> list[float]:
    s = config.settings
    if is_kitchen:
        entry = room["styles"].get(default_style) or {}
        image = entry.get("image")
        path = s.media_dir / image if image else None
        if path and path.is_file():
            try:
                boxes = meta.sam_segment(
                    path, "kitchen counter", trace=trace, purpose="live.sam.focus",
                    target={"room": room["id"], "moment": "coffee"},
                )
            except meta_client.MetaError:
                boxes = []
            if boxes:
                best = max(boxes, key=lambda b: (b["box"][2] - b["box"][0]) * (b["box"][3] - b["box"][1]))
                return _norm(best["box"], _size(path))
        return COFFEE_FALLBACK_FOCUS
    table = _largest_piece(_default_pieces(room, default_style), ("table",))
    return table or COFFEE_FALLBACK_FOCUS


def _prepare_moments(listing: dict[str, Any], rooms: list[dict[str, Any]], meta,
                     trace: list, raw_dir: Path, live_dir: Path) -> list[dict[str, Any]]:
    s = config.settings
    lid = listing["id"]
    default_style = listing.get("style") or listings.DEFAULT_STYLE
    moments: list[dict[str, Any]] = []

    view_room = next(
        (r for r in rooms if r["type"] in ("terrace", "living") and r["window"]),
        None,
    ) or next((r for r in rooms if r["window"]), None)
    if view_room:
        moments.append({"id": "view", "label": MOMENT_LABELS["view"],
                        "room_id": view_room["id"], "focus": view_room["window"], "images": {}})

    sit_room = next(
        (r for r in rooms if r["type"] == "living"
         and _largest_piece(_default_pieces(r, default_style), ("sofa", "chair"))),
        None,
    ) or next(
        (r for r in rooms
         if _largest_piece(_default_pieces(r, default_style), ("sofa", "chair"))),
        None,
    )
    if sit_room:
        focus = _largest_piece(_default_pieces(sit_room, default_style), ("sofa", "chair"))
        moments.append({"id": "sit", "label": MOMENT_LABELS["sit"],
                        "room_id": sit_room["id"], "focus": focus, "images": {}})

    coffee_room = next((r for r in rooms if r["type"] == "kitchen"), None)
    is_kitchen = coffee_room is not None
    if coffee_room is None:
        ranked = [
            r for r in rooms
            if _largest_piece(_default_pieces(r, default_style), ("table",))
        ]
        ranked.sort(key=lambda r: {"dining": 0, "living": 1}.get(r["type"], 2))
        coffee_room = ranked[0] if ranked else None
    if coffee_room:
        focus = _coffee_focus(coffee_room, is_kitchen, default_style, meta, trace)
        surface = "counter" if is_kitchen else "table"
        images: dict[str, str] = {}
        for style_id, entry in coffee_room["styles"].items():
            if not entry.get("available") or not entry.get("image"):
                continue
            try:
                data = meta.image_stage(
                    s.media_dir / entry["image"], COFFEE_PROMPT.format(surface=surface),
                    trace=trace, purpose="live.image.moment",
                    target={"room": coffee_room["id"], "style": style_id, "moment": "coffee"},
                )
                filename = f"{coffee_room['id']}_coffee_{style_id}.jpg"
                _save_checked(data, raw_dir / filename, live_dir / filename, meta, trace,
                              {"room": coffee_room["id"], "style": style_id, "moment": "coffee"})
                images[style_id] = f"live/{lid}/{filename}"
            except meta_client.MetaError:
                continue
        moments.append({"id": "coffee", "label": MOMENT_LABELS["coffee"],
                        "room_id": coffee_room["id"], "focus": focus, "images": images})
    return moments


# ---------- live job log ----------
# The Meta call trace of each running (or recently finished) Live-In job, by job id, so the
# console can show what the job is doing. In memory only: the saved trace stays in live["trace"].
JOB_TRACES: dict[str, list[dict[str, Any]]] = {}
_JOB_TRACE_KEEP = 20


def _track(job_id: str, trace: list[dict[str, Any]]) -> None:
    JOB_TRACES[job_id] = trace
    while len(JOB_TRACES) > _JOB_TRACE_KEEP:
        JOB_TRACES.pop(next(iter(JOB_TRACES)))


# ---------- job handler ----------

def run(job: dict[str, Any]) -> None:
    listing = db.get_listing(job["listing_id"])
    if listing is None or listing.get("status") != "published" or not listing.get("published"):
        if listing is not None and isinstance(listing.get("live"), dict):
            listing["live"]["status"] = "failed"
            listing["live"]["error"] = "Live-In-It needs a published listing."
            db.save_listing(listing)
        db.update_job(job["id"], status="failed", error="Live-In-It needs a published listing.")
        return

    live_block = listing.get("live")
    if not isinstance(live_block, dict):
        live_block = {"residence": None, "status": "preparing", "job_id": job["id"],
                      "requested_at": db.now(), "prepared_at": None, "error": None,
                      "rooms": [], "moments": [], "trace": [], "calls": 0}
        listing["live"] = live_block
    live_block["trace"] = []
    live_block["status"] = "preparing"
    trace = live_block["trace"]
    _track(job["id"], trace)

    client = meta_client.get_client()
    if hasattr(client, "reset_budget"):
        client.reset_budget()

    s = config.settings
    lid = listing["id"]
    raw_dir = s.staged_raw_dir / "live" / lid
    live_dir = s.media_dir / "live" / lid
    raw_dir.mkdir(parents=True, exist_ok=True)
    live_dir.mkdir(parents=True, exist_ok=True)
    try:
        published_rooms = listing["published"].get("rooms") or []
        main = main_room(published_rooms)
        if main is None:
            raise listings.ReviewError(422, NO_MAIN_ROOM)
        # Token guard: the main living room first; the rest only if it yields a usable style.
        # Utility rooms (bathroom, laundry, other) are walked past on the video, never staged.
        todo = [main] + [r for r in published_rooms if r is not main and not is_utility(r)]
        skipped = [r["id"] for r in published_rooms if r is not main and is_utility(r)]
        out_rooms: list[dict[str, Any]] = []
        guard = {"main_room": main["id"], "order": [], "skipped_utility": skipped, "held": []}
        for index, room in enumerate(todo):
            if out_rooms and not any(st.get("available") for st in out_rooms[0]["styles"].values()):
                guard["held"] = [r["id"] for r in todo[index:]]
                break
            db.update_job(job["id"], stage=f"live:{room['id']}",
                          progress=round(index / (len(todo) + 1) * 100))
            guard["order"].append(room["id"])
            out_rooms.append(_prepare_room(listing, room, client, trace, raw_dir, live_dir))
        db.update_job(job["id"], stage="live:moments",
                      progress=round(len(todo) / (len(todo) + 1) * 100))
        moments = _prepare_moments(listing, out_rooms, client, trace, raw_dir, live_dir)
        out_rooms.sort(key=lambda r: (r["upload"] or 0, r["t"] if r["t"] is not None else 0))
        live_block.update(
            status="ready", prepared_at=db.now(), rooms=out_rooms, moments=moments,
            calls=getattr(client, "calls", 0), error=None, guard=guard,
        )
        db.save_listing(listing)
        db.update_job(job["id"], status="done", stage="ready", progress=100)
    except Exception as exc:
        if isinstance(exc, listings.ReviewError):
            message = str(exc)
        else:
            log.exception("live job %s crashed", job["id"])
            message = f"Live-In-It preparation stopped unexpectedly ({exc.__class__.__name__})."
        live_block.update(status="failed", error=message)
        db.save_listing(listing)
        db.update_job(job["id"], status="failed", error=message)


# ---------- request + payload ----------

def main_room(rooms: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The main living space among (published, included) rooms."""
    rooms = [r for r in rooms if not r.get("rejected")]
    marked = next((r for r in rooms if r.get("main")), None)
    if marked is not None:
        return marked
    for room_type in MAIN_TYPES:
        found = next((r for r in rooms if r.get("type") == room_type), None)
        if found is not None:
            return found
    return None


def eligibility(listing: dict[str, Any]) -> dict[str, Any]:
    """Can a buyer enter this listing? Any published listing with a main living space can."""
    live_block = listing.get("live") or {}
    status = live_block.get("status")
    if listing.get("status") != "published":
        return {"eligible": False, "reason": "Live-In-It opens only after the broker publishes this listing.",
                "status": status}
    rooms = (listing.get("published") or {}).get("rooms") or []
    main = main_room(rooms)
    if main is None:
        return {"eligible": False, "reason": NO_MAIN_ROOM, "status": status}
    return {"eligible": True, "reason": None, "status": status, "main_room": main["id"],
            "main_room_name": main.get("name")}


def request(listing: dict[str, Any], residence: str | None = None) -> str:
    """Gate + enqueue a Live-In-It job for any published listing with a main living space.
    `residence` optionally links it to a seeded home-page residence (city must match)."""
    gate = eligibility(listing)
    if listing["status"] != "published":
        raise listings.ReviewError(409, gate["reason"])
    if residence is not None:
        if residence not in LIVE_RESIDENCES:
            raise listings.ReviewError(
                422, "There are no seeded home-page residences; prepare without a residence link.")
        seed_city = ((_seed_entry(residence) or {}).get("facts") or {}).get("city") or ""
        if (listing["facts"].get("city") or "").strip().lower() != seed_city.lower():
            raise listings.ReviewError(422, f"This listing isn't in {seed_city}, so it can't open as that residence.")
    if not gate["eligible"]:
        raise listings.ReviewError(422, gate["reason"])
    if (listing.get("live") or {}).get("status") == "preparing":
        raise listings.ReviewError(409, "Live-In-It is already being prepared.")
    job_id = db.new_id("job")
    listing["live"] = {
        "residence": residence,
        "status": "preparing",
        "job_id": job_id,
        "requested_at": db.now(),
        "prepared_at": None,
        "error": None,
        "rooms": [],
        "moments": [],
        "trace": [],
        "calls": 0,
    }
    db.save_listing(listing)
    with db.connect() as conn:
        db.insert_job(conn, job_id, listing["id"], "live")
    return job_id


def _seed_entry(residence_id: str | None) -> dict[str, Any] | None:
    if not residence_id:
        return None
    try:
        entries = json.loads((config.settings.seed_dir / "listings.json").read_text())
    except OSError:
        return None
    return next((entry for entry in entries if entry.get("id") == residence_id), None)


def _seed_note(residence_id: str | None) -> str | None:
    return (_seed_entry(residence_id) or {}).get("note")


def _walk_path(published: dict[str, Any], prepared: set[str]) -> list[dict[str, Any]]:
    """Every published room on the video timeline, in video order. Prepared rooms are where the
    walk stops for the cascade; the others (utility rooms) are walked past and only labelled."""
    rooms = [r for r in published.get("rooms") or [] if r.get("t") is not None]
    rooms.sort(key=lambda r: (r.get("upload") or 0, r["t"]))
    return [{"id": r["id"], "name": r["name"], "type": r["type"], "t": r["t"], "span": r.get("span"),
             "upload": r.get("upload"), "main": bool(r.get("main")), "prepared": r["id"] in prepared}
            for r in rooms]


def _sam_map(frame: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project stored image-space openings into a view schematic, not a floor plan."""
    if not frame or not frame.get("width") or not frame.get("height"):
        return None
    width, height = frame["width"], frame["height"]
    detections = []
    for item in ((frame.get("sam") or {}).get("structure") or []):
        box = item.get("box")
        if item.get("concept") not in {"window", "door"} or not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        if not all(isinstance(v, (int, float)) for v in box):
            continue
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            continue
        x = (x1 + x2) / (2 * width)
        # Without stored wall masks, assignment is based on image position only.
        wall = "left" if x < 0.33 else "right" if x > 0.66 else "back"
        detections.append({"concept": item["concept"], "x_center": x,
                           "width": (x2 - x1) / width, "wall": wall})
    return {"source_frame": frame.get("id"), "detections": detections, "has_wall_masks": False} if detections else None


def payload(listing: dict[str, Any]) -> dict[str, Any]:
    published = listing.get("published") or {}
    live_block = listing.get("live") or {}
    ready = live_block.get("status") == "ready"
    source_rooms = {r["id"]: r for r in listing.get("rooms") or []}
    frames = {f["id"]: f for f in listing.get("frames") or []}
    rooms = [{**r, "sam_map": _sam_map(frames.get(source_rooms.get(r["id"], {}).get("source_frame")))}
             for r in (live_block.get("rooms") or [])] if ready else []
    video = published.get("video")
    calls_by_purpose: dict[str, int] = {}
    for entry in live_block.get("trace") or []:
        if entry.get("cached"):
            continue
        purpose = entry.get("purpose")
        if purpose:
            calls_by_purpose[purpose] = calls_by_purpose.get(purpose, 0) + 1
    return {
        "listing_id": listing["id"],
        "residence": live_block.get("residence"),
        "status": live_block.get("status"),
        "job_id": live_block.get("job_id"),
        "error": live_block.get("error"),
        "prepared_at": live_block.get("prepared_at"),
        "title": published.get("title"),
        "facts": published.get("facts") or {},
        "price_display": published.get("price_display"),
        "approved_at": published.get("approved_at"),
        "published_at": published.get("published_at"),
        "note": listing.get("note") or _seed_note(live_block.get("residence")),
        "styles": [{"id": style_id, "label": preset["label"]}
                   for style_id, preset in stage.STYLE_PRESETS.items()],
        "default_style": listing.get("style") or listings.DEFAULT_STYLE,
        "rooms": rooms,
        "moments": (live_block.get("moments") or []) if ready else [],
        "video": video,
        "path": _walk_path(published, {r["id"] for r in rooms}) if video else [],
        "guard": live_block.get("guard"),
        "calls": live_block.get("calls") or 0,
        "calls_by_purpose": calls_by_purpose,
    }


def for_residence(residence_id: str) -> dict[str, Any] | None:
    """Most recently requested published listing prepared for this residence,
    preferring a ready one over preparing/failed."""
    if residence_id not in LIVE_RESIDENCES:
        return None
    candidates = [
        item for item in db.list_listings()
        if item.get("status") == "published"
        and isinstance(item.get("live"), dict)
        and item["live"].get("residence") == residence_id
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item["live"].get("requested_at") or "", reverse=True)
    ready = [item for item in candidates if item["live"].get("status") == "ready"]
    pick = (ready or candidates)[0]
    return {"listing_id": pick["id"], "status": pick["live"].get("status")}


def rerun_style(job: dict[str, Any]) -> None:
    """Regenerate one style; retain its existing image unless all checks succeed."""
    _, room_id, style_id = job["kind"].split(":", 2)
    listing = db.get_listing(job["listing_id"])
    if not listing or listing.get("status") != "published":
        raise ValueError("Listing is no longer published.")
    room = next((r for r in listing.get("live", {}).get("rooms", []) if r.get("id") == room_id), None)
    source_room = next((r for r in listing.get("published", {}).get("rooms", []) if r.get("id") == room_id), None)
    if not room or not source_room or not room.get("before"):
        raise ValueError("Source room is unavailable.")
    frame = next((f for f in listing.get("frames", []) if f.get("id") == source_room.get("source_frame")), None)
    before = config.settings.media_dir / room["before"]
    raw_dir = config.settings.staged_raw_dir / "live" / listing["id"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    candidate = raw_dir / f"{job['id']}_checked.jpg"
    trace: list = []
    _track(job["id"], trace)
    meta = meta_client.get_client()
    meta.reset_budget()
    required = {"living": ("sofa", "table"), "bedroom": ("bed",), "dining": ("table", "chair")}.get(room.get("type"))
    if not required:
        raise ValueError("Targeted furniture rerun is available for living rooms, bedrooms and dining rooms.")
    prompt = (stage.prompt_for(style_id) + stage.STRICT_FRAMING + stage.STRICT_STRUCTURE
              + f" Furnish this {room.get('type')} room with clearly visible " + " and ".join(required) + ". "
              + f"Render variation {job['id']}.")
    # Recheck a face-checked candidate rejected solely for missing source boxes,
    # so adding the source scan does not spend another image-generation call.
    previous = next((j for j in reversed(db.list_jobs(listing["id"]))
                     if j["id"] != job["id"] and j["kind"] == job["kind"]), None)
    reusable = previous and previous["status"] == "failed" and (
        ((previous.get("error") or "").startswith("Verification did not pass: Geometry preserved")
         and "No windows or doors detected in the source frame" in (previous.get("error") or ""))
        or (room.get("type") == "living" and previous.get("error") == "Furniture not detected: table; existing style retained.")
    )
    previous_candidate = raw_dir / f"{previous['id']}_checked.jpg" if reusable else None
    if previous_candidate and previous_candidate.is_file():
        candidate.write_bytes(previous_candidate.read_bytes())
    else:
        data = meta.image_stage(before, prompt, trace=trace, purpose="live.image.stage",
                                target={"room": room_id, "style": style_id, "job": job["id"]})
        _save_checked(data, raw_dir / f"{job['id']}_raw.jpg", candidate, meta, trace, {"room": room_id, "style": style_id})
    align = cascade.align(before, candidate)
    is_concept = style_id in checks.CONCEPT_STYLES
    geometry = _geometry_check(before, candidate, align)
    concept_geometry = (_geometry_check(before, candidate, align, min_corr=checks.GEOMETRY_MIN_CORR_CONCEPT)
                        if is_concept else geometry)
    # Older frames can lack saved SAM boxes. Detect source structure now instead of
    # treating missing evidence as a failed comparison or silently passing it.
    if not (((frame or {}).get("sam") or {}).get("structure")):
        source_boxes = []
        for concept in STRUCTURE_CONCEPTS:
            for box in meta.sam_segment(before, concept, trace=trace, purpose="live.sam.source_structure",
                                        target={"room": room_id, "style": style_id, "concept": concept}):
                source_boxes.append({**box, "concept": concept})
        width, height = _size(before)
        frame = {**(frame or {}), "width": width, "height": height,
                 "sam": {**((frame or {}).get("sam") or {}), "structure": source_boxes}}
    if not (frame.get("sam") or {}).get("structure"):
        # Floor-to-ceiling glazing is often missed by SAM's generic "window" query.
        src_glass = meta.sam_segment(before, "glass wall", trace=trace, purpose="live.sam.source_structure",
                                     target={"room": room_id, "style": style_id, "concept": "glass wall"})
        dst_glass = meta.sam_segment(candidate, "glass wall", trace=trace, purpose="live.sam.structure",
                                     target={"room": room_id, "style": style_id, "concept": "glass wall"})
        if src_glass and dst_glass:
            src_boxes = [_norm(box["box"], _size(before)) for box in src_glass]
            dst_boxes = [_norm(box["box"], _size(candidate)) for box in dst_glass]
            result = checks.compare_structure({"window": src_boxes}, {"window": dst_boxes}, image_align=align)
            if result["problems"] or result["compared"] == 0:
                structure = {"status": "fail", "reason": "Glass wall comparison failed or was inconclusive." + result["note"]}
            else:
                structure = {"status": "pass", "reason": "Glass wall compared at IoU 0.3." + result["note"]}
        else:
            structure = {"status": "not_checked", "reason": "Glass wall not detected in both images; structure not compared."}
    else:
        structure, _ = _structure_check(source_room, frame, candidate, meta, trace, style_id, before, align)
    drift = checks.image_drift(align)
    drift_record = {"status": "pass", "value": drift, "reason": f"Framing drift {drift:.3f} within 5% cap."}
    if drift > checks.FRAMING_MAX_DRIFT:
        if not is_concept:
            raise ValueError("Framing drift exceeds 5%; existing style retained.")
        # Day's explicit direction: a concept style may exceed the drift cap.
        # Recorded, not hidden: still not broker-verified as the same room.
        drift_record = {"status": "concept-pass", "value": drift,
                        "reason": f"Concept style {style_id} — framing drift {drift:.3f} exceeds 5% cap, not broker-verified as the same room."}
    if concept_geometry["status"] != "pass" or (not is_concept and structure["status"] != "pass"):
        raise ValueError(f"Verification did not pass: {geometry['reason']} {structure['reason']}")
    pieces = _pieces(candidate, meta, trace, room_id, style_id)
    primary = {"living": ("sofa",), "bedroom": ("bed",), "dining": ("table",)}[room["type"]]
    missing = [concept for concept in primary if not any(p["concept"] == concept for p in pieces)]
    if missing:
        raise ValueError(f"Furniture not detected: {', '.join(missing)}; existing style retained.")
    rel = f"live/{listing['id']}/{room_id}_{style_id}_{job['id']}.jpg"
    dest = config.settings.media_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(candidate.read_bytes())
    current = db.get_listing(listing["id"])
    target = next((r for r in (current or {}).get("live", {}).get("rooms", []) if r.get("id") == room_id), None)
    if not target or current.get("status") != "published":
        dest.unlink(missing_ok=True)
        raise ValueError("Listing changed during preparation; result not attached.")
    target["styles"][style_id] = {**target["styles"].get(style_id, {}), "label": stage.STYLE_PRESETS[style_id]["label"], "image": rel, "source": "live", "available": True, "concept": is_concept,
                                  "error": None, "geometry": geometry, "concept_geometry": concept_geometry if is_concept else None, "structure": structure, "pieces": pieces,
                                  "align": align, "drift": drift_record, "mask": None}
    current["live"].setdefault("trace", []).extend(trace)
    current["live"]["calls"] = current["live"].get("calls", 0) + meta.calls
    db.save_listing(current)
    db.update_job(job["id"], status="done", stage="ready", progress=100)
