"""Virtual staging via Muse Image, image-to-image from each room's hero frame.

The prompt hard-requires geometry preservation: same room, same camera, every
wall/window/door/floor exactly where it was — only furniture and decor change.
Each staged image then gets a SAM face check and any hit is blurred in place.

A room the verifier still flags can be re-staged once or twice with a stricter
prompt (image.restage): different prompt text means a new Meta call, so the
stricter wording is what actually changes the picture.
"""

import io
from datetime import UTC, datetime
from typing import Any

from PIL import Image

import checklist
import config
import meta_client
from pipeline import privacy
from pipeline.classify import is_utility

STYLE_PRESETS = {
    "modern-luxury": {
        "label": "Modern luxury",
        "description": "Restyle this room as a modern luxury interior with a few large pieces "
                       "only, low and clean-lined: one large warm-ivory sofa, one low sculptural "
                       "travertine or stone coffee table, one large warm-neutral rug grounding "
                       "the set, and exactly one accent piece — either a charcoal armchair or a "
                       "champagne-metal floor lamp, never both. Palette: warm ivory upholstery, "
                       "charcoal and champagne-metal accents, at most one small muted-cyan "
                       "cushion or artwork. No small decor: no vases, books, throws, plants, "
                       "dried stems, or objects on counters and shelves. Warm light, not flat "
                       "daylight. Light and space first — do not fill empty floor.",
    },
    "coastal": {
        "label": "Coastal",
        "description": "Restyle this room as a coastal luxury interior: light oak, linen, rattan, "
                       "soft whites and sand tones, airy sheer curtains.",
    },
    "minimal": {
        "label": "Minimal",
        "description": "Restyle this room as a warm minimal interior: few sculptural pieces, "
                       "pale plaster tones, negative space, soft daylight.",
    },
}

GEOMETRY_RULES = (
    "This must remain the exact same room photographed from the exact same camera position, "
    "perspective and lens. Keep every wall, window, door, ceiling, floor and built-in exactly "
    "where it is; do not move, resize, add or remove any architectural feature. Change only "
    "furniture, lighting and decor. No people, no text, no logos, no personal photographs."
)

MAX_RESTAGE_LEVEL = 2

STRICT_FRAMING = (
    "Critical: the output must line up with the source photo: identical camera position, "
    "framing, zoom and crop; do not pan, zoom, rotate, crop or extend the image."
)
STRICT_STRUCTURE = (
    "Keep every door, cabinet door, drawer front, window, mirror and built-in exactly as in "
    "the source: same count, same position, same size, fully visible. Do not add pendant "
    "lights, chandeliers, wall sconces, curtains, artwork or tall plants in front of or over "
    "any door, window, cabinet or mirror. Do not place chairs, stools or furniture in front "
    "of cabinet doors or doorways."
)
WET_ROOM_TYPES = {"kitchen", "bathroom"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def prompt_for(style: str) -> str:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["modern-luxury"])
    return f"{preset['description']} {GEOMETRY_RULES}"


def _structure_counts(frame: dict[str, Any] | None) -> str:
    structure = ((frame or {}).get("sam") or {}).get("structure")
    if not structure:
        return ""
    doors = sum(1 for box in structure if box.get("concept") == "door")
    windows = sum(1 for box in structure if box.get("concept") == "window")
    return (
        f"The source photo shows {doors} door(s) (including cabinet doors) and "
        f"{windows} window(s); the result must show exactly the same {doors} door(s) "
        f"and {windows} window(s) in the same places."
    )


def _wet_room_note(room: dict[str, Any]) -> str:
    room_type = room.get("type")
    if room_type not in WET_ROOM_TYPES:
        return ""
    return (
        f"This is a {room_type}: keep all cabinetry, countertops, appliances, sinks, "
        "faucets, tiles, mirrors and light fixtures exactly as they are; style it only "
        "with a few small decor objects placed on the countertops."
    )


def restage_prompt(style: str, room: dict[str, Any], frame: dict[str, Any] | None,
                   level: int) -> str:
    """Stricter staging prompt for a flagged room. Part of the Meta cache key:
    keep the wording stable and deterministic."""
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["modern-luxury"])
    counts = _structure_counts(frame)
    if level >= 2:
        surface = {
            "kitchen": "on the countertop or island",
            "bathroom": "on the vanity countertop",
        }.get(room.get("type"),
              "such as a plant, a small side table or a rug, kept away from walls, "
              "doors and windows")
        head = (f"Make a minimal staging edit: add only two or three small decor objects "
                f"{surface} in a {preset['label'].lower()} style. Change nothing else in "
                f"the image.")
        return " ".join(part for part in
                        (head, GEOMETRY_RULES, STRICT_FRAMING, STRICT_STRUCTURE, counts)
                        if part)
    head = f"{preset['description']} {GEOMETRY_RULES} {STRICT_FRAMING} {STRICT_STRUCTURE}"
    return " ".join(part for part in (head, counts, _wet_room_note(room)) if part)


