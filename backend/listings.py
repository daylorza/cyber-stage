"""Listing lifecycle: create, seed, broker review, publish.

processing -> draft -> (approved | rejected) -> published, with failed as a terminal pipeline state.
Nothing publishes without a broker approval, and any edit after approval clears it.
"""

import json
from typing import Any

import config
import db
from pipeline import comps, copy

REVIEWABLE = {"draft", "approved", "rejected"}
BROKER_EDIT = {"kind": "broker", "ref": "edited"}


class ReviewError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def new_listing(listing_id: str, *, source: str, facts: dict[str, Any], uploads: list[dict[str, Any]],
                job_id: str | None = None, status: str = "processing") -> dict[str, Any]:
    return {
        "id": listing_id,
        "source": source,
        "status": status,
        "facts": facts,
        "uploads": uploads,
        "frames": [],
        "rooms": [],
        "review": {"decision": None, "decided_at": None, "notes": "", "edited_fields": []},
        "job_id": job_id,
    }


def seed_inventory() -> None:
    entries = json.loads((config.settings.seed_dir / "listings.json").read_text())
    with db.connect() as conn:
        for entry in entries:
            if db.listing_exists(conn, entry["id"]):
                continue
            listing = new_listing(entry["id"], source="seed", facts=entry["facts"], uploads=[], status="draft")
            listing["note"] = entry.get("note")
            db.insert_listing(conn, comps.attach(copy.write(listing)))


def summary(listing: dict[str, Any]) -> dict[str, Any]:
    facts = listing["facts"]
    rooms = listing.get("rooms", [])
    return {
        "id": listing["id"],
        "status": listing["status"],
        "source": listing["source"],
        "title": listing.get("copy", {}).get("title", ""),
        "city": facts.get("city"),
        "price_display": copy.format_price(facts.get("price"), facts.get("currency")),
        "cover": rooms[0]["before"] if rooms else None,
        "rooms": len(rooms),
        "note": listing.get("note"),
        "updated_at": listing["updated_at"],
    }


def _edit_copy(listing: dict[str, Any], edit: dict[str, Any]) -> list[str]:
    current = listing["copy"]
    edited: list[str] = []
    for field in ("title", "description"):
        value = edit[field].strip()
        if value != current[field]:
            current[field] = value
            current["evidence"][field] = [BROKER_EDIT]
            edited.append(field)
    by_text = {h["text"]: h for h in current["highlights"]}
    texts = [t.strip() for t in edit["highlights"] if t.strip()]
    if texts != [h["text"] for h in current["highlights"]]:
        current["highlights"] = [by_text.get(t) or {"text": t, "evidence": [BROKER_EDIT]} for t in texts]
        edited.append("highlights")
    return edited


def _edit_rooms(listing: dict[str, Any], rejected: list[str]) -> list[str]:
    rooms = listing["rooms"]
    unknown = set(rejected) - {r["id"] for r in rooms}
    if unknown:
        raise ReviewError(422, f"Unknown room id(s): {', '.join(sorted(unknown))}.")
    changed = [r["id"] for r in rooms if r["rejected"] != (r["id"] in rejected)]
    for room in rooms:
        room["rejected"] = room["id"] in rejected
    return ["rooms"] if changed else []


def apply_review(listing: dict[str, Any], *, action: str, copy_edit: dict[str, Any] | None = None,
                 rejected_rooms: list[str] | None = None, notes: str | None = None) -> dict[str, Any]:
    if listing["status"] not in REVIEWABLE:
        message = {
            "processing": "The listing is still processing.",
            "published": "Published listings can't be edited.",
            "failed": "Processing failed; upload the walkthrough again.",
        }.get(listing["status"], "This listing can't be reviewed right now.")
        raise ReviewError(409, message)

    review = listing["review"]
    edited = (_edit_copy(listing, copy_edit) if copy_edit is not None else []) + (
        _edit_rooms(listing, rejected_rooms) if rejected_rooms is not None else []
    )
    review["edited_fields"] = sorted(set(review["edited_fields"]) | set(edited))
    if notes is not None:
        review["notes"] = notes.strip()

    if action == "approve":
        if not listing["copy"]["title"]:
            raise ReviewError(422, "Add a title before approving.")
        listing["status"] = "approved"
        review.update(decision="approved", decided_at=db.now())
    elif action == "reject":
        listing["status"] = "rejected"
        review.update(decision="rejected", decided_at=db.now())
    elif edited and listing["status"] == "approved":
        listing["status"] = "draft"
        review.update(decision=None, decided_at=None)
    return listing


def publish(listing: dict[str, Any]) -> dict[str, Any]:
    if listing["status"] != "approved":
        raise ReviewError(409, "Approve the listing before publishing.")
    facts, listing_copy = listing["facts"], listing["copy"]
    published_at = db.now()
    listing["published"] = {
        "id": listing["id"],
        "title": listing_copy["title"],
        "description": listing_copy["description"],
        "highlights": listing_copy["highlights"],
        "facts": {k: v for k, v in facts.items() if k != "estimate_price"},
        "price_display": copy.format_price(facts.get("price"), facts.get("currency")),
        "rooms": [r for r in listing["rooms"] if not r["rejected"]],
        "comps": listing["comps"],
        "approved_at": listing["review"]["decided_at"],
        "published_at": published_at,
    }
    listing.update(status="published", published_at=published_at)
    return listing
