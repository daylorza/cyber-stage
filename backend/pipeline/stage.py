"""Virtual staging via Muse Image, image-to-image from each room's hero frame.

Listing styles preserve the room and its architecture. The 2142 style is
concept art: it preserves the layout while allowing futuristic transformations.
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
        "description": (
            "Stage in a refined modern luxury style with clean-lined, sculptural furnishings. "
            "Use warm ivory upholstery, rich textured fabrics, honed travertine or veined "
            "stone, restrained champagne metal and subtle charcoal accents. Favor a calm, "
            "gallery-like composition with generous open space and a few substantial, "
            "appropriately scaled pieces. Add a small, curated selection of abstract wall art "
            "in a slim refined frame and sculptural decor such as a ceramic vessel or tray, "
            "where suitable surfaces and clear wall space exist."
        ),
    },
    "coastal": {
        "label": "Coastal",
        "description": (
            "Stage in a refined coastal style with comfortable, relaxed, tailored furnishings. "
            "Use soft white and sand tones, linen, natural woven textures, light oak and "
            "a restrained muted ocean-blue accent. Keep the room airy and uncluttered; "
            "add understated landscape or abstract wall art in a light wood frame and a few "
            "natural ceramic or woven accents where space allows. Avoid nautical motifs and "
            "beach-themed decor."
        ),
    },
    "minimal": {
        "label": "Minimal",
        "description": (
            "Stage in a warm, understated minimal style with simple, sculptural furnishings. "
            "Use ivory, warm neutral textiles, pale stone and light wood with subtle texture. "
            "Keep the composition quiet and uncluttered, with generous negative space; "
            "add one understated abstract artwork and a few simple ceramic or natural-material "
            "accents where space allows. Avoid busy patterns and visual clutter."
        ),
    },
    "2142": {
        "label": "Cyberpunk",
        "description": (
            "Create photorealistic futuristic concept art of this exact room as a luxurious penthouse in 2142, not a listing-accurate staging. "
            "Preserve the original camera position, perspective, room proportions, walls, "
            "ceiling shape, floor, windows, door openings and architectural layout. "
            "Keep all windows and doors in their existing positions and retain their frames. "
            "Adapt the furniture arrangement to the available space without blocking openings "
            "or walkways. "
            "Create a warm, sophisticated interior with a palette of ivory, cream, champagne, "
            "soft taupe and warm gray. Use polished white marble with subtle gray veining, "
            "reflective stone, smoked or mirrored glass, and polished chrome. "
            "Choose futuristic furnishings suited to the room's function and available space. "
            "For a living room, use a curved ivory sofa, a sculptural low chrome or reflective "
            "stone coffee table and a textured taupe-gray rug, scaled to fit. Include a "
            "matching rounded chaise or ottoman only if space allows. Keep the arrangement "
            "open and balanced. "
            "Enhance an existing feature wall with elegant backlit marble panels, slim mirrored "
            "display shelving and a low floating console, while preserving the wall's shape and "
            "any existing openings. Use only a few carefully placed decorative objects and "
            "one understated plant or branch arrangement. Add sophisticated futuristic abstract "
            "wall art or a subtle luminous art panel on clear wall space, if appropriate. "
            "Light the room with a warm golden glow from recessed ceiling coves, concealed "
            "shelf lighting and slim vertical wall lights. Add thin, controlled cyan and violet "
            "light accents along existing ceiling curves, beneath the sofa or console, and "
            "around architectural edges. Include a sculptural concentric-ring ceiling light "
            "only where the existing ceiling and fixtures allow it. "
            "Doors: keep every door opening in exactly the same place and size, but make the "
            "doors retractable translucent panels with no doorknobs — a laser-gate privacy "
            "shimmer that frosts on touch, with the door frame still clearly visible so every "
            "door still reads as a door. Replace any ceiling fan with a levitating halo climate "
            "ring, no blades, in the same ceiling position. "
            "Through the existing windows, show a believable futuristic city skyline at blue "
            "hour or night, with distant illuminated skyscrapers. Preserve the window frames "
            "and the view's perspective. The finished image should look like a photorealistic "
            "high-end real estate photograph: inviting, polished and subtly futuristic. "
            "Avoid garish neon, dark dystopian interiors, carbon fiber, exposed wires, robots, "
            "weapons, excessive clutter and changes to the room's structure."
        ),
    },
}

GEOMETRY_RULES = (
    "Virtually stage the source photo for a real estate listing. Preserve the exact camera "
    "position, framing, perspective and lens, and keep all walls, windows, doors, ceilings, "
    "floors, built-ins, fixtures, finishes and the exterior view as they are. Preserve the "
    "existing time of day and natural light direction. Choose furnishings suited to the "
    "room's function and scale them to fit. Keep doorways, windows, cabinets and walkways "
    "accessible; leave tight spaces open rather than forcing furniture into them. Add "
    "tasteful, appropriately scaled wall art and a few coordinated decorative accents "
    "only where suitable clear wall space or surfaces exist. Keep art off windows, "
    "doors, mirrors and built-ins, and avoid covering important features. Do not add "
    "art or wall decor in kitchens or bathrooms; follow their room-specific instructions. Match "
    "perspective, lighting, shadows and reflections for a photorealistic result. "
    "No people, text, logos or personal photographs."
)

FANTASY_RULES = (
    "This is futuristic concept art, not listing-accurate staging. Preserve the original "
    "camera position, framing, room proportions, structural layout, and the position and "
    "size of all window and door openings. Futuristic door panels, ceiling fixtures, "
    "surface treatments and the skyline described above are intentional. Keep openings "
    "recognizable and walkways clear. No people, text, logos or personal photographs."
)

ROOM_GUIDANCE = {
    "living": "Furnish as a living room, with seating and a coffee table or rug where space allows.",
    "bedroom": "Furnish as a bedroom, with an appropriately sized bed and bedside pieces where space allows.",
    "dining": "Furnish as a dining room, with an appropriately sized dining table and chairs where space allows.",
    "office": "Furnish as an office, with an appropriately sized desk and chair where space allows.",
    "terrace": "Furnish as a terrace with appropriately scaled outdoor seating where space allows.",
}

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


def prompt_for(style: str, room: dict[str, Any] | None = None) -> str:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["modern-luxury"])
    room = room or {}
    guidance = ROOM_GUIDANCE.get(room.get("type"),
        "Choose furnishings appropriate to the room's apparent function; if uncertain, "
        "keep the staging neutral and do not impose a new function.")
    rules = FANTASY_RULES if style == "2142" else GEOMETRY_RULES
    wet_note = "" if style == "2142" else _wet_room_note(room)
    return " ".join(part for part in (preset["description"], guidance, rules, wet_note) if part)


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
    if style == "2142":
        return " ".join(part for part in (prompt_for(style, room), STRICT_FRAMING, counts) if part)
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
    head = f"{prompt_for(style, room)} {STRICT_FRAMING} {STRICT_STRUCTURE}"
    return " ".join(part for part in (head, counts) if part)


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
    staged = 0
    first_error: str | None = None
    included = [r for r in listing["rooms"] if not r.get("rejected")]
    main = next((r for r in included if r.get("main")), None)
    order = ([main] if main else []) + sorted(
        (r for r in included if r is not main), key=lambda r: is_utility(r))
    guard: dict[str, Any] = {"main_room": main["id"] if main else None, "order": [], "skipped": [],
                             "at": _now()}

    for room in order:
        prompt = prompt_for(style, room)
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
