"""Virtual staging via Muse Image, image-to-image from each room's hero frame.

The prompt hard-requires geometry preservation: same room, same camera, every
wall/window/door/floor exactly where it was — only furniture and decor change.
Each staged image then gets a SAM face check and any hit is blurred in place.
"""

import io
from typing import Any

from PIL import Image

import checklist
import config
import meta_client
from pipeline import privacy

STYLE_PRESETS = {
    "modern-luxury": {
        "label": "Modern luxury",
        "description": "Restyle this room as a modern luxury interior: calm neutral palette, "
                       "designer furniture, layered lighting, museum-minimal styling.",
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


def prompt_for(style: str) -> str:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["modern-luxury"])
    return f"{preset['description']} {GEOMETRY_RULES}"


def stage_rooms(listing: dict[str, Any]) -> dict[str, Any]:
    s = config.settings
    lid = listing["id"]
    meta = meta_client.get_client()
    style = listing.get("style") or "modern-luxury"
    prompt = prompt_for(style)
    pre_dir = s.staged_raw_dir / lid
    pre_dir.mkdir(parents=True, exist_ok=True)
    out_dir = s.media_dir / "staged" / lid
    out_dir.mkdir(parents=True, exist_ok=True)
    trace = listing.setdefault("trace", [])
    staged = 0
    first_error: str | None = None

    for room in listing["rooms"]:
        if room.get("rejected"):
            continue
        record = {"model": getattr(meta, "image_model", None), "prompt": prompt, "style": style, "error": None}
        if not room.get("before"):
            record["error"] = "No blurred source frame."
            room["staging"] = record
            first_error = first_error or record["error"]
            continue
        try:
            data = meta.image_stage(
                s.media_dir / room["before"], prompt,
                trace=trace, target={"room": room["id"]},
            )
            img = Image.open(io.BytesIO(data)).convert("RGB")
            filename = f"{room['id']}_{style}.jpg"
            # Face check runs on the non-served copy; only cleared images reach media_dir.
            pre_path = pre_dir / filename
            img.save(pre_path, "JPEG", quality=90)
            faces = meta.sam_segment(
                pre_path, "face", trace=trace, purpose="sam.staged_faces",
                target={"room": room["id"]},
            )
            if faces:
                privacy.blur_regions(img, faces)
            img.save(out_dir / filename, "JPEG", quality=90)
            room["after"] = f"staged/{lid}/{filename}"
            room["style"] = style
            staged += 1
        except meta_client.MetaError as exc:
            record["error"] = str(exc)
            first_error = first_error or record["error"]
        room["staging"] = record

    if staged:
        checklist.set_item(
            listing, "staging_geometry", "generated",
            f"{staged} of {len(listing['rooms'])} rooms staged ({style})",
        )
    else:
        checklist.set_item(listing, "staging_geometry", "failed", first_error or "No rooms to stage.")
    return listing
