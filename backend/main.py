"""Walkthrough to Listing API. Run: uv run uvicorn main:create_app --factory --reload"""

import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import db
import listings
from jobs import Worker
from pipeline import runner

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
    return listing


def _review_call(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return db.save_listing(fn(*args, **kwargs))
    except listings.ReviewError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
) -> dict[str, str]:
    kinds = [_kind(f.filename or "") for f in files]
    if currency not in CURRENCIES:
        raise HTTPException(422, f"Currency must be one of {', '.join(sorted(CURRENCIES))}.")
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

    listing = listings.new_listing(listing_id, source="upload", facts=facts, uploads=uploads, job_id=job_id)
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
    return [listings.summary(item) for item in db.list_listings()]


@router.get("/listings/{listing_id}")
def get_listing(listing_id: str) -> dict[str, Any]:
    listing = _listing_or_404(listing_id)
    listing["job"] = db.get_job(listing["job_id"]) if listing.get("job_id") else None
    return listing


class CopyEdit(BaseModel):
    title: str
    description: str
    highlights: list[str]


class ReviewBody(BaseModel):
    action: Literal["save", "approve", "reject"]
    copy_edit: CopyEdit | None = None
    rejected_rooms: list[str] | None = None
    notes: str | None = None


@router.post("/listings/{listing_id}/review")
def review_listing(listing_id: str, body: ReviewBody) -> dict[str, Any]:
    return _review_call(
        listings.apply_review,
        _listing_or_404(listing_id),
        action=body.action,
        copy_edit=body.copy_edit.model_dump() if body.copy_edit else None,
        rejected_rooms=body.rejected_rooms,
        notes=body.notes,
    )


@router.post("/listings/{listing_id}/publish")
def publish_listing(listing_id: str) -> dict[str, Any]:
    return _review_call(listings.publish, _listing_or_404(listing_id))


@router.get("/listings/{listing_id}/page")
def published_page(listing_id: str) -> dict[str, Any]:
    listing = _listing_or_404(listing_id)
    if listing["status"] != "published":
        raise HTTPException(404, "This listing isn't published.")
    return listing["published"]


@router.post("/listings/{listing_id}/reserve", status_code=201)
def reserve(listing_id: str) -> dict[str, Any]:
    """SIMULATED hold for the demo. No payment provider is called and nothing is charged."""
    listing = _listing_or_404(listing_id)
    if listing["status"] != "published":
        raise HTTPException(409, "Only published listings can be reserved.")
    return {**db.insert_reservation(listing_id), "charged": False,
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


def create_app(**overrides: Any) -> FastAPI:
    settings = config.configure(**overrides)
    worker = Worker(runner.run)

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
