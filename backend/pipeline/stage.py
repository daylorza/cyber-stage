"""Virtual staging via Muse Image, image-to-image from each room's hero frame.

Listing styles preserve the room and its architecture. The 2142 style is
concept art: it preserves the layout while allowing futuristic transformations.
Each staged image then gets a SAM face check and any hit is blurred in place.

A room the verifier still flags can be re-staged once or twice with a stricter
prompt (image.restage): different prompt text means a new Meta call, so the
stricter wording is what actually changes the picture.
"""

import io
import random
from datetime import UTC, datetime
from threading import Lock
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
            "Restyle this room as a gallery-grade modern luxury interior, staged to the "
            "standard of a five-star residence. Use a few large architectural furnishings "
            "appropriate to the room's function, with exceptional proportions, tactile "
            "upholstery and carefully finished materials. Follow the selected design "
            "direction for furniture silhouettes, materials and colors. Ground the main "
            "arrangement with one large tonal rug where appropriate. Include at most one "
            "supporting accent chair or sculptural floor lamp where space allows. "
            "Use the source lighting direction with realistic layered shadows and depth. "
            "No small decor: no vases, books, throws, plants, dried stems or countertop "
            "ornaments. Preserve generous open floor and long sightlines."
        ),
        "variants": {
            "Warm sculptural": "Warm ivory boucle, honed travertine and champagne metal; generous rounded upholstered forms and softly carved stone profiles.",
            "Walnut atelier": "Dark walnut, saddle leather and brushed bronze with warm neutral textiles; tailored rectilinear upholstery and slender timber frames.",
            "Pale stone gallery": "Pale limestone, soft gray sculpted wool and satin nickel; broad monolithic profiles balanced with precisely curved upholstery.",
            "Smoked glass salon": "Smoked glass, charcoal velvet and champagne metal; sleek low horizontal forms with slender metallic supports and one restrained deep-blue textile accent.",
        },
    },
    "coastal": {
        "label": "Coastal",
        "description": (
            "Restyle this room as an elegant coastal luxury interior in a refined "
            "oceanfront residence. Use a few generous comfortable furnishings suited to "
            "the room's function. Follow the selected design direction for silhouettes, "
            "wood tones, textiles and stone. Favor tactile natural materials, relaxed "
            "tailoring and breathable woven textures. Use a large natural-fiber or tonal "
            "rug where appropriate. Work with the source daylight and existing light "
            "direction for an airy, serene photographic result. Keep floor space generous "
            "and sightlines long. Avoid nautical motifs, beach-themed decor, clutter and "
            "small decorative objects."
        ),
        "variants": {
            "Mediterranean calm": "Chalk-white linen, pale oak and cream limestone; softly rounded upholstery, carved stone profiles and quiet woven textures. Echo plaster tones in furnishings without changing existing walls.",
            "Contemporary shoreline": "Tailored ivory linen, bleached ash and pale honed stone; crisp low horizontal furnishings with slim open frames and a restrained muted ocean-blue accent.",
            "Weathered timber retreat": "Weathered light timber, oatmeal linen and warm sand woven fiber; generous relaxed forms and open woven accent frames, refined rather than rustic.",
            "Sea glass residence": "Cool off-white cotton, light natural oak, pale coastal stone and restrained sea-glass green; gently curved upholstery and transparent glass details, no literal shells or seaside ornaments.",
        },
    },
    "minimal": {
        "label": "Minimal",
        "description": (
            "Restyle this room as a museum-quiet minimal interior where every piece earns "
            "its place. Use only the essential functional furnishings for this room, "
            "with purposeful sculptural forms, subtle texture and precise proportions. "
            "Minimal does not mean unfurnished: include the main furniture required by "
            "the room-specific guidance. Follow the selected design direction rather "
            "than defaulting every room to ivory. Use one understated tonal rug where "
            "appropriate. Preserve the source lighting direction with soft realistic "
            "shadows revealing form. Maintain generous negative space and clean sightlines. "
            "Avoid busy patterns, clutter and small decorative objects."
        ),
        "variants": {
            "Warm oak quiet": "Natural warm oak, oatmeal linen and ivory textiles; low clean-lined forms with softly eased corners and visible natural grain.",
            "Monolithic stone": "Pale honed stone, chalk-white wool and soft gray textiles; block-like grounded profiles paired with simple generous upholstery.",
            "Dark timber stillness": "Dark-stained timber, charcoal fabric and warm gray wool; precise rectilinear furniture with slim profiles and quiet matte surfaces. Keep the room clearly exposed.",
            "Soft plaster forms": "Plaster-toned matte furniture, cream upholstery and a restrained light-wood accent; simple rounded volumes and continuous softly curved profiles. Leave existing wall finishes unchanged.",
        },
    },
    "2142": {
        "label": "Cyberpunk",
        "description": (
            "Restyle this exact room as a believable luxury cyberpunk residence in 2142. "
            "Let the selected design direction determine the degree of futurism in the "
            "furniture's construction, silhouette and materials. Softer luxury directions "
            "use generous upholstered forms, refined metal trim and discreet integrated "
            "technology; more technical directions use sculptural engineered outer shells, "
            "precision metal chassis, layered structural bases and purposeful panel seams. "
            "Apply the selected cyberpunk design direction consistently to furniture forms, "
            "dominant materials, upholstery, lighting colors and architectural details. "
            "Integrate technology into selected wall panels, furnishings and existing "
            "architectural edges. Where called for by the selected direction, use a few "
            "purposeful interface surfaces displaying abstract graphics without readable "
            "text. Otherwise keep technology discreet, with localized luminous details. "
            "Keep any door opening and frame exactly in place; futuristic sliding privacy "
            "panels must remain recognizable as doors. Any redesigned ceiling fixture "
            "must occupy the existing fixture's position. Preserve comfortable usable "
            "space and clear circulation paths. "
            "Through existing windows, retain the exterior view's composition, horizon, "
            "terrain, recognizable setting and perspective. Keep existing buildings' "
            "recognizable silhouettes, heights, spacing and apparent distance. Preserve "
            "the source exterior's time of day, weather and overall exposure. Add only "
            "subtle near-future refinements to buildings already visible: fine facade "
            "detailing, a few softly illuminated windows and sparse faint architectural "
            "light accents. Keep any ocean or landscape visible. The city is a quiet "
            "secondary backdrop; the interior remains the focal point. No replacement "
            "skyline, oversized new towers, megastructures, new skybridges, elevated transit "
            "bands, giant billboards, flying vehicles or neon-saturated cityscape. "
            "Use believable scale and atmospheric depth, with interior reflections and "
            "exposure consistent with the preserved exterior light. "
            "Render as a high-end architectural photograph with physically plausible "
            "reflections, material texture, upholstery stitching, subtle surface "
            "imperfections, grounded furnishings and controlled exposure. Balance luminous "
            "accents with ambient and task lighting so materials remain readable. "
            "Avoid excessive bloom, uniformly glowing outlines, floating furniture, "
            "oversized holograms, dystopian grime, exposed wire clutter, robots, weapons, "
            "plastic CGI surfaces and changes to the room's structural layout."
        ),
        "variants": {
            "Liquid chrome": (
                "Continuous fluid polished-chrome outer shells wrap around deeply inset "
                "ivory upholstery; use capsule-like curves and substantial sculpted "
                "pedestal bases with narrow recessed luminous seams. Smoked glass and "
                "soft rose and cyan reflections complete the interior palette."
            ),
            "Integrated tech luxury": (
                "Broad low profiles in pearl composite, brushed aluminum and smoked "
                "glass, with recessed upholstery, layered plinth bases and integrated "
                "touch surfaces. Architectural amber light channels meet ice-blue "
                "interface accents. Keep the interior relatively bright and open."
            ),
            "Industrial penthouse": (
                "Layered brushed-titanium frames, charcoal upholstery, substantial "
                "platform bases, visible precision joints and ribbed metal detailing. "
                "Coral and turquoise light is recessed into structural channels. "
                "Moody but readable interior shadows, tactile fabric and credible "
                "machined surfaces."
            ),
            "Angular future noir": (
                "Faceted black-chrome chassis, tailored silver-gray upholstery, "
                "cantilevered surfaces with visible structural support, and sharply "
                "folded metallic profiles. Restrained violet and cool-white lighting "
                "reveals material edges while preserving comfortable ambient exposure."
            ),
            "Original warm luxury": (
                "Return to the original soft, warm futuristic penthouse look: ivory, "
                "cream, champagne, taupe and warm gray; generously rounded plush "
                "upholstery, softly curved low profiles and plump tailored cushions. "
                "Use polished white marble with subtle gray veining, reflective stone, "
                "smoked or mirrored glass and polished chrome in room-appropriate "
                "furnishings. Keep metal trim slender and the upholstered forms soft, "
                "without heavy exoskeleton shells or industrial chassis. On an existing "
                "feature wall, use elegant backlit marble panels, slim mirrored shelving "
                "and a low floating console only where space and the room's function "
                "allow. Warm golden cove and shelf lighting dominates, with thin "
                "controlled cyan and violet accents beneath selected furnishings and "
                "along existing ceiling edges. A concentric-ring light may replace an "
                "existing ceiling fixture only if it fits the existing ceiling shape "
                "and fixture position. Keep any decor sparse and coordinated, with at "
                "most one understated plant or branch arrangement. Inviting, polished "
                "and subtly futuristic, with no large display walls."
            ),
            "Pearl and jewel chrome": (
                "Pearl-ivory upholstered forms wrapped in slender polished-chrome or "
                "champagne-metal frames, with softly rounded corners and comfortable "
                "tailored cushions. Add a few deep emerald and amethyst textile accents "
                "appropriate to the room, plus one quiet geometric rug where suitable. "
                "Use glossy pearl wall panels fitted to existing surfaces, precise "
                "metallic seams and sparse hairline cyan and violet light channels. "
                "A slim metal-framed stone or glass table and chrome-edged supporting "
                "pieces carry the design. Where suitable clear wall space exists, "
                "include one flush smoked-glass interface panel with faint abstract "
                "graphics; it must not cover or replace a window, door or mirror. "
                "Existing ceiling geometry may receive restrained angular light "
                "details. Keep the room luminous, refined and residential."
            ),
        },
    },
}

