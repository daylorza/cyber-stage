"""Virtual staging.

Stage 1: Muse Image, image-to-image from each room's source frame, geometry preserved, with the
buyer-chosen style preset. Every staged image keeps `source_frame` for the before/after toggle.
Stage 0 leaves `after` empty so the review UI shows staging as pending.
"""

from typing import Any


def stage_rooms(listing: dict[str, Any]) -> dict[str, Any]:
    return listing
