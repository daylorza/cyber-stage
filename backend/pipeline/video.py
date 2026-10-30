"""Publishable walkthrough video: the WHOLE upload, in order, re-encoded to H.264 with the
audio removed, and every SAM privacy box blurred for the stretch of video around the frame
it was found in (from half a second before that frame to half a second after the next one).

The published listing page plays this file. Raw uploads are never served. A video whose
sampled seconds did not all get SAM privacy masks is held back (no path), exactly like a
held-back frame. Blurring follows the 1-per-second SAM samples: something that appears only
between two samples is not seen by SAM, and the console says so.
"""

import shutil
import subprocess
from typing import Any

import config
from pipeline.frames import clock

PAD_RATIO = 0.25
WINDOW = 0.5
MAX_SIDE = 1920
NOTE = "Blur follows SAM's 1-per-second samples; brief appearances between samples are not checked. Audio removed."


def _even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def regions(frames: list[dict[str, Any]], duration: float, scale: float,
            out_w: int, out_h: int) -> list[tuple[int, int, int, int, float, float]]:
    """(x, y, w, h, t0, t1) in output pixels for every privacy box, padded and kept even."""
    out: list[tuple[int, int, int, int, float, float]] = []
    for i, frame in enumerate(frames):
        t0 = max(0.0, (frame["t"] or 0) - WINDOW)
        t1 = (frames[i + 1]["t"] if i + 1 < len(frames) else duration) + WINDOW
        for box in (frame.get("sam") or {}).get("privacy") or []:
            x1, y1, x2, y2 = (v * scale for v in box["box"])
            px, py = (x2 - x1) * PAD_RATIO, (y2 - y1) * PAD_RATIO
            x = max(0, int(x1 - px) // 2 * 2)
            y = max(0, int(y1 - py) // 2 * 2)
            w = min(out_w - x, _even(x2 - x1 + 2 * px))
            h = min(out_h - y, _even(y2 - y1 + 2 * py))
            if w >= 4 and h >= 4:
                out.append((x, y, w // 2 * 2, h // 2 * 2, round(t0, 2), round(t1, 2)))
    return out


def _filter_graph(out_w: int, out_h: int, boxes: list[tuple[int, int, int, int, float, float]]) -> tuple[str, str]:
    parts = [f"[0:v]scale={out_w}:{out_h},setsar=1[v0]"]
    for k, (x, y, w, h, t0, t1) in enumerate(boxes):
        sigma = max(8, min(w, h) // 5)
        parts.append(
            f"[v{k}]split=2[b{k}][s{k}];[s{k}]crop={w}:{h}:{x}:{y},gblur=sigma={sigma}[k{k}];"
            f"[b{k}][k{k}]overlay={x}:{y}:enable='between(t,{t0},{t1})'[v{k + 1}]"
        )
    return ";".join(parts), f"[v{len(boxes)}]"


def _publish(listing: dict[str, Any], video: dict[str, Any]) -> None:
    s = config.settings
    lid = listing["id"]
    index = video["upload"]
    frames = [f for f in listing["frames"] if f["upload"] == index]
    video.update(path=None, status="held", audio="removed", blurred_boxes=0, note=NOTE)
    missing = [f["id"] for f in frames if not f.get("sam")]
    if not frames or missing:
        video["detail"] = (f"Held back: SAM privacy masks are missing for {', '.join(missing) or 'every frame'}, "
                           "so not every second could be checked and blurred.")
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        video.update(status="failed", detail="ffmpeg is not installed on the server.")
        return
    fw, fh = frames[0]["width"], frames[0]["height"]
    scale = min(1.0, MAX_SIDE / max(fw, fh))
    out_w, out_h = _even(fw * scale), _even(fh * scale)
    boxes = regions(frames, video["duration"], out_w / fw, out_w, out_h)
    graph, label = _filter_graph(out_w, out_h, boxes)
    out_dir = s.media_dir / "video" / lid
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"walkthrough_{index:02d}.mp4"
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-i", str(s.uploads_dir / listing["uploads"][index - 1]["path"]),
         "-filter_complex", graph, "-map", label, "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_dir / name)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        (out_dir / name).unlink(missing_ok=True)
        video.update(status="failed", detail="The walkthrough video could not be re-encoded for publishing.")
        return
    video.update(
        path=f"video/{lid}/{name}", status="ready", width=out_w, height=out_h, blurred_boxes=len(boxes),
        detail=(f"Full walkthrough 0:00–{clock(video['duration'])} ready to publish · "
                f"{len(boxes)} privacy region(s) blurred · audio removed"),
    )


def run(listing: dict[str, Any]) -> dict[str, Any]:
    for video in listing.get("videos") or []:
        _publish(listing, video)
    return listing


def public(listing: dict[str, Any]) -> dict[str, Any] | None:
    """The primary published video for the listing page, or None."""
    for video in listing.get("videos") or []:
        if video.get("status") == "ready" and video.get("path"):
            return {"path": video["path"], "duration": video["duration"], "width": video["width"],
                    "height": video["height"], "upload": video["upload"], "note": video.get("note")}
    return None
