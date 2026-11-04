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
            "Restyle this room as an ultra-luxury modern interior, staged to the standard "
            "of a landmark penthouse or a five-star private residence. Use a few large, "
            "bespoke, atelier-made furnishings suited to the room's function, with "
            "exceptional proportions, hand-finished joinery, couture-grade upholstery "
            "and museum-quality materials. Every surface should read as rare and "
            "expensive: book-matched stone, hand-rubbed metal, dense natural fibres and "
            "flawless tailoring. Follow the selected design direction for silhouettes, "
            "materials and colors. Ground the main arrangement with one large hand-knotted "
            "tonal rug where appropriate. Include at most one sculptural accent chair or "
            "statement floor lamp where space allows. Use the source lighting direction "
            "with soft, layered, gallery-like light and realistic shadows that give the "
            "furniture weight. No small decor: no vases, books, throws, plants, dried "
            "stems or countertop ornaments. Preserve generous open floor and long "
            "sightlines; the result should feel calm, rare and effortlessly expensive."
        ),
        "variants": {
            "Travertine and boucle": "Warm ivory boucle, book-matched honed travertine and hand-polished champagne bronze; generous rounded upholstery with plump sculpted cushions and softly carved monolithic stone profiles.",
            "Walnut atelier": "Book-matched figured walnut, hand-stitched cognac saddle leather and brushed bronze with cashmere-soft neutral textiles; precisely tailored low rectilinear upholstery on slender, hand-finished timber frames.",
            "Calacatta gallery": "Calacatta marble with soft gold veining, dove-gray sculpted mohair and satin nickel; broad monolithic stone profiles balanced with precisely curved, deeply cushioned upholstery.",
            "Smoked bronze salon": "Smoked bronze glass, ivory silk-velvet and champagne metal; sleek low horizontal forms on slender polished supports, with one restrained deep sapphire textile accent.",
        },
    },
    "coastal": {
        "label": "Coastal",
        "description": (
            "Restyle this room as an ultra-luxury coastal interior in an exclusive "
            "oceanfront estate, the standard of a private clifftop villa on the Riviera "
            "or in Malibu. Use a few generous, bespoke furnishings suited to the room's "
            "function, with relaxed but impeccable tailoring and hand-finished detail. "
            "Follow the selected design direction for silhouettes, wood tones, textiles "
            "and stone. Favor rare natural materials: heavyweight Belgian linen, "
            "hand-woven fibres, oiled hardwoods and honed natural stone. Use one large "
            "hand-loomed natural-fibre or tonal rug where appropriate. Work with the "
            "source daylight and existing light direction for a luminous, sun-washed, "
            "serene photographic result. Keep floor space generous and sightlines long. "
            "Avoid nautical motifs, beach-themed decor, rustic or distressed finishes, "
            "clutter and small decorative objects."
        ),
        "variants": {
            "Riviera villa": "Chalk-white Belgian linen, pale oiled oak and cream limestone; softly rounded deep-seated upholstery, carved stone tables and fine hand-woven textures. Echo plaster tones in the furnishings without changing existing walls.",
            "Malibu glass house": "Tailored ivory linen, bleached ash and pale honed quartzite; crisp low horizontal furnishings with slim open frames and one restrained muted ocean-blue accent.",
            "Sun-bleached teak estate": "Sun-bleached plantation teak, oatmeal linen and warm sand hand-woven fibre; generous relaxed forms with precise joinery and open woven accent frames, polished and refined, never rustic.",
            "Sea glass residence": "Cool off-white cotton-silk, light natural oak, pale coastal stone and restrained sea-glass green; gently curved upholstery and hand-blown glass details, no literal shells or seaside ornaments.",
        },
    },
    "minimal": {
        "label": "Minimal",
        "description": (
            "Restyle this room as an ultra-luxury, museum-quiet minimal interior, the "
            "kind of serene private residence where every piece is a bespoke object and "
            "earns its place. Use only the essential functional furnishings for this room, "
            "with purposeful sculptural forms, rare materials, invisible joinery and "
            "precise proportions. Minimal does not mean unfurnished: include the main "
            "furniture required by the room-specific guidance. Follow the selected design "
            "direction rather than defaulting every room to ivory. Use one understated "
            "hand-loomed tonal rug where appropriate. Preserve the source lighting "
            "direction with soft, diffused light and realistic shadows revealing form. "
            "Maintain generous negative space, clean sightlines and a sense of stillness. "
            "Avoid busy patterns, clutter and small decorative objects."
        ),
        "variants": {
            "Warm oak sanctuary": "Quarter-sawn warm oak, oatmeal linen and ivory wool; low clean-lined forms with softly eased corners and flawless natural grain.",
            "Monolithic stone": "Pale honed limestone, chalk-white boucle and soft gray cashmere-weight wool; block-like grounded stone profiles paired with simple, generous upholstery.",
            "Smoked oak stillness": "Smoked oak, warm graphite linen and soft gray wool; precise rectilinear furniture with slim profiles and quiet matte surfaces. Keep the room bright and clearly exposed.",
            "Soft plaster forms": "Hand-troweled plaster-toned furniture, cream upholstery and a single pale ash accent; simple rounded volumes and continuous softly curved profiles. Leave existing wall finishes unchanged.",
        },
    },
    "2142": {
        "label": "Cyberpunk",
        "description": (
            "Restyle this exact room as a pristine ultra-luxury residence in the year "
            "2142: immaculate, high-tech and unmistakably far-future, never retro and "
            "never contemporary. Furniture must look designed in 2142, not 2026: "
            "seamless monocoque forms with no visible legs, screws or seams, grown "
            "or printed as single sculptural pieces; programmable smart-knit and "
            "self-healing upholstery; liquid-metal and pearl-ceramic shells; "
            "photochromic glass; and slim magnetic plinths so key pieces appear to hover "
            "a few centimetres above the floor on a soft halo of light while still "
            "casting a grounded contact shadow. Apply the selected design direction "
            "consistently to furniture forms, materials, upholstery, lighting colors and "
            "architectural details. Integrate technology invisibly into selected wall "
            "panels, furnishings and existing architectural edges: flush light seams, "
            "touch-reactive surfaces and, where the direction calls for it, one "
            "translucent interface surface with abstract graphics and no readable text. "
            "Every surface is spotless, precise and flawlessly finished. "
            "Keep any door opening and frame exactly in place; futuristic sliding privacy "
            "panels must remain recognizable as doors. Any redesigned ceiling fixture "
            "must occupy the existing fixture's position. Preserve comfortable usable "
            "space and clear circulation paths. "
            "Through the existing windows, show the exterior view described by the "
            "selected design direction, keeping window frames and the view's perspective "
            "intact; the city is breathtaking but the interior remains the focal point. "
            "Render as a high-end architectural photograph with physically plausible "
            "reflections, rich material texture, precise upholstery detail and controlled "
            "exposure. Balance luminous accents with bright ambient light so materials "
            "remain readable. The mood is bright, clean, optimistic and serene. Avoid "
            "dark, moody or gritty atmospheres, rain-soaked streets, neon signage, "
            "billboards, grime, graffiti, exposed wiring, carbon fiber, industrial "
            "hardware, robots, weapons, oversized holograms, excessive bloom, plastic CGI "
            "surfaces and changes to the room's structural layout."
        ),
        "variants": {
            "Champagne halo": (
                "Warm ivory, cream, champagne and soft pearl-taupe. Main upholstered "
                "pieces are single seamless crescent-curved monocoques in ivory "
                "smart-knit, with deep self-shaping cushions flowing out of one "
                "continuous shell, hovering on polished champagne-metal halo plinths "
                "with warm light beneath. Tables are low liquid-champagne forms that "
                "rise like polished droplets from the floor. Backlit translucent white onyx panels and a "
                "floating cantilevered console on an existing feature wall where space "
                "allows. Warm golden cove light dominates, with hairline ice-blue and "
                "soft violet light seams along existing ceiling edges. Exterior view: "
                "replace the view with a pristine 2142 megacity at blue hour, with "
                "slender luminous white and glass supertall towers, sky gardens and "
                "softly glowing skybridges under a deep sapphire sky, and exactly one "
                "sleek silent flying vehicle gliding in the distance."
            ),
            "Pearl atrium": (
                "Luminous pearl-white, opal and brushed platinum with a few deep "
                "emerald and amethyst textile accents. Furnishings are flowing "
                "pearl-ceramic shells wrapped around plush pearl smart-knit upholstery, "
                "with platinum hairline seams and softly rounded edges; tables are "
                "single pieces of milky photochromic glass on slim levitating plinths. "
                "Glossy pearl wall panels fitted to existing surfaces, with sparse "
                "hairline cyan light channels and, where clear wall space exists, one "
                "flush translucent interface panel with faint abstract graphics that "
                "never covers a window, door or mirror. Bright, airy, gallery-white "
                "interior. Exterior view: keep the real view's horizon, terrain, water "
                "and the layout, spacing and scale of its buildings, but rebuild every "
                "visible building as an immaculate 2142 version with white ceramic and "
                "glass facades, vertical gardens and fine light lines, in bright clear "
                "daylight under a crisp blue sky. No flying vehicles."
            ),
            "Liquid chrome": (
                "Mirror-polished liquid chrome, white silk-velvet and ice-blue light. "
                "Furnishings are continuous fluid chrome shells that look poured rather "
                "than built, cradling deeply inset white silk-velvet upholstery, with "
                "capsule-like curves and narrow recessed ice-blue luminous seams; key "
                "pieces hover on mirrored plinths with cool light beneath. Smoked-glass "
                "and pale silver surfaces reflect soft ice-blue and rose highlights. "
                "Interior stays bright and clean, never dark. Exterior view: keep the "
                "real view's horizon, terrain, water and the layout, spacing and scale "
                "of its buildings, but rebuild every visible building as a gleaming 2142 "
                "tower of mirrored glass and white light ribbons at blue hour, with "
                "exactly one sleek silent flying vehicle gliding in the distance."
            ),
            "Glacier glass": (
                "Arctic white, frosted crystal, brushed aluminum and pale ice-blue with "
                "warm amber light channels. Furnishings are low, broad sculptural forms "
                "in frosted crystal-ceramic and soft white smart-knit, with integrated "
                "touch surfaces and edges that glow faintly when touched; tables are "
                "slabs of clear glacier glass with light suspended inside. Flush white "
                "wall panels with precise light seams. Brilliant, crisp, high-key "
                "interior. Exterior view: replace the view with a pristine 2142 "
                "megacity in bright clear daylight, with elegant white and glass "
                "supertall towers, terraced sky gardens, silent maglev lines and "
                "luminous clean air. No flying vehicles."
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
    "surface treatments and the exterior view described in the design direction are "
    "intentional. Keep window frames and openings recognizable and walkways clear. "
    "No people, text, logos or personal photographs."
)

ROOM_GUIDANCE = {
    "living": "Furnish as a living room: include a comfortable sofa as the primary seating, plus a coffee table and rug where space allows. If only one seating piece fits, prioritize the sofa over a chair, bench or ottoman.",
    "bedroom": "Furnish as a bedroom, with an appropriately sized bed and bedside pieces where space allows.",
    "dining": "Furnish as a dining room, with an appropriately sized dining table and chairs where space allows.",
    "office": "Furnish as an office, with an appropriately sized desk and chair where space allows.",
    "terrace": "Furnish as a terrace with appropriately scaled outdoor seating where space allows.",
}

OUTDOOR_NOTE = (
    "If a balcony, terrace or patio floor is visible in the photo, furnish it too with a few "
    "appropriately scaled outdoor pieces in the same style, such as a pair of loungers or "
    "outdoor seating; keep railings, glass and the view unobstructed."
)

CYBERPUNK_ROOM_GUIDANCE = {
    "living": (
        "Furnish as a living room with a comfortable 2142 sofa as the primary seating, "
        "built as one seamless sculptural form following the selected direction, with "
        "no conventional legs, frame or visible hardware. Coordinate a low coffee "
        "table and any accent chair with this design, giving each its own silhouette."
    ),
    "bedroom": (
        "Furnish as a bedroom with a 2142 bed following the selected direction: a "
        "seamless low platform that appears to hover on a soft halo of light, with an "
        "integrated sculptural headboard and discreet touch controls. Keep bedding "
        "soft, tactile and immaculate. Add floating bedside units only where space "
        "allows."
    ),
    "dining": "Furnish as a dining room with a seamless sculptural dining table and comfortable chairs whose shells, upholstery and silhouettes follow the selected 2142 direction.",
    "office": "Furnish as an office with a seamless sculptural desk and ergonomic task chair following the selected 2142 direction, with invisible integrated controls.",
    "terrace": "Furnish as a terrace with immaculate weather-proof 2142 outdoor seating and a sculptural table in the selected direction.",
    "kitchen": "Keep this a functional kitchen. Preserve the count, positions and sizes of cabinets, appliances, sinks and openings. Apply pristine 2142 materials, flush touch controls and integrated task lighting to existing surfaces without blocking access or adding unrelated furniture.",
    "bathroom": "Keep this a functional bathroom. Preserve the positions and sizes of the vanity, basin, toilet, bath or shower, mirrors and openings. Apply pristine 2142 materials, discreet touch controls and integrated light to existing fixtures without adding unrelated furniture.",
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
    fantasy = style == "2142"
    if fantasy:
        guidance = CYBERPUNK_ROOM_GUIDANCE.get(room.get("type"), guidance)
    rules = FANTASY_RULES if fantasy else GEOMETRY_RULES
    wet_note = "" if fantasy else _wet_room_note(room)
    outdoor = "" if fantasy or room.get("type") in WET_ROOM_TYPES else OUTDOOR_NOTE
    return " ".join(part for part in (preset["description"], direction, guidance, outdoor, rules, wet_note) if part)


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
    else a short error message; the room keeps its current staging on failure.
    Level 0 is a broker room-type change: the normal prompt for the new type."""
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
    prompt = restage_prompt(style, room, frame, level) if level else prompt_for(style, room)
    filename = f"{room_id}_{style}_strict{level}.jpg" if level else f"{room_id}_{style}_{room['type']}.jpg"
    meta = meta_client.get_client()
    previous_staging = room.get("staging")
    previous_after = room.get("after")
    try:
        _staged_image(
            listing, room, prompt, filename,
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
