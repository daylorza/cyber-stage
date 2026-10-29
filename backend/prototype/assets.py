"""Build the Prototype Testing page's local assets (git-ignored) from the POC clip.

    make prototype     # cd backend && uv run --with numpy python -m prototype.assets

1. STOP unless the exact POC clip is at meta-hackathon/poc-luxury-empty-apartment.mp4
   (30,987,086 bytes, sha256 951f282a...). No other clip is ever substituted.
2. Find the local listing made from that clip (database opened read-only) and its
   broker-approved Modern Luxury staging (Meta Image). Nothing is re-ingested, re-staged,
   re-approved or written back.
3. Grab the hero frame from the 4K clip: the exact frame the staging was made from.
4. SAM 3.1 through meta_client (cached on disk): the floor on the hero frame (anchor), and
   per staged image the furniture boxes (placement) and curtains (window cover check).
5. Calibrate the camera from vanishing points of room edges measured on the hero frame.
6. Cut each piece (prototype.cut) and write textures + manifest.json, plus a symlink to the
   clip, into frontend/public/prototype/ (git-ignored: the clip never enters the repo).
"""

import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

import cascade
import config
import meta_client
from pipeline.frames import _packet_times

POC_NAME = "poc-luxury-empty-apartment.mp4"
POC_BYTES = 30_987_086
POC_SHA256 = "951f282aa16222010df1763ae172c3d32aa4b499a47f8ab7560612884d2c4a37"
LABEL = "Prototype Testing — Not a real listing — AI-modified — Proof of concept"
OUT_DIR = config.REPO_DIR / "frontend" / "public" / "prototype"
SAM_PURPOSE = "prototype.sam"
SAM_MASK_PURPOSE = "prototype.sam.masks"
STYLES = (("modern-luxury", "Modern Luxury"), ("coastal", "Coastal"), ("minimal", "Minimal"))
# What falls, in this order: the rug first (everything stands on it), then left to right.
PIECES = (
    ("rug", "rug", "rug", "Large rug"),
    ("sofa", "sofa", "upright", "Sofa"),
    ("coffee_table", "coffee table", "upright", "Coffee table"),
    ("armchair", "armchair", "upright", "Armchair"),
)
COVER_CONCEPT = "curtain"
# Decor that rides on a piece (found inside its box): it falls with that piece.
RIDER_CONCEPTS = ("cushion",)
MAX_FRAME_DIFF = 6.0  # mean abs luma diff vs the pipeline's hero frame; more = wrong frame

# Room edges measured by hand on the 1600x900 hero frame, (x1, y1, x2, y2). Two families of
# parallel edges, square to each other. A runs along the window wall (ceiling beam, top and
# bottom edge; window base). B recedes toward it (left wall base; kitchen counter front edge).
CALIB_SIZE = (1600, 900)
LINES_A = ((380, 275, 985, 196.7), (330, 320, 1100, 250), (490, 570, 1080, 630))
LINES_B = ((161.7, 646, 486.7, 578.3), (1127.5, 567.5, 1187.5, 850))
# One image has no absolute scale; these set it. The window bay's head sits ~1.03x as far
# above the horizon as its base is below it, so a ~2.75 m head puts the camera ~1.35 m up.
CAMERA_HEIGHT_M = 1.35
CEILING_M = 2.85


