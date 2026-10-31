"""Walkthrough to Listing API. Run: uv run uvicorn main:create_app --factory --reload"""

import re
import shutil
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import db
import export_logs
import listings
import live
import meta_client
from jobs import Worker
from pipeline import runner, stage

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
CURRENCIES = {"USD", "GBP", "EUR"}
CHUNK = 1 << 20

router = APIRouter(prefix="/api")


def _kind(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in PHOTO_EXTS:
        return "photo"
    raise HTTPException(415, f"{filename} isn't supported. Upload a video (MP4, MOV, M4V, WebM) or photos (JPG, PNG, WebP).")


def _number(raw: str, name: str, cast: type = int) -> Any:
    raw = raw.replace(",", "").strip()
    if not raw:
        return None
    try:
        value = cast(raw)
    except ValueError:
        raise HTTPException(422, f"{name} must be a number.") from None
    if value < 0:
        raise HTTPException(422, f"{name} can't be negative.")
    return value


def _safe_name(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name)[-80:] or "upload"


def _listing_or_404(listing_id: str) -> dict[str, Any]:
    listing = db.get_listing(listing_id)
    if listing is None:
        raise HTTPException(404, "Listing not found.")
    return listings.normalize(listing)


def _review_call(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return db.save_listing(fn(*args, **kwargs))
    except listings.ReviewError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta/status")
def meta_status() -> dict[str, Any]:
    return meta_client.meta_status()


@router.get("/settings")
def app_settings() -> dict[str, Any]:
    return {"blocking_checks": config.settings.blocking_checks}


@router.post("/listings", status_code=202)
async def create_listing(
    files: list[UploadFile] = File(...),
    address: str = Form(""),
    city: str = Form(""),
    beds: str = Form(""),
    baths: str = Form(""),
    sqft: str = Form(""),
    price: str = Form(""),
    currency: str = Form("USD"),
    estimate_price: bool = Form(False),
    style: str = Form(listings.DEFAULT_STYLE),
    test_listing: bool = Form(False),
    prototype_test: bool = Form(False),
) -> dict[str, str]:
    kinds = [_kind(f.filename or "") for f in files]
    if currency not in CURRENCIES:
        raise HTTPException(422, f"Currency must be one of {', '.join(sorted(CURRENCIES))}.")
    if style not in listings.STYLES:
        raise HTTPException(422, f"Style must be one of {', '.join(sorted(listings.STYLES))}.")
    facts = {
        "address": address.strip(),
        "city": city.strip(),
        "beds": _number(beds, "Bedrooms", float),
        "baths": _number(baths, "Bathrooms", float),
        "sqft": _number(sqft, "Square feet"),
        "price": None if estimate_price else _number(price, "Asking price"),
        "currency": currency,
        "estimate_price": estimate_price,
    }
    if facts["beds"] is not None and facts["beds"].is_integer():
        facts["beds"] = int(facts["beds"])

    s = config.settings
    listing_id, job_id = db.new_id("lst"), db.new_id("job")
    upload_dir = s.uploads_dir / listing_id
    upload_dir.mkdir(parents=True)
    limit, total, uploads = s.max_upload_mb * 1024 * 1024, 0, []
    try:
        for index, (upload, kind) in enumerate(zip(files, kinds), start=1):
            dest = upload_dir / f"{index:02d}_{_safe_name(upload.filename or '')}"
            with dest.open("wb") as out:
                while chunk := await upload.read(CHUNK):
                    total += len(chunk)
                    if total > limit:
                        raise HTTPException(413, f"Uploads are limited to {s.max_upload_mb} MB in total.")
                    out.write(chunk)
            uploads.append({"name": upload.filename, "kind": kind, "path": str(dest.relative_to(s.uploads_dir))})
    except BaseException:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise

    listing = listings.new_listing(listing_id, source="upload", facts=facts, uploads=uploads, job_id=job_id,
                                   style=style)
    if prototype_test:
        listing["prototype_test"] = True
    listings.set_test_label(listing, test_listing)
    with db.connect() as conn:
        db.insert_listing(conn, listing)
        db.insert_job(conn, job_id, listing_id, "listing")
    return {"listing_id": listing_id, "job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job


@router.get("/listings")
def list_listings() -> list[dict[str, Any]]:
    return [listings.summary(listings.normalize(item)) for item in db.list_listings()]


@router.get("/listings/{listing_id}")
def get_listing(listing_id: str) -> dict[str, Any]:
    listing = _listing_or_404(listing_id)
    listing["job"] = db.get_job(listing["job_id"]) if listing.get("job_id") else None
    return listing


@router.delete("/listings/{listing_id}")
def delete_listing(listing_id: str) -> dict[str, bool]:
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT source FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Listing not found.")
        if row["source"] == "seed":
            raise HTTPException(409, "Seeded hero listings cannot be deleted.")
        if conn.execute("SELECT 1 FROM jobs WHERE listing_id = ? AND status IN ('queued', 'running')", (listing_id,)).fetchone():
            raise HTTPException(409, "Wait for processing to finish before deleting.")
        conn.execute("DELETE FROM reservations WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM jobs WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
    return {"deleted": True}


class CopyEdit(BaseModel):
    title: str
    description: str
    highlights: list[str]


class ReviewBody(BaseModel):
    action: Literal["save", "approve", "reject"]
    copy_edit: CopyEdit | None = None
    rejected_rooms: list[str] | None = None
    notes: str | None = None
    test_listing: bool | None = None


@router.post("/listings/{listing_id}/review")
def review_listing(listing_id: str, body: ReviewBody) -> dict[str, Any]:
    return _review_call(
        listings.apply_review,
        _listing_or_404(listing_id),
        action=body.action,
        copy_edit=body.copy_edit.model_dump() if body.copy_edit else None,
        rejected_rooms=body.rejected_rooms,
        notes=body.notes,
        test_listing=body.test_listing,
    )


@router.post("/listings/{listing_id}/publish")
def publish_listing(listing_id: str) -> dict[str, Any]:
    return _review_call(listings.publish, _listing_or_404(listing_id))


@router.post("/listings/{listing_id}/unpublish")
def unpublish_listing(listing_id: str) -> dict[str, Any]:
    return _review_call(listings.unpublish, _listing_or_404(listing_id))


@router.post("/listings/{listing_id}/reprocess", status_code=202)
def reprocess_listing(listing_id: str) -> dict[str, str]:
    """Re-run the full pipeline from the stored uploads. Starts the listing over:
    fresh checklist and trace, generated copy replaces broker edits. A published listing is
    taken down: it needs a new broker approval and publish before anyone sees it again."""
    listing = _listing_or_404(listing_id)
    if listing["source"] != "upload" or listing["status"] not in {"draft", "approved", "rejected", "failed",
                                                                   "published"}:
        raise HTTPException(409, "This listing can't be reprocessed right now.")
    if (listing.get("live") or {}).get("status") == "preparing":
        raise HTTPException(409, "Live-In-It is being prepared; reprocess when it finishes.")
    job_id = db.new_id("job")
    listing["status"] = "processing"
    listing["job_id"] = job_id
    listing["verification"] = None
    listing.pop("published", None)
    listing.pop("published_at", None)
    listing.pop("live", None)
    listing.pop("token_guard", None)
    listing["review"] = {"decision": None, "decided_at": None, "notes": "", "edited_fields": []}
    db.save_listing(listing)
    with db.connect() as conn:
        db.insert_job(conn, job_id, listing_id, "listing")
    return {"listing_id": listing_id, "job_id": job_id}


@router.post("/listings/{listing_id}/verify", status_code=202)
def verify_listing(listing_id: str) -> dict[str, str]:
    """Re-run only the independent verifier with live Meta calls.
    Preserves content, broker edits, and the existing checklist."""
    listing = _listing_or_404(listing_id)
    if listing["source"] != "upload" or listing["status"] not in {"draft", "approved", "rejected"}:
        raise HTTPException(409, "This listing can't be verified right now.")
    job_id = db.new_id("job")
    listing["status"] = "processing"
    listing["job_id"] = job_id
    db.save_listing(listing)
    with db.connect() as conn:
        db.insert_job(conn, job_id, listing_id, "verify")
    return {"listing_id": listing_id, "job_id": job_id}


@router.post("/listings/{listing_id}/rooms/{room_id}/restage", status_code=202)
def restage_room(listing_id: str, room_id: str) -> dict[str, Any]:
    """Re-stage one flagged room with a stricter prompt: a fresh Meta Image call,
    then the verifier re-runs so the flag clears or stays."""
    listing = _listing_or_404(listing_id)
    room = next((r for r in listing.get("rooms") or [] if r.get("id") == room_id), None)
    if room is None:
        raise HTTPException(404, "Room not found.")
    if listing["source"] != "upload" or listing["status"] not in {"draft", "approved", "rejected"}:
        raise HTTPException(409, "This listing can't be re-staged right now.")
    if room.get("rejected"):
        raise HTTPException(409, "This room is excluded from the listing.")
    checks = (listing.get("verification") or {}).get("checks") or []
    flagged = any(
        c.get("item") == "staging_geometry"
        and (c.get("target") or {}).get("room") == room_id
        and c.get("status") != "pass"
        for c in checks
    ) or bool((room.get("staging") or {}).get("error"))
    if not flagged:
        raise HTTPException(409, "This room has no staging flag to fix.")
    level = ((room.get("staging") or {}).get("level") or 0) + 1
    if level > stage.MAX_RESTAGE_LEVEL:
        raise HTTPException(
            409,
            f"Stricter re-staging was already tried twice for {room.get('name') or room_id}; "
            "exclude the room or re-film it.",
        )
    job_id = db.new_id("job")
    listing["restage_request"] = {
        "job_id": job_id, "room": room_id, "level": level, "prior_status": listing["status"],
    }
    listing["status"] = "processing"
    listing["job_id"] = job_id
    db.save_listing(listing)
    with db.connect() as conn:
        db.insert_job(conn, job_id, listing_id, "restage")
    return {"listing_id": listing_id, "job_id": job_id, "room_id": room_id, "level": level}


@router.get("/listings/{listing_id}/export")
def export_listing_logs(listing_id: str) -> Response:
    """Download the full debug log for one listing as one text file. Read-only."""
    listing = _listing_or_404(listing_id)
    exported_at = datetime.now(UTC)
    text = export_logs.render(
        listing, db.list_jobs(listing_id),
        meta=meta_client.meta_status(), commit=export_logs.app_commit(),
        exported_at=exported_at,
    )
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{export_logs.filename(listing_id, exported_at)}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/listings/{listing_id}/page")
def published_page(listing_id: str) -> dict[str, Any]:
    """The broker-approved snapshot (video first), plus its label and whether a buyer can
    enter Live-In-It from it (and why not)."""
    listing = _listing_or_404(listing_id)
    if listing["status"] != "published":
        raise HTTPException(404, "This listing isn't published.")
    return {**listing["published"], "video": listing["published"].get("video"),
            "note": listing.get("note"), "live": live.eligibility(listing)}


class LiveRequest(BaseModel):
    residence: str | None = None


@router.post("/listings/{listing_id}/live", status_code=202)
def request_live(listing_id: str, body: LiveRequest) -> dict[str, str]:
    """Enqueue the Live-In-It preparation job for a published listing."""
    listing = _listing_or_404(listing_id)
    try:
        job_id = live.request(listing, body.residence)
    except listings.ReviewError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    return {"listing_id": listing_id, "job_id": job_id}


@router.post("/listings/{listing_id}/live/rooms/{room_id}/styles/{style_id}/rerun", status_code=202)
def rerun_live_style(listing_id: str, room_id: str, style_id: str) -> dict[str, str]:
    if style_id not in stage.STYLE_PRESETS:
        raise HTTPException(422, "Unknown style.")
    listing = db.get_listing(listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found.")
    block = listing.get("live") or {}
    if listing.get("status") != "published" or block.get("status") != "ready":
        raise HTTPException(409, "A published, prepared residence is required.")
    room = next((r for r in block.get("rooms", []) if r.get("id") == room_id), None)
    if not room:
        raise HTTPException(404, "Prepared room not found.")
    job_id = db.new_id("job")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM jobs WHERE listing_id = ? AND status IN ('queued', 'running')", (listing_id,)).fetchone():
            raise HTTPException(409, "Wait for the current job to finish.")
        db.insert_job(conn, job_id, listing_id, f"live_style:{room_id}:{style_id}")
    return {"listing_id": listing_id, "job_id": job_id}


@router.get("/listings/{listing_id}/live")
def get_live(listing_id: str) -> dict[str, Any]:
    listing = _listing_or_404(listing_id)
    if listing["status"] != "published":
        raise HTTPException(404, "This listing isn't published.")
    if not listing.get("live"):
        raise HTTPException(404, "Live-In-It hasn't been prepared for this listing.")
    return live.payload(listing)


@router.get("/residences/{residence_id}/live")
def residence_live(residence_id: str) -> dict[str, Any]:
    result = live.for_residence(residence_id)
    if result is None:
        raise HTTPException(404, "No published listing for this residence yet.")
    return result


@router.post("/listings/{listing_id}/reserve", status_code=201)
def reserve(listing_id: str) -> dict[str, Any]:
    """SIMULATED hold for the demo. No payment provider is called and nothing is charged."""
    listing = _listing_or_404(listing_id)
    if listing["status"] != "published":
        raise HTTPException(409, "Only published listings can be reserved.")
    return {**db.insert_reservation(listing_id), "charged": False, "payment_taken": False,
            "provider": None,
            "message": "Simulated hold. No payment was taken; the broker confirms."}


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / "index.html")


def _dispatch(job: dict[str, Any]) -> None:
    if job.get("kind", "").startswith("live_style:"):
        live.rerun_style(job)
    elif job.get("kind") == "live":
        live.run(job)
    else:
        runner.run(job)


def create_app(**overrides: Any) -> FastAPI:
    settings = config.configure(**overrides)
    worker = Worker(_dispatch)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.init()
        listings.seed_inventory()
        worker.start()
        yield
        worker.stop()

    app = FastAPI(title="Walkthrough to Listing", lifespan=lifespan)
    app.mount("/api/media", StaticFiles(directory=settings.media_dir), name="media")
    app.include_router(router)
    if (settings.frontend_dist / "index.html").is_file():
        _mount_frontend(app, settings.frontend_dist)
    return app
