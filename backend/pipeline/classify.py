"""Rooms from Wonder's multimodal classification, over blurred frames only.

Only frames that survived the privacy pass (frame.path set) are sent to the API —
unblurred pixels never leave the box. Wonder returns per-frame room keys, types
and observations; frames group into rooms in walkthrough order, with the sharpest
well-covered frame as the hero (before image).
"""

from typing import Any

import checklist
import config
import meta_client

ROOM_NAMES = {
    "living": "Living room",
    "kitchen": "Kitchen",
    "dining": "Dining room",
    "bedroom": "Bedroom",
    "bathroom": "Bathroom",
    "office": "Office",
    "terrace": "Terrace",
    "exterior": "Exterior",
    "other": "Space",
}
SKIP_TYPES = {"hallway", "closet"}


def _evenly_spaced(items: list[Any], count: int) -> list[Any]:
    if len(items) <= count:
        return items
    step = (len(items) - 1) / (count - 1)
    return [items[round(i * step)] for i in range(count)]


def _fallback(listing: dict[str, Any]) -> None:
    """Stage 0 behavior: evenly spaced frames become unclassified spaces."""
    usable = [f for f in listing["frames"] if f.get("path")] or listing["frames"]
    picks = _evenly_spaced(usable, config.settings.max_rooms)
    listing["rooms"] = [
        {
            "id": f"room_{n}",
            "name": f"Space {n}",
            "type": "unclassified",
            "source_frame": frame["id"],
            "before": frame.get("path"),
            "after": None,
            "style": None,
            "frames": [frame["id"]],
            "hero_reason": "evenly spaced fallback",
            "staging": None,
            "rejected": False,
        }
        for n, frame in enumerate(picks, start=1)
    ]


def run(listing: dict[str, Any]) -> dict[str, Any]:
    s = config.settings
    meta = meta_client.get_client()
    usable = [f for f in listing["frames"] if f.get("path")]
    try:
        result = meta.wonder_classify(
            [{"id": f["id"], "t": f["t"], "path": str(s.media_dir / f["path"])} for f in usable],
            trace=listing.setdefault("trace", []),
            purpose="wonder.classify",
            target={"frames": len(usable)},
        )
    except meta_client.MetaError as exc:
        _fallback(listing)
        checklist.set_item(listing, "wonder_classification", "failed", str(exc))
        return listing

    by_id = {f["id"]: f for f in usable}
    for entry in result.get("frames") or []:
        frame = by_id.get(entry.get("frame"))
        if frame is None:
            continue
        observations = [
            {"id": f"o_{frame['id']}_{i}", "text": str(text)}
            for i, text in enumerate(entry.get("observations") or [], start=1)
        ][:6]
        frame["wonder"] = {
            "room_key": entry.get("room_key") or frame["id"],
            "room_type": entry.get("room_type") or "other",
            "usable": bool(entry.get("usable", True)),
            "coverage": float(entry.get("coverage") or 0),
            "observations": observations,
            "condition": str(entry.get("condition") or ""),
        }

    groups: dict[str, list[dict[str, Any]]] = {}
    for frame in usable:
        if frame.get("wonder"):
            groups.setdefault(frame["wonder"]["room_key"], []).append(frame)
    order = [key for key in (result.get("order") or []) if key in groups]
    order += [key for key in groups if key not in order]

    rooms: list[dict[str, Any]] = []
    name_counts: dict[str, int] = {}
    for key in order:
        members = [
            f for f in groups[key]
            if f["wonder"]["usable"] and f["wonder"]["room_type"] not in SKIP_TYPES
        ]
        if not members:
            continue
        max_sharp = max((f["sharpness"] or 0) for f in members) or 1
        hero = max(
            members,
            key=lambda f: (f["sharpness"] or 0) / max_sharp * 0.5 + f["wonder"]["coverage"] * 0.5,
        )
        room_type = hero["wonder"]["room_type"]
        name_counts[room_type] = name_counts.get(room_type, 0) + 1
        base = ROOM_NAMES.get(room_type, "Space")
        name = base if name_counts[room_type] == 1 else f"{base} {name_counts[room_type]}"
        rooms.append({
            "id": f"room_{len(rooms) + 1}",
            "name": name,
            "type": room_type,
            "source_frame": hero["id"],
            "before": hero["path"],
            "after": None,
            "style": None,
            "frames": [f["id"] for f in members],
            "hero_reason": f"sharpest of {len(members)} frames, coverage {hero['wonder']['coverage']:.2g}",
            "staging": None,
            "rejected": False,
        })
        if len(rooms) >= s.max_rooms:
            break

    listing["rooms"] = rooms
    checklist.set_item(
        listing, "wonder_classification", "generated",
        f"{len(usable)} frames classified, {len(rooms)} rooms",
    )
    return listing
