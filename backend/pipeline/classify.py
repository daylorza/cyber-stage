"""Rooms from Wonder's multimodal classification, over blurred frames only.

Only frames that survived the privacy pass (frame.path set) are sent to the API —
unblurred pixels never leave the box. Wonder returns per-frame room keys, types
and observations; frames group into rooms in walkthrough (video) order, with the
sharpest well-covered frame as the hero (before image).

A long walkthrough is classified in batches of up to MAX_CLASSIFY_FRAMES frames, each
batch told which room keys earlier frames used, so every frame of the video is read.

The main living space is the hero room. Utility rooms (bathrooms, laundry, other) are
secondary: when the room cap bites they are dropped first, and the main living room is
always kept.
"""

import math
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
# The main living space, in order of preference.
MAIN_TYPES = ("living", "dining")
# Rooms a buyer lives in. Everything else (bathroom, other/laundry, exterior, unclassified)
# is a utility room: secondary, never the hero, never the demo.
PRIMARY_TYPES = {"living", "kitchen", "dining", "bedroom", "office", "terrace"}
HERO_MIN_SHARPNESS = 0.6


def is_utility(room: dict[str, Any]) -> bool:
    return room.get("type") not in PRIMARY_TYPES


def _clock(t: float | None) -> str:
    if t is None:
        return "photo"
    s = max(0, round(t))
    return f"{s // 60}:{s % 60:02d}"


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
            "t": frame.get("t"),
            "span": [frame.get("t"), frame.get("t")],
            "upload": frame.get("upload"),
            "main": False,
        }
        for n, frame in enumerate(picks, start=1)
    ]
    listing["main_room"] = _main_summary(None)


def _batches(frames: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not frames:
        return [[]]  # still one call, so an unconfigured client fails loudly as before
    count = math.ceil(len(frames) / meta_client.MAX_CLASSIFY_FRAMES)
    size = math.ceil(len(frames) / count)
    return [frames[i:i + size] for i in range(0, len(frames), size)]


def _known_rooms(entries: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]) -> str:
    seen: dict[str, dict[str, Any]] = {}
    for entry in entries:
        frame = by_id.get(entry.get("frame"))
        key = entry.get("room_key")
        if frame is None or not key:
            continue
        info = seen.setdefault(key, {"type": entry.get("room_type") or "other", "ts": []})
        info["ts"].append(frame.get("t"))
    parts = []
    for key, info in seen.items():
        ts = [t for t in info["ts"] if t is not None]
        span = f"{_clock(min(ts))}-{_clock(max(ts))}" if ts else "photos"
        parts.append(f"{key} ({info['type']}, {span})")
    return "; ".join(parts)


def _classify(listing: dict[str, Any], usable: list[dict[str, Any]]) -> list[dict[str, Any]]:
    s = config.settings
    meta = meta_client.get_client()
    by_id = {f["id"]: f for f in usable}
    batches = _batches(usable)
    entries: list[dict[str, Any]] = []
    for index, batch in enumerate(batches, start=1):
        result = meta.wonder_classify(
            [{"id": f["id"], "t": f["t"], "path": str(s.media_dir / f["path"])} for f in batch],
            known_rooms=_known_rooms(entries, by_id),
            trace=listing.setdefault("trace", []),
            purpose="wonder.classify",
            target={"frames": len(batch), "batch": f"{index}/{len(batches)}"},
        )
        batch_ids = {f["id"] for f in batch}
        entries.extend(e for e in result.get("frames") or [] if e.get("frame") in batch_ids)
    return entries


