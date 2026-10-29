"""Runs one listing job through the pipeline, reporting stage + progress for status polling.

Stages write checklist items; the independent verifier runs last and reconciles
them. Meta errors mark their stage's item failed but never fail the job;
PipelineError (bad upload, over limit) still fails it.
"""

import logging
import time
from typing import Any, Callable

import checklist
import config
import db
import meta_client
import verify
from pipeline import PipelineError, classify, comps, copy, frames, privacy, segment, stage, video

log = logging.getLogger("vre.pipeline")

Step = Callable[[dict[str, Any]], dict[str, Any]]

STAGES: list[tuple[str, Step]] = [
    ("frames", frames.extract),
    ("masks", segment.run),
    ("privacy", privacy.run),
    ("video", video.run),
    ("rooms", classify.run),
    ("staging", stage.stage_rooms),
    ("copy", copy.write),
    ("comps", comps.attach),
    ("verify", verify.run),
]


def _run_verify(job: dict[str, Any]) -> None:
    listing = db.get_listing(job["listing_id"])
    if listing is None:
        db.update_job(job["id"], status="failed", error="Listing no longer exists.")
        return
    client = meta_client.get_client()
    if hasattr(client, "reset_budget"):
        client.reset_budget()
    try:
        db.update_job(job["id"], stage="verify", progress=50)
        listing = verify.run(listing)
    except Exception:
        log.exception("verify job %s crashed", job["id"])
        listing.update(status="draft", error="Verification stopped unexpectedly.")
        db.save_listing(listing)
        db.update_job(job["id"], status="failed", error="Verification stopped unexpectedly.")
        return
    if listing["review"]["decision"] == "rejected":
        listing["status"] = "rejected"
    else:
        listing["status"] = "draft"
        if listing["review"]["decision"] == "approved":
            listing["review"].update(decision=None, decided_at=None)
    db.save_listing(listing)
    db.update_job(job["id"], status="done", stage="ready", progress=100)


def _run_restage(job: dict[str, Any]) -> None:
    listing = db.get_listing(job["listing_id"])
    if listing is None:
        db.update_job(job["id"], status="failed", error="Listing no longer exists.")
        return
    request = listing.pop("restage_request", None) or {}
    prior_status = request.get("prior_status") or "draft"
    room_id, level = request.get("room"), request.get("level")
    if request.get("job_id") != job["id"] or not room_id or not isinstance(level, int):
        listing["status"] = prior_status
        db.save_listing(listing)
        db.update_job(job["id"], status="failed", error="No re-stage request found.")
        return
    client = meta_client.get_client()
    if hasattr(client, "reset_budget"):
        client.reset_budget()
    try:
        db.update_job(job["id"], stage="staging", progress=30)
        error = stage.restage_room(listing, room_id, level)
        if error:
            listing["status"] = prior_status
            db.save_listing(listing)
            db.update_job(job["id"], status="failed", error=error)
            return
        db.save_listing(listing)
        db.update_job(job["id"], stage="verify", progress=70)
        listing = verify.run(listing)
    except Exception:
        log.exception("restage job %s crashed", job["id"])
        listing.update(status="draft", error="Re-staging stopped unexpectedly.")
        db.save_listing(listing)
        db.update_job(job["id"], status="failed", error="Re-staging stopped unexpectedly.")
        return
    if listing["review"]["decision"] == "rejected":
        listing["status"] = "rejected"
    else:
        listing["status"] = "draft"
        if listing["review"]["decision"] == "approved":
            listing["review"].update(decision=None, decided_at=None)
    db.save_listing(listing)
    db.update_job(job["id"], status="done", stage="ready", progress=100)


def run(job: dict[str, Any]) -> None:
    if job.get("kind") == "verify":
        _run_verify(job)
        return
    if job.get("kind") == "restage":
        _run_restage(job)
        return
    listing = db.get_listing(job["listing_id"])
    if listing is None:
        db.update_job(job["id"], status="failed", error="Listing no longer exists.")
        return
    listing["checklist"] = checklist.new_checklist()
    listing["trace"] = []
    db.save_listing(listing)
    client = meta_client.get_client()
    if hasattr(client, "reset_budget"):
        client.reset_budget()
    name = "start"
    try:
        for index, (name, step) in enumerate(STAGES):
            db.update_job(job["id"], stage=name, progress=round(index / len(STAGES) * 100))
            listing = db.save_listing(step(listing))
            time.sleep(config.settings.stage_delay)
    except Exception as exc:
        if isinstance(exc, PipelineError):
            message = str(exc)
        else:
            log.exception("job %s crashed in stage %s", job["id"], name)
            message = f"Processing stopped unexpectedly during {name}."
        listing.update(status="failed", error=message)
        db.save_listing(listing)
        db.update_job(job["id"], status="failed", error=message)
        return
    listing["status"] = "draft"
    db.save_listing(listing)
    db.update_job(job["id"], status="done", stage="ready", progress=100)
