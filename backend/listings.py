"""Listing lifecycle: create, seed, broker review, publish.

processing -> draft -> (approved | rejected) -> published, with failed as a terminal pipeline state.
Nothing publishes without a broker approval, a clear Stage 1 checklist, and a passed
independent verification; any edit after approval clears it.
"""

import json
from typing import Any

import checklist
import config
import db
import verify
from pipeline import comps, copy, video

REVIEWABLE = {"draft", "approved", "rejected"}
BROKER_EDIT = {"kind": "broker", "ref": "edited"}
STYLES = {"modern-luxury", "coastal", "minimal"}
DEFAULT_STYLE = "modern-luxury"
# Shown on the console, the published page and inside Live-In-It for test uploads.
TEST_NOTE = "Test upload · Not a real listing. Placeholder facts."


class ReviewError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def new_listing(listing_id: str, *, source: str, facts: dict[str, Any], uploads: list[dict[str, Any]],
                job_id: str | None = None, status: str = "processing",
                style: str = DEFAULT_STYLE) -> dict[str, Any]:
    return {
        "id": listing_id,
        "source": source,
        "status": status,
        "facts": facts,
        "uploads": uploads,
        "frames": [],
        "rooms": [],
        "style": style,
        "review": {"decision": None, "decided_at": None, "notes": "", "edited_fields": []},
        "job_id": job_id,
    }


