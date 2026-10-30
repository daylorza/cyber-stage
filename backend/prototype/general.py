"""Generalised cascade assets for ANY approved listing's main living room.

    uv run --env-file ../.env --with numpy --with meta-sam-parser \
        python -m prototype.general <listing_id> <video.mp4> <lines.json>

`lines.json` is the per-video camera calibration: two families of parallel
room edges measured on that video's hero frame, {"a": [[x1,y1,x2,y2], ...],
"b": [...]} in a 1600x900 frame. The POC camera is never reused blindly:
without lines for THIS video the build stops.

Refusals (Stop, nothing written): listing not broker-approved, no main
living room, no approved staging for it, no calibration lines, or the
clip fails the probe. Clean-footage rules (empty, slow, well-lit, framed
windows/doors, no people, no text, no watermark) are the broker's
attestation at upload; this builder does not re-litigate them and never
substitutes another listing's footage.

Output goes to frontend/public/prototype-general/<listing_id>/ (git-ignored),
the same manifest + textures the Prototype Testing page renders, at
/prototype-testing?listing=<listing_id>. Every generalised manifest is
labelled "Not a real listing — AI-modified" unless Day confirms real
facts in writing for that listing (see REAL_CONFIRMED below).
"""

import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

import cascade
import config
import meta_client
from prototype import assets
from prototype.assets import Stop

LABEL = "Not a real listing — AI-modified"
# Listing ids Day has confirmed in writing as real, broker-authorised listings
# with real facts. Empty: every generalised page carries the label above.
REAL_CONFIRMED: set[str] = set()
OUT_ROOT = config.REPO_DIR / "frontend" / "public" / "prototype-general"


def probe_video(path: Path) -> dict[str, Any]:
    """Any clip, probed: no hash lock (that guard is POC-only)."""
    if not path.is_file():
        raise Stop(f"{path} is not there. No other clip is substituted.")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,avg_frame_rate:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    num, den = (int(v) for v in stream["avg_frame_rate"].split("/"))
    return {"bytes": path.stat().st_size, "sha256": assets.sha256(path),
            "width": stream["width"], "height": stream["height"],
            "fps": round(num / den, 3), "duration": round(float(info["format"]["duration"]), 4)}