class Stop(SystemExit):
    """Refuse to build: print why and exit non-zero."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"STOP: {reason}")


def video_path() -> Path:
    return Path(os.environ.get("VRE_POC_VIDEO", str(config.REPO_DIR.parent / POC_NAME)))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_video(path: Path) -> dict[str, Any]:
    """The exact POC clip or nothing: same name, same bytes, same hash."""
    if path.name != POC_NAME or not path.is_file():
        raise Stop(f"{path} is not there. Put the POC clip at that exact path; no other clip is used.")
    size = path.stat().st_size
    if size != POC_BYTES:
        raise Stop(f"{path} is {size:,} bytes, expected {POC_BYTES:,}. Not the confirmed POC clip.")
    digest = sha256(path)
    if digest != POC_SHA256:
        raise Stop(f"{path} has sha256 {digest[:16]}..., expected {POC_SHA256[:16]}...")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,avg_frame_rate:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    num, den = (int(v) for v in stream["avg_frame_rate"].split("/"))
    return {"bytes": size, "sha256": digest, "width": stream["width"], "height": stream["height"],
            "fps": round(num / den, 3), "duration": round(float(info["format"]["duration"]), 4)}


def find_listing(db_path: Path) -> dict[str, Any]:
    """The listing whose upload IS the POC clip (by hash). Read-only connection."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT data FROM listings").fetchall()
    finally:
        conn.close()
    found = []
    for (raw,) in rows:
        listing = json.loads(raw)
        for up in listing.get("uploads") or []:
            path = config.settings.uploads_dir / up.get("path", "")
            if path.is_file() and path.stat().st_size == POC_BYTES and sha256(path) == POC_SHA256:
                found.append(listing)
                break
    approved = [l for l in found if (l.get("review") or {}).get("decision") == "approved"]
    if not approved:
        raise Stop("no broker-approved listing from the POC clip in the local build.")
    return max(approved, key=lambda l: l.get("updated_at", ""))


def hero_pts(video: Path, t: float) -> float:
    packets = _packet_times(video)
    if not packets:
        raise Stop("could not read frame times from the clip.")
    return min(packets, key=lambda p: abs(p - t))


def extract_frame(video: Path, pts: float, fps: float, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    # Accurate seek keeps the first frame at or after -ss; a quarter frame early lands on `pts`.
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{pts - 0.25 / fps:.6f}", "-i", str(video),
         "-frames:v", "1", str(out)],
        check=True,
    )


def frame_diff(a: Path, b: Path) -> float:
    with Image.open(a) as x, Image.open(b) as y:
        size = y.size
        return ImageStat.Stat(ImageChops.difference(x.convert("L").resize(size), y.convert("L"))).mean[0]


def _vanishing_point(lines: tuple[tuple[float, ...], ...]) -> tuple[float, float]:
    """Least-squares point closest to every line."""
    a11 = a12 = a22 = b1 = b2 = 0.0
    for x1, y1, x2, y2 in lines:
        nx, ny = y2 - y1, x1 - x2
        n = math.hypot(nx, ny)
        nx, ny = nx / n, ny / n
        c = nx * x1 + ny * y1
        a11, a12, a22 = a11 + nx * nx, a12 + nx * ny, a22 + ny * ny
        b1, b2 = b1 + nx * c, b2 + ny * c
    det = a11 * a22 - a12 * a12
    return (a22 * b1 - a12 * b2) / det, (a11 * b2 - a12 * b1) / det


def calibrate(lines_a=LINES_A, lines_b=LINES_B, size=CALIB_SIZE) -> dict[str, Any]:
    """Pinhole camera from two square vanishing points, principal point at the centre:
    (vA - c) . (vB - c) = -f^2. Their line is the horizon (pitch, roll)."""
    w, h = size
    (ax, ay), (bx, by) = _vanishing_point(lines_a), _vanishing_point(lines_b)
    cx, cy = w / 2, h / 2
    f2 = -((ax - cx) * (bx - cx) + (ay - cy) * (by - cy))
    if f2 <= 0:
        raise ValueError("vanishing points are not from square directions")
    f = math.sqrt(f2)
    horizon = ay + (by - ay) * (cx - ax) / (bx - ax)
    return {
        "source": "vanishing points of room edges measured on the hero frame",
        "focal_px": round(f, 1), "size": [w, h],
        "fx": round(f / w, 5), "fy": round(f / h, 5),
        "vfov_deg": round(math.degrees(2 * math.atan(h / 2 / f)), 2),
        "hfov_deg": round(math.degrees(2 * math.atan(w / 2 / f)), 2),
        "horizon_y": round(horizon / h, 5),
        "pitch_deg": round(math.degrees(math.atan((cy - horizon) / f)), 3),
        "roll_deg": round(math.degrees(math.atan2(by - ay, bx - ax)), 3),
        "vanishing_points": [[round(ax, 1), round(ay, 1)], [round(bx, 1), round(by, 1)]],
        "height_m": CAMERA_HEIGHT_M, "ceiling_m": CEILING_M,
        "assumed": ["principal point at the image centre", "no lens distortion",
                    f"camera {CAMERA_HEIGHT_M} m above the floor, ceiling at {CEILING_M} m (sets scale only)"],
    }


