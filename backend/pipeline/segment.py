"""Rooms from frames.

Stage 0 placeholder: evenly spaced frames become unclassified spaces.
Stage 1: SAM 3.1 segments each frame, Wonder classifies room type and orders the walkthrough.
"""

from typing import Any

import config


def _evenly_spaced(items: list[str], count: int) -> list[str]:
    if len(items) <= count:
        return items
    step = (len(items) - 1) / (count - 1)
    return [items[round(i * step)] for i in range(count)]


def group_rooms(listing: dict[str, Any]) -> dict[str, Any]:
    picks = _evenly_spaced(listing["frames"], config.settings.max_rooms)
    listing["rooms"] = [
        {
            "id": f"room_{n}",
            "name": f"Space {n}",
            "type": "unclassified",
            "source_frame": frame,
            "before": frame,
            "after": None,
            "style": None,
            "rejected": False,
        }
        for n, frame in enumerate(picks, start=1)
    ]
    return listing