def check_enterable(listing: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The listing must be enterable, or the build stops and says why."""
    if (listing.get("review") or {}).get("decision") != "approved":
        raise Stop(f"listing {listing.get('id')} is not broker-approved; it is not enterable.")
    live_rooms = (listing.get("live") or {}).get("rooms") or []
    room = next((r for r in live_rooms if r.get("main")), None)
    if not room:
        raise Stop(f"listing {listing.get('id')} has no main living room; it is not enterable.")
    stage1 = next((r for r in listing.get("rooms") or [] if r.get("id") == room.get("id")), None)
    if not stage1 or not stage1.get("after"):
        raise Stop(f"listing {listing.get('id')} main room has no approved staging; it is not enterable.")
    return room, stage1


def require_calibration(lines_a: Any, lines_b: Any) -> None:
    """Per-video room-edge lines, or stop: the POC camera is not reused."""
    if not lines_a or not lines_b:
        raise Stop("no calibration lines for this video. Measure two families of parallel "
                   "room edges on its hero frame (1600x900) and pass them in lines.json; "
                   "the POC camera is not reused for other videos.")


def find_listing(db_path: Path, listing_id: str) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT data FROM listings").fetchall()
    finally:
        conn.close()
    for (raw,) in rows:
        listing = json.loads(raw)
        if listing.get("id") == listing_id:
            return listing
    raise Stop(f"no listing {listing_id} in the local build.")


def build(listing_id: str, video: Path, lines_a: Any, lines_b: Any,
          db_path: Path | None = None, out_dir: Path | None = None) -> dict[str, Any]:
    require_calibration(lines_a, lines_b)
    clip = probe_video(video)
    listing = find_listing(db_path or config.settings.db_path, listing_id)
    room, stage1 = check_enterable(listing)
    media = config.settings.media_dir
    frame = next(f for f in listing["frames"] if f["id"] == stage1["source_frame"])

    out = out_dir or (OUT_ROOT / listing_id)
    work = config.settings.data_dir / "prototype-general" / listing_id
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    pts = assets.hero_pts(video, float(frame["t"]))
    plate = work / "hero_plate.png"
    assets.extract_frame(video, pts, clip["fps"], plate)
    diff = assets.frame_diff(plate, media / frame["path"])
    if diff > assets.MAX_FRAME_DIFF:
        raise Stop(f"the grabbed frame differs from the pipeline's hero frame (mean diff {diff:.1f}).")

    meta = meta_client.get_client()
    trace: list[dict[str, Any]] = []
    floors = meta.sam_segment(plate, "floor", trace=trace, purpose=assets.SAM_PURPOSE, target={"concept": "floor"})
    windows = meta.sam_segment(plate, "window", trace=trace, purpose=assets.SAM_PURPOSE, target={"concept": "window"})
    plate_size = Image.open(plate).size
    floor = max((assets.norm_box(b["box"], plate_size) for b in floors),
                key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), default=None)
    camera = assets.calibrate(tuple(tuple(v) for v in lines_a), tuple(tuple(v) for v in lines_b))

    from prototype import cut  # numpy lives here; the module command adds it

    styles = []
    for style_id, label in assets.STYLES:
        live_style = room["styles"].get(style_id)
        path = media / (stage1["after"] if style_id == listing.get("style") else (live_style or {}).get("image", ""))
        entry = assets.plan_style(style_id, label, live_style, path if path.is_file() else None, meta, trace)
        entry["source"] = ("Broker-approved Stage 1 staging (Meta Image)" if style_id == listing.get("style")
                           else "Live-In-It preset (Meta Image), prepared earlier; not broker-approved")
        if entry["available"]:
            align = {k: (live_style.get("align") or cascade.IDENTITY)[k] for k in cascade.IDENTITY}
            with Image.open(path) as im:
                size = im.size
                aligned = cascade.warp(im.convert("RGB"), align, size)
            pieces = []
            for pid, concept, kind, name in assets.PIECES:
                records = meta.sam_masks(path, concept, trace=trace, purpose=assets.SAM_MASK_PURPOSE,
                                         target={"style": style_id, "concept": concept})
                if records:
                    best = max(records, key=lambda b: (b["box"][2] - b["box"][0]) * (b["box"][3] - b["box"][1]))
                    pieces.append({"id": pid, "name": name, "concept": concept, "kind": kind,
                                   "box": cascade.to_frame(assets.norm_box(best["box"], size), align),
                                   "mask": {"source": "SAM 3.1", "encoding": best["mask"]["encoding"],
                                            "raster": [best["mask"]["width"], best["mask"]["height"]]},
                                   "_records": [best]})
            for concept in assets.RIDER_CONCEPTS:
                for rec in meta.sam_masks(path, concept, trace=trace, purpose=assets.SAM_MASK_PURPOSE,
                                          target={"style": style_id, "concept": concept}):
                    box = cascade.to_frame(assets.norm_box(rec["box"], size), align)
                    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                    host = next((pc for pc in pieces if pc["kind"] == "upright"
                                 and pc["box"][0] <= cx <= pc["box"][2] and pc["box"][1] <= cy <= pc["box"][3]), None)
                    if host:
                        host["_records"].append(rec)
                        host.setdefault("riders", []).append({"concept": concept, "box": box})
            if not assets.require_pieces(entry, pieces):
                styles.append(entry)
                continue
            for pc in pieces:
                pc["coverage"] = assets.coverage(pc.pop("_records"), align)
            cut_out = cut.cut_style(aligned, Image.open(plate), pieces, camera, out, style_id, debug_dir=work)
            by_id = {p["id"]: p for p in cut_out["pieces"]}
            entry["pieces"] = [by_id[p["id"]] for p in pieces if p["id"] in by_id]
            entry["draw_order"] = cut_out["draw_order"]
            entry["check"] = cut_out["check"] | {"floor_anchor": assets.floor_contact_inside(entry["pieces"], floor)}
            entry["geometry"] = live_style.get("geometry")
            entry["image"] = str(path.relative_to(media))
        styles.append(entry)

    link = out / video.name
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(video.resolve())
    with Image.open(plate) as im:
        im.convert("RGB").resize((480, 270), Image.Resampling.LANCZOS).save(out / "hero_plate_small.png")

    label = LABEL if listing_id not in REAL_CONFIRMED else "AI-modified"
    manifest = {
        "label": label,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "listing": {"id": listing["id"], "note": listing.get("note"), "review": listing["review"]["decision"],
                    "room": room["name"], "hero_frame": frame["id"]},
        "video": {"src": f"/prototype-general/{listing_id}/{video.name}", **clip},
        "hero": {"t": frame["t"], "pts": round(pts, 6), "seek": round(pts + 0.5 / clip["fps"], 6),
                 "frame_diff": round(diff, 2), "plate": f"/prototype-general/{listing_id}/hero_plate_small.png"},
        "camera": camera,
        "sam": {"floor": floor, "floor_boxes": [assets.norm_box(b["box"], plate_size) for b in floors],
                "windows": [assets.norm_box(b["box"], plate_size) for b in windows],
                "window_note": None if windows else
                "SAM 3.1 finds no window in the hero frame, so window checks cannot run here."},
        "styles": styles,
        "meta_calls": [{k: t[k] for k in ("model", "purpose", "target", "cached", "ok", "summary")} for t in trace],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return manifest


def main() -> None:
    config.configure()
    if len(sys.argv) != 4:
        raise SystemExit("usage: python -m prototype.general <listing_id> <video.mp4> <lines.json>")
    listing_id, video, lines_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    lines = json.loads(lines_path.read_text()) if lines_path.is_file() else {}
    manifest = build(listing_id, video, lines.get("a"), lines.get("b"))
    calls = manifest["meta_calls"]
    print(f"Generalised assets for {listing_id} in {(OUT_ROOT / listing_id).relative_to(config.REPO_DIR)}")
    print(f"  clip: {manifest['video']['width']}x{manifest['video']['height']} {manifest['video']['duration']} s, "
          f"hero frame {manifest['hero']['pts']} s")
    for s in manifest["styles"]:
        print(f"  {s['label']}: " + (f"{len(s['pieces'])} pieces {s['draw_order']}" if s["available"] else f"off ({s['reason']})"))
    print(f"  Meta calls: {len(calls)} (SAM 3.1), {sum(1 for c in calls if c['cached'])} cached")


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        print(stop.code, file=sys.stderr)
        raise SystemExit(1)