# Rotation is process-local; saved staging records retain their chosen variant on retry.
_VARIANT_BAGS: dict[str, list[str]] = {}
_LAST_VARIANTS: dict[str, str] = {}
_VARIANT_LOCK = Lock()


def select_variant(style: str) -> str:
    """Shuffle each style's directions once per cycle, without a boundary repeat."""
    style = style if style in STYLE_PRESETS else "modern-luxury"
    with _VARIANT_LOCK:
        bag = _VARIANT_BAGS.setdefault(style, [])
        if not bag:
            bag.extend(STYLE_PRESETS[style]["variants"])
            random.shuffle(bag)
            if len(bag) > 1 and bag[-1] == _LAST_VARIANTS.get(style):
                bag[0], bag[-1] = bag[-1], bag[0]
        variant = bag.pop()
        _LAST_VARIANTS[style] = variant
        return variant


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
    "surface treatments and subtle facade-lighting refinements are intentional; retain "
    "the recognizable existing skyline and keep its changes understated. Keep openings "
    "recognizable and walkways clear. No people, text, logos or personal photographs."
)

ROOM_GUIDANCE = {
    "living": "Furnish as a living room: include a comfortable sofa as the primary seating, plus a coffee table and rug where space allows. If only one seating piece fits, prioritize the sofa over a chair, bench or ottoman.",
    "bedroom": "Furnish as a bedroom, with an appropriately sized bed and bedside pieces where space allows.",
    "dining": "Furnish as a dining room, with an appropriately sized dining table and chairs where space allows.",
    "office": "Furnish as an office, with an appropriately sized desk and chair where space allows.",
    "terrace": "Furnish as a terrace with appropriately scaled outdoor seating where space allows.",
}

