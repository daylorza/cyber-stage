"""Runs one listing job through the pipeline, reporting stage + progress for status polling."""

import logging
import time
from typing import Any, Callable

import config
import db
from pipeline import PipelineError, comps, copy, frames, segment, stage

log = logging.getLogger("vre.pipeline")

Step = Callable[[dict[str, Any]], dict[str, Any]]

STAGES: list[tuple[str, Step]] = [
    ("frames", frames.extract),
    ("rooms", segment.group_rooms),
    ("staging", stage.stage_rooms),
    ("copy", copy.write),
    ("comps", comps.attach),
]


def run(job: dict[str, Any]) -> None:
    listing = db.get_listing(job["listing_id"])
    if listing is None:
        db.update_job(job["id"], status="failed", error="Listing no longer exists.")
        return
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