def norm_box(box: list[float], size: tuple[int, int]) -> list[float]:
    w, h = size
    return [round(box[0] / w, 4), round(box[1] / h, 4), round(box[2] / w, 4), round(box[3] / h, 4)]


def floor_contact_inside(pieces: list[dict[str, Any]], floor: list[float] | None) -> dict[str, Any]:
    """Every piece's floor contact (base points; the rug's own box) must sit in the SAM floor box."""
    if not floor:
        return {"status": "not_checked", "reason": "SAM 3.1 returned no floor box."}
    outside = []
    for pc in pieces:
        pts = pc.get("base") or [[pc["box"][0], pc["box"][3]], [pc["box"][2], pc["box"][3]]]
        if any(not (floor[0] - 0.01 <= x <= floor[2] + 0.01 and floor[1] - 0.01 <= y <= floor[3] + 0.01)
               for x, y in pts):
            outside.append(pc["id"])
    return {"status": "pass" if not outside else "fail", "outside": outside,
            "reason": "All floor contacts inside the SAM floor box." if not outside
            else f"Outside the SAM floor box: {', '.join(outside)}."}


def coverage(records: list[dict[str, Any]], align: dict[str, float]) -> Image.Image:
    """SAM 3.1 masks as one soft coverage image (L, 0-255) in hero-frame coordinates, at the
    size of the image SAM saw. Lossless masks are 8-bit coverage: edges come out anti-aliased."""
    from meta_sam_parser import SegmentationMask, decode_mask_to_raster  # `make prototype` adds it
    from meta_sam_parser._mask_codec import _decode_lossless_raster

    size = tuple(records[0]["source_size"])
    canvas = Image.new("L", size, 0)
    for rec in records:
        m = rec["mask"]
        w, h = m["width"], m["height"]
        if m["encoding"] == "lossless":
            raster = _decode_lossless_raster(m["payload"], w, h)
        else:
            raster = bytes(255 * v for v in decode_mask_to_raster(SegmentationMask("one_bit", m["payload"], w, h)))
        x1, y1 = rec["source_box"][:2]
        piece = Image.frombytes("L", (w, h), raster)
        layer = Image.new("L", size, 0)
        layer.paste(piece, (x1, y1))
        canvas = ImageChops.lighter(canvas, layer)
    return cascade.warp(canvas, align, size) if align != cascade.IDENTITY else canvas


