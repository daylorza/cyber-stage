"""Stage 1 pipeline checklist, generated at job start.

Every item must reach "done" before a broker can approve. Statuses:
open -> generated/failed (generator writes) -> done/flagged (verifier reconciles).
"""

from datetime import UTC, datetime
from typing import Any

import config

ITEMS: list[tuple[str, str]] = [
    ("frames", "Frames extracted"),
    ("sam_masks", "SAM 3.1 masks"),
    ("wonder_classification", "Wonder room classification"),
    ("staging_geometry", "Staging geometry preserved"),
    ("claim_evidence", "Every claim has evidence"),
    ("comps_demo", "Comps labeled demo"),
    ("blur_pass", "Faces and personal items blurred"),
]

LEGACY_DETAIL = "Created before Stage 1. Upload the walkthrough again."


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_checklist(detail: str = "") -> dict[str, Any]:
    return {
        "created_at": _now(),
        "items": [
            {"id": item_id, "label": label, "status": "open", "detail": detail, "updated_at": _now()}
            for item_id, label in ITEMS
        ],
    }


def get_item(listing: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for item in (listing.get("checklist") or {}).get("items", []):
        if item["id"] == item_id:
            return item
    return None


def set_item(listing: dict[str, Any], item_id: str, status: str, detail: str | None = None) -> None:
    item = get_item(listing, item_id)
    if item is None:
        return
    item["status"] = status
    if detail is not None:
        item["detail"] = detail
    item["updated_at"] = _now()


def blocking(listing: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in (listing.get("checklist") or {}).get("items", [])
        if item["status"] != "done"
    ]


def is_clear(listing: dict[str, Any]) -> bool:
    return not blocking(listing)


def checks_block(listing: dict[str, Any]) -> bool:
    """Open items block Approve/Publish only with VRE_BLOCKING_CHECKS=1. Seeded placeholders
    (no footage) always stay blocked; uploads get warnings only in demo mode."""
    return config.settings.blocking_checks or listing.get("source") != "upload"