def _staged_image(listing: dict[str, Any], room: dict[str, Any], prompt: str,
                  filename: str, *, style: str, purpose: str,
                  target: dict[str, Any]) -> None:
    """image_stage -> staged-faces check -> blur -> save under staged/<lid>/.

    Sets room["after"]/room["style"]. Raises MetaError on any Meta failure.
    """
    s = config.settings
    lid = listing["id"]
    meta = meta_client.get_client()
    trace = listing.setdefault("trace", [])
    pre_dir = s.staged_raw_dir / lid
    pre_dir.mkdir(parents=True, exist_ok=True)
    out_dir = s.media_dir / "staged" / lid
    out_dir.mkdir(parents=True, exist_ok=True)

    data = meta.image_stage(
        s.media_dir / room["before"], prompt,
        trace=trace, purpose=purpose, target=target,
    )
    img = Image.open(io.BytesIO(data)).convert("RGB")
    # Face check runs on the non-served copy; only cleared images reach media_dir.
    pre_path = pre_dir / filename
    img.save(pre_path, "JPEG", quality=90)
    faces = meta.sam_segment(
        pre_path, "face", trace=trace, purpose="sam.staged_faces", target=target,
    )
    if faces:
        privacy.blur_regions(img, faces)
    img.save(out_dir / filename, "JPEG", quality=90)
    room["after"] = f"staged/{lid}/{filename}"
    room["style"] = style


NO_MAIN_ROOM = ("Not staged: no main living space was found in this video, so no Meta Image calls "
                "were spent on bathrooms, laundry or door close-ups.")
MAIN_FAILED = "Not staged: the main living room did not stage, so the rest of the budget was held."


def stage_rooms(listing: dict[str, Any]) -> dict[str, Any]:
    """Token guard: the main living room is confirmed and staged FIRST. Without one nothing is
    staged; if it fails, utility and secondary rooms are not staged either. Primary rooms then
    stage before utility rooms. The order is recorded in listing["token_guard"]."""
    meta = meta_client.get_client()
    style = listing.get("style") or "modern-luxury"
    prompt = prompt_for(style)
    staged = 0
    first_error: str | None = None
    included = [r for r in listing["rooms"] if not r.get("rejected")]
    main = next((r for r in included if r.get("main")), None)
    order = ([main] if main else []) + sorted(
        (r for r in included if r is not main), key=lambda r: is_utility(r))
    guard: dict[str, Any] = {"main_room": main["id"] if main else None, "order": [], "skipped": [],
                             "at": _now()}

    for room in order:
        record = {"model": getattr(meta, "image_model", None), "prompt": prompt, "style": style, "error": None}
        if main is None or (room is not main and main.get("after") is None):
            record["error"] = NO_MAIN_ROOM if main is None else MAIN_FAILED
            room["staging"] = record
            guard["skipped"].append(room["id"])
            continue
        if not room.get("before"):
            record["error"] = "No blurred source frame."
            room["staging"] = record
            first_error = first_error or record["error"]
            continue
        guard["order"].append(room["id"])
        try:
            _staged_image(
                listing, room, prompt, f"{room['id']}_{style}.jpg",
                style=style, purpose="image.stage", target={"room": room["id"]},
            )
            staged += 1
        except meta_client.MetaError as exc:
            record["error"] = str(exc)
            first_error = first_error or record["error"]
        room["staging"] = record

    if main is None:
        guard["status"] = "no_main_room"
        guard["detail"] = NO_MAIN_ROOM
    elif main.get("after") is None:
        guard["status"] = "main_failed"
        guard["detail"] = f"{main['name']} did not stage ({first_error}); {len(guard['skipped'])} other room(s) held."
    else:
        names = {r["id"]: r["name"] for r in included}
        guard["status"] = "main_first"
        guard["detail"] = (f"{main['name']} confirmed and staged first; then "
                           + (", ".join(names[i] for i in guard["order"][1:]) or "no other rooms") + ".")
    listing["token_guard"] = guard

    if staged:
        checklist.set_item(
            listing, "staging_geometry", "generated",
            f"{staged} of {len(listing['rooms'])} rooms staged ({style}), {guard['detail']}",
        )
    else:
        checklist.set_item(listing, "staging_geometry", "failed",
                           guard["detail"] if main is None else first_error or "No rooms to stage.")
    return listing


def restage_room(listing: dict[str, Any], room_id: str, level: int) -> str | None:
    """Re-stage ONE flagged room with a stricter prompt. Returns None on success,
    else a short error message; the room keeps its current staging on failure."""
    room = next((r for r in listing.get("rooms") or [] if r.get("id") == room_id), None)
    if room is None:
        return f"Room {room_id} not found."
    if not room.get("before"):
        return f"{room.get('name') or room_id} has no blurred source frame."
    style = room.get("style") or listing.get("style") or "modern-luxury"
    frame = next(
        (f for f in listing.get("frames") or [] if f.get("id") == room.get("source_frame")),
        None,
    )
    prompt = restage_prompt(style, room, frame, level)
    meta = meta_client.get_client()
    previous_staging = room.get("staging")
    previous_after = room.get("after")
    try:
        _staged_image(
            listing, room, prompt, f"{room_id}_{style}_strict{level}.jpg",
            style=style, purpose="image.restage",
            target={"room": room_id, "level": level},
        )
    except meta_client.MetaError as exc:
        room["restage_error"] = {"level": level, "error": str(exc), "at": _now()}
        return str(exc)
    if previous_staging:
        room.setdefault("staging_history", []).append(
            {**previous_staging, "after": previous_after, "replaced_at": _now()})
    room["staging"] = {
        "model": getattr(meta, "image_model", None),
        "prompt": prompt,
        "style": style,
        "error": None,
        "level": level,
        "purpose": "image.restage",
        "at": _now(),
    }
    room.pop("restage_error", None)
    return None