def normalize(listing: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a pre-Stage-1 listing in place so every endpoint can read it."""
    frames = listing.get("frames") or []
    if frames and isinstance(frames[0], str):
        listing["frames"] = [
            {"id": f"legacy_{i}", "raw": None, "path": None, "t": None, "upload": 0,
             "width": None, "height": None, "sharpness": None, "sam": None,
             "wonder": None, "blur": None}
            for i, _ in enumerate(frames, start=1)
        ]
    frame_ids = {f["id"] for f in listing.get("frames") or []}
    for room in listing.get("rooms") or []:
        room.setdefault("rejected", False)
        room.setdefault("after", None)
        room.setdefault("style", None)
        room.setdefault("staging", None)
        room.setdefault("hero_reason", "")
        room.setdefault("frames", [])
        if room.get("source_frame") not in frame_ids:
            # Stage 0 rooms pointed at unblurred media paths; do not serve them.
            room["source_frame"] = None
            room["before"] = None
    if "checklist" not in listing:
        listing["checklist"] = checklist.new_checklist(checklist.LEGACY_DETAIL)
    listing.setdefault("verification", None)
    listing.setdefault("trace", [])
    listing.setdefault("style", DEFAULT_STYLE)
    if "copy" in listing:
        listing["copy"].setdefault("sentences", [])
        listing["copy"].setdefault("generator", {"model": None, "note": "Created before Stage 1."})
    return listing


def _untouched_seed(listing: dict[str, Any]) -> bool:
    return listing["status"] == "draft" and not listing["review"]["edited_fields"]


def seed_inventory() -> None:
    """Insert seeded hero listings; refresh ones the broker hasn't touched so seed edits show up,
    and drop untouched seeds that are no longer in the seed file."""
    entries = json.loads((config.settings.seed_dir / "listings.json").read_text())
    seeded = {entry["id"] for entry in entries}
    for stale in db.list_listings():
        if stale["source"] == "seed" and stale["id"] not in seeded and _untouched_seed(stale):
            db.delete_listing(stale["id"])
    for entry in entries:
        existing = db.get_listing(entry["id"])
        if existing and not _untouched_seed(existing):
            continue
        listing = new_listing(entry["id"], source="seed", facts=entry["facts"], uploads=[], status="draft")
        listing["note"] = entry.get("note")
        listing = comps.attach(copy.write_facts(listing))
        listing["checklist"] = checklist.new_checklist()
        checklist.set_item(listing, "frames", "open", "No walkthrough footage yet")
        listing["trace"] = []
        verify.run(listing, meta=False)
        if existing:
            db.save_listing({**listing, "created_at": existing["created_at"]})
        else:
            with db.connect() as conn:
                db.insert_listing(conn, listing)


def summary(listing: dict[str, Any]) -> dict[str, Any]:
    facts = listing["facts"]
    rooms = listing.get("rooms", [])
    return {
        "id": listing["id"],
        "status": listing["status"],
        "source": listing["source"],
        "prototype_test": bool(listing.get("prototype_test")),
        "title": listing.get("copy", {}).get("title", ""),
        "city": facts.get("city"),
        "facts": {k: v for k, v in facts.items() if k != "estimate_price"},
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
            if field == "description":
                current["sentences"] = (
                    [{"id": "c_broker_desc", "text": value, "evidence": [BROKER_EDIT]}] if value else []
                )
            edited.append(field)
    by_text = {h["text"]: h for h in current["highlights"]}
    texts = [t.strip() for t in edit["highlights"] if t.strip()]
    if texts != [h["text"] for h in current["highlights"]]:
        current["highlights"] = [
            by_text.get(t) or {"id": f"c_broker_{i}", "text": t, "evidence": [BROKER_EDIT]}
            for i, t in enumerate(texts, start=1)
        ]
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


def set_test_label(listing: dict[str, Any], test: bool) -> None:
    """Label (or unlabel) an upload as a test: "Not a real listing" everywhere it shows.
    A label, not content: it never clears an approval."""
    if listing.get("source") != "upload":
        return
    if test:
        listing["note"] = TEST_NOTE
    elif listing.get("note") == TEST_NOTE:
        listing.pop("note", None)


def apply_review(listing: dict[str, Any], *, action: str, copy_edit: dict[str, Any] | None = None,
                 rejected_rooms: list[str] | None = None, notes: str | None = None,
                 test_listing: bool | None = None) -> dict[str, Any]:
    normalize(listing)
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
    if test_listing is not None:
        set_test_label(listing, test_listing)

    verify.run(listing, meta=False)

    if action == "approve":
        if not listing["copy"]["title"]:
            raise ReviewError(422, "Add a title before approving.")
        blocked = checklist.blocking(listing)
        if blocked and checklist.checks_block(listing):
            labels = ", ".join(item["label"] for item in blocked)
            raise ReviewError(409, f"Resolve {len(blocked)} checklist items before approving: {labels}.")
        listing["status"] = "approved"
        review.update(decision="approved", decided_at=db.now(),
                      open_checks=[item["label"] for item in blocked])
    elif action == "reject":
        listing["status"] = "rejected"
        review.update(decision="rejected", decided_at=db.now())
    elif edited and listing["status"] == "approved":
        listing["status"] = "draft"
        review.update(decision=None, decided_at=None)
    return listing


def unpublish(listing: dict[str, Any]) -> dict[str, Any]:
    """Return a published listing to draft so the broker can edit and republish.

    The published page and Live-In-It prep stay live until the broker publishes
    again, so there is no downtime and no reprocessing."""
    normalize(listing)
    if listing["status"] != "published":
        raise ReviewError(409, "Only a published listing can be unpublished.")
    listing["status"] = "draft"
    listing["review"].update(decision=None, decided_at=None)
    return listing


def publish(listing: dict[str, Any]) -> dict[str, Any]:
    normalize(listing)
    verify.run(listing, meta=False)
    if listing["status"] != "approved":
        raise ReviewError(409, "Approve the listing before publishing.")
    blocked = checklist.blocking(listing)
    verification = listing.get("verification") or {}
    if checklist.checks_block(listing):
        if blocked:
            labels = ", ".join(item["label"] for item in blocked)
            raise ReviewError(409, f"Resolve {len(blocked)} checklist items before publishing: {labels}.")
        if not verification.get("passed"):
            flags = verification.get("flags", [])
            detail = "; ".join(f["message"] for f in flags[:3]) or "verification did not pass"
            raise ReviewError(409, f"Verification has open flags: {detail}")
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
        "video": video.public(listing),
        "comps": listing["comps"],
        "verification": {
            "passed": bool(verification.get("passed")) and not blocked,
            "ran_at": verification.get("ran_at"),
            "checks": len(verification.get("checks", [])),
            "open": len(blocked),
        },
        "approved_at": listing["review"]["decided_at"],
        "published_at": published_at,
    }
    listing.update(status="published", published_at=published_at)
    return listing