CYBERPUNK_ROOM_GUIDANCE = {
    "living": (
        "Furnish as a living room with a comfortable sofa whose silhouette and "
        "construction follow the selected direction: plush rounded upholstered forms "
        "for the softer luxury directions, or sculpted shells around recessed "
        "upholstery for the more technical directions. Use carefully controlled "
        "integrated light only where the direction calls for it. Coordinate a low coffee table "
        "and any accent chair with this design, giving each its own silhouette."
    ),
    "bedroom": (
        "Furnish as a bedroom with a bed and headboard following the selected direction: "
        "a softly upholstered low platform and padded headboard for the softer luxury "
        "directions, or a layered engineered frame and architectural headboard for the "
        "more technical directions. Use discreet bedside controls and restrained light. "
        "Keep bedding soft, tactile and believable. Add bedside units only "
        "where space allows."
    ),
    "dining": "Furnish as a dining room with a dining table and comfortable chairs whose frames, upholstery and silhouettes follow the selected cyberpunk direction.",
    "office": "Furnish as an office with a desk and ergonomic task chair whose construction follows the selected cyberpunk direction, with discreet integrated controls.",
    "terrace": "Furnish as a terrace with weather-resistant engineered outdoor seating and a grounded sculptural table in the selected cyberpunk direction.",
    "kitchen": "Keep this a functional kitchen. Preserve the count, positions and sizes of cabinets, appliances, sinks and openings. Apply futuristic materials, flush controls and task lighting to existing surfaces without blocking access or adding unrelated furniture.",
    "bathroom": "Keep this a functional bathroom. Preserve the positions and sizes of the vanity, basin, toilet, bath or shower, mirrors and openings. Apply futuristic materials, discreet controls and integrated light to existing fixtures without adding unrelated furniture.",
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


def prompt_for(style: str, room: dict[str, Any] | None = None, *,
               variant: str | None = None) -> str:
    style = style if style in STYLE_PRESETS else "modern-luxury"
    preset = STYLE_PRESETS[style]
    room = room or {}
    saved = room.get("staging") or {}
    if variant is None and saved.get("style") == style:
        variant = saved.get("variant")
    if variant not in preset["variants"]:
        variant = select_variant(style)
    direction = f"Design direction: {variant}. {preset['variants'][variant]}"
    guidance = ROOM_GUIDANCE.get(room.get("type"),
        "Choose furnishings appropriate to the room's apparent function; if uncertain, "
        "keep the staging neutral and do not impose a new function.")
    if style == "2142":
        guidance = CYBERPUNK_ROOM_GUIDANCE.get(room.get("type"), guidance)
    rules = FANTASY_RULES if style == "2142" else GEOMETRY_RULES
    wet_note = "" if style == "2142" else _wet_room_note(room)
    return " ".join(part for part in (preset["description"], direction, guidance, rules, wet_note) if part)


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
    style = style if style in STYLE_PRESETS else "modern-luxury"
    preset = STYLE_PRESETS[style]
    saved = room.get("staging") or {}
    variant = saved.get("variant") if saved.get("style") == style else None
    if variant not in preset["variants"]:
        # Legacy staging has no variant metadata; its retries still need stable cache keys.
        variant = next(iter(preset["variants"]))
    counts = _structure_counts(frame)
    if style == "2142":
        return " ".join(part for part in (prompt_for(style, room, variant=variant), STRICT_FRAMING, counts) if part)
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
                        (head, f"Design direction: {variant}. {preset['variants'][variant]}",
                         GEOMETRY_RULES, STRICT_FRAMING, STRICT_STRUCTURE, counts)
                        if part)
    head = f"{prompt_for(style, room, variant=variant)} {STRICT_FRAMING} {STRICT_STRUCTURE}"
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
        variant = select_variant(style)
        prompt = prompt_for(style, room, variant=variant)
        record = {"model": getattr(meta, "image_model", None), "prompt": prompt,
                  "style": style, "variant": variant, "error": None}
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
        "variant": (previous_staging or {}).get("variant") or next(iter(
            STYLE_PRESETS.get(style, STYLE_PRESETS["modern-luxury"])["variants"])),
        "error": None,
        "level": level,
        "purpose": "image.restage",
        "at": _now(),
    }
    room.pop("restage_error", None)
    return None