def plan_style(style_id: str, label: str, live_style: dict[str, Any] | None, image: Path | None,
               meta, trace: list) -> dict[str, Any]:
    """Which styles can drop here, without re-running anything: approved or prepared image,
    furniture SAM can box, and no curtains across the windows (a real cover)."""
    entry: dict[str, Any] = {"id": style_id, "label": label, "available": False}
    if not image or not image.is_file() or not (live_style or {}).get("available"):
        entry["reason"] = "No staged image for this style in the local build."
        entry["reason_short"] = "no staged image"
        return entry
    if not (live_style or {}).get("pieces"):
        entry["reason"] = ("Meta Image added no furniture to this room in this style: SAM 3.1 found no sofa, "
                           "chair, table, bed, lamp, rug or plant, so there is nothing to drop.")
        entry["reason_short"] = "no furniture to drop"
        return entry
    size = Image.open(image).size
    curtains = meta.sam_segment(image, COVER_CONCEPT, trace=trace, purpose=SAM_PURPOSE,
                                target={"style": style_id, "concept": COVER_CONCEPT})
    if curtains:
        span = sum(b["box"][2] - b["box"][0] for b in curtains) / size[0]
        entry["reason"] = (f"Meta Image drew curtains across the window wall (SAM 3.1: {len(curtains)} curtain "
                           f"box(es), {span:.0%} of the frame width). That covers the windows, a real cover, "
                           "so this style stays off.")
        entry["reason_short"] = "curtains cover the windows"
        entry["curtains"] = [norm_box(b["box"], size) for b in curtains]
        return entry
    entry["cover_check"] = {"status": "pass", "reason": "SAM 3.1 finds no curtains in the staged image."}
    entry["available"] = True
    return entry