def _main_room(rooms: list[dict[str, Any]], frames_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for room_type in MAIN_TYPES:
        candidates = [r for r in rooms if r["type"] == room_type]
        if candidates:
            def weight(r: dict[str, Any]) -> tuple[int, float]:
                coverage = sum((frames_by_id[f]["wonder"] or {}).get("coverage", 0) for f in r["frames"])
                return len(r["frames"]), coverage
            return max(candidates, key=weight)
    return None


def _main_summary(room: dict[str, Any] | None) -> dict[str, Any]:
    if room is None:
        return {"room": None, "found": False,
                "detail": "No main living space found in this video. Staging is held so no Meta calls "
                          "are spent on bathrooms, laundry or door close-ups."}
    span = room.get("span") or [None, None]
    when = (f"hero {room['source_frame']} at {_clock(room.get('t'))}, "
            f"{len(room['frames'])} frames {_clock(span[0])}–{_clock(span[1])}")
    return {"room": room["id"], "found": True, "type": room["type"], "name": room["name"],
            "source_frame": room["source_frame"], "t": room.get("t"), "span": span,
            "detail": f"{room['name']} confirmed as the main living space · {when}"}


def run(listing: dict[str, Any]) -> dict[str, Any]:
    s = config.settings
    usable = [f for f in listing["frames"] if f.get("path")]
    try:
        entries = _classify(listing, usable)
    except meta_client.MetaError as exc:
        _fallback(listing)
        checklist.set_item(listing, "wonder_classification", "failed", str(exc))
        return listing

    by_id = {f["id"]: f for f in usable}
    for entry in entries:
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

    # Frames are in video order, so first appearance gives walkthrough order.
    position = {f["id"]: i for i, f in enumerate(usable)}
    groups: dict[str, list[dict[str, Any]]] = {}
    for frame in usable:
        if frame.get("wonder"):
            groups.setdefault(frame["wonder"]["room_key"], []).append(frame)

    candidates: list[dict[str, Any]] = []
    for members in groups.values():
        members = [
            f for f in members
            if f["wonder"]["usable"] and f["wonder"]["room_type"] not in SKIP_TYPES
        ]
        if not members:
            continue
        # Hero: the frame that shows the most of the room, among frames at least 60% as sharp as
        # the sharpest (so a blurry wide shot never wins). Coverage is what staging needs: open floor.
        max_sharp = max((f["sharpness"] or 0) for f in members) or 1
        sharp = [f for f in members if (f["sharpness"] or 0) >= HERO_MIN_SHARPNESS * max_sharp] or members
        hero = max(sharp, key=lambda f: (f["wonder"]["coverage"], (f["sharpness"] or 0)))
        # The room's segment of the video: the unbroken run of its frames around the hero.
        ids = {f["id"] for f in members}
        lo = hi = position[hero["id"]]
        while lo > 0 and usable[lo - 1]["id"] in ids:
            lo -= 1
        while hi < len(usable) - 1 and usable[hi + 1]["id"] in ids:
            hi += 1
        candidates.append({
            "name": "",
            "type": hero["wonder"]["room_type"],
            "source_frame": hero["id"],
            "before": hero["path"],
            "after": None,
            "style": None,
            "frames": [f["id"] for f in members],
            "hero_reason": (f"widest view of {len(members)} frames (coverage {hero['wonder']['coverage']:.2g}, "
                            f"sharpness {round((hero['sharpness'] or 0) / max_sharp * 100)}% of the sharpest)"),
            "staging": None,
            "rejected": False,
            "t": hero["t"],
            "span": [usable[lo]["t"], usable[hi]["t"]],
            "upload": hero["upload"],
            "main": False,
        })

    main = _main_room(candidates, by_id)
    if main is not None:
        main["main"] = True
    if len(candidates) > s.max_rooms:
        rank = {id(r): (0 if r is main else 1 if not is_utility(r) else 2, i) for i, r in enumerate(candidates)}
        keep = {id(r) for r in sorted(candidates, key=lambda r: rank[id(r)])[:s.max_rooms]}
        candidates = [r for r in candidates if id(r) in keep]

    name_counts: dict[str, int] = {}
    rooms: list[dict[str, Any]] = []
    for room in candidates:
        name_counts[room["type"]] = name_counts.get(room["type"], 0) + 1
        base = ROOM_NAMES.get(room["type"], "Space")
        name = base if name_counts[room["type"]] == 1 else f"{base} {name_counts[room['type']]}"
        rooms.append({"id": f"room_{len(rooms) + 1}", **room, "name": name})

    listing["rooms"] = rooms
    listing["main_room"] = _main_summary(next((r for r in rooms if r["main"]), None))
    batches = len(_batches(usable))
    checklist.set_item(
        listing, "wonder_classification", "generated",
        f"{len(usable)} frames classified in {batches} call(s), {len(rooms)} rooms"
        + ("" if main else " · no main living space found"),
    )
    return listing