def build() -> dict[str, Any]:
    video = video_path()
    clip = verify_video(video)
    listing = find_listing(config.settings.db_path)
    media = config.settings.media_dir
    live_rooms = (listing.get("live") or {}).get("rooms") or []
    room = next((r for r in live_rooms if r.get("main")), None)
    stage1 = next((r for r in listing.get("rooms") or [] if r.get("id") == (room or {}).get("id")), None)
    if not room or not stage1 or not stage1.get("after"):
        raise Stop("the POC listing has no prepared main living room with an approved staging.")
    frame = next(f for f in listing["frames"] if f["id"] == stage1["source_frame"])

    work = config.settings.data_dir / "prototype"
    work.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pts = hero_pts(video, float(frame["t"]))
    plate = work / "hero_plate.png"
    extract_frame(video, pts, clip["fps"], plate)
    diff = frame_diff(plate, media / frame["path"])
    if diff > MAX_FRAME_DIFF:
        raise Stop(f"the grabbed frame differs from the pipeline's hero frame (mean diff {diff:.1f}).")

    meta = meta_client.get_client()
    trace: list[dict[str, Any]] = []
    floors = meta.sam_segment(plate, "floor", trace=trace, purpose=SAM_PURPOSE, target={"concept": "floor"})
    windows = meta.sam_segment(plate, "window", trace=trace, purpose=SAM_PURPOSE, target={"concept": "window"})
    plate_size = Image.open(plate).size
    floor = max((norm_box(b["box"], plate_size) for b in floors),
                key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), default=None)
    camera = calibrate()

    from prototype import cut  # numpy lives here; `make prototype` adds it for this script only

    styles = []
    for style_id, label in STYLES:
        live_style = room["styles"].get(style_id)
        path = media / (stage1["after"] if style_id == listing.get("style") else (live_style or {}).get("image", ""))
        entry = plan_style(style_id, label, live_style, path if path.is_file() else None, meta, trace)
        entry["source"] = ("Broker-approved Stage 1 staging (Meta Image)" if style_id == listing.get("style")
                           else "Live-In-It preset (Meta Image), prepared earlier; not broker-approved")
        if entry["available"]:
            align = {k: (live_style.get("align") or cascade.IDENTITY)[k] for k in cascade.IDENTITY}
            with Image.open(path) as im:
                size = im.size
                aligned = cascade.warp(im.convert("RGB"), align, size)
            pieces = []
            for pid, concept, kind, name in PIECES:
                records = meta.sam_masks(path, concept, trace=trace, purpose=SAM_MASK_PURPOSE,
                                         target={"style": style_id, "concept": concept})
                if records:
                    best = max(records, key=lambda b: (b["box"][2] - b["box"][0]) * (b["box"][3] - b["box"][1]))
                    pieces.append({"id": pid, "name": name, "concept": concept, "kind": kind,
                                   "box": cascade.to_frame(norm_box(best["box"], size), align),
                                   "mask": {"source": "SAM 3.1", "encoding": best["mask"]["encoding"],
                                            "raster": [best["mask"]["width"], best["mask"]["height"]]},
                                   "_records": [best]})
            for concept in RIDER_CONCEPTS:
                for rec in meta.sam_masks(path, concept, trace=trace, purpose=SAM_MASK_PURPOSE,
                                          target={"style": style_id, "concept": concept}):
                    box = cascade.to_frame(norm_box(rec["box"], size), align)
                    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                    host = next((pc for pc in pieces if pc["kind"] == "upright"
                                 and pc["box"][0] <= cx <= pc["box"][2] and pc["box"][1] <= cy <= pc["box"][3]), None)
                    if host:
                        host["_records"].append(rec)
                        host.setdefault("riders", []).append({"concept": concept, "box": box})
            for pc in pieces:
                pc["coverage"] = coverage(pc.pop("_records"), align)
            out = cut.cut_style(aligned, Image.open(plate), pieces, camera, OUT_DIR, style_id, debug_dir=work)
            by_id = {p["id"]: p for p in out["pieces"]}
            entry["pieces"] = [by_id[p["id"]] for p in pieces if p["id"] in by_id]
            entry["draw_order"] = out["draw_order"]
            entry["check"] = out["check"] | {"floor_anchor": floor_contact_inside(entry["pieces"], floor)}
            entry["geometry"] = live_style.get("geometry")
            entry["image"] = str(path.relative_to(media))
        styles.append(entry)

    link = OUT_DIR / POC_NAME
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(video.resolve())
    # A small copy of the extracted hero frame: the page compares it with the frame as the
    # browser shows it (the clip is HDR) and corrects the pieces' colour to match.
    with Image.open(plate) as im:
        im.convert("RGB").resize((480, 270), Image.Resampling.LANCZOS).save(OUT_DIR / "hero_plate_small.png")

    manifest = {
        "label": LABEL,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "listing": {"id": listing["id"], "note": listing.get("note"), "review": listing["review"]["decision"],
                    "room": room["name"], "hero_frame": frame["id"]},
        "video": {"src": f"/prototype/{POC_NAME}", **clip},
        "hero": {"t": frame["t"], "pts": round(pts, 6), "seek": round(pts + 0.5 / clip["fps"], 6),
                 "frame_diff": round(diff, 2), "plate": "/prototype/hero_plate_small.png"},
        "camera": camera,
        "sam": {"floor": floor, "floor_boxes": [norm_box(b["box"], plate_size) for b in floors],
                "windows": [norm_box(b["box"], plate_size) for b in windows],
                "window_note": None if windows else
                "SAM 3.1 finds no window in the hero frame (floor-to-ceiling glass), so window checks cannot run here."},
        "styles": styles,
        "meta_calls": [{k: t[k] for k in ("model", "purpose", "target", "cached", "ok", "summary")} for t in trace],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return manifest


def main() -> None:
    config.configure()
    manifest = build()
    calls = manifest["meta_calls"]
    print(f"Prototype assets in {OUT_DIR.relative_to(config.REPO_DIR)}")
    print(f"  clip: {manifest['video']['width']}x{manifest['video']['height']} "
          f"{manifest['video']['duration']} s, hero frame {manifest['hero']['pts']} s")
    print(f"  camera: vfov {manifest['camera']['vfov_deg']} deg, pitch {manifest['camera']['pitch_deg']} deg")
    for s in manifest["styles"]:
        print(f"  {s['label']}: " + (f"{len(s['pieces'])} pieces {s['draw_order']}" if s["available"] else f"off ({s['reason']})"))
    print(f"  Meta calls: {len(calls)} (SAM 3.1), {sum(1 for c in calls if c['cached'])} cached")


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        print(stop.code, file=sys.stderr)
        raise SystemExit(1)
