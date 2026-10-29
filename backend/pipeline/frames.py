"""Frame extraction: photos pass through, videos are sampled with ffmpeg at 1 fps over their
WHOLE length. There is no frame cap: a 56-second walkthrough yields ~56 frames. If the
extracted frames stop short of the video's end, the job fails instead of publishing part
of the walkthrough as if it were the whole home.

Raw frames land in raw_frames_dir/<lid>/ and are never served; only blurred copies
reach media_dir later. Near-duplicates are dropped via an 8x8 average hash
(Hamming distance <= 5 vs the previous kept frame).
"""

import bisect
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

import checklist
import config
from pipeline import PipelineError

HASH_MAX_DISTANCE = 5
VIDEO_FPS = 1.0
# The last extracted frame must land within this many seconds of the video's end.
TAIL_TOLERANCE = 2.0


def clock(seconds: float | None) -> str:
    if seconds is None:
        return "-:--"
    s = max(0, round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def _require(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise PipelineError(f"{binary} is not installed on the server.")
    return path


def video_duration(src: Path) -> float:
    out = subprocess.run(
        [_require("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(src)],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise PipelineError(f"{src.name} could not be read as a video.") from None


def _packet_times(src: Path) -> list[float]:
    """Presentation times of every video frame, relative to the start of the file."""
    out = subprocess.run(
        [_require("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
         "packet=pts_time:format=start_time", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True, check=False,
    )
    values = []
    for line in out.stdout.split():
        try:
            values.append(float(line.strip(",")))
        except ValueError:
            continue
    if len(values) < 2:
        return []
    start = values[-1]  # format start_time is printed last
    return sorted(v - start for v in values[:-1])


def slot_time(slot: int, packets: list[float]) -> float:
    """When the frame ffmpeg's fps filter kept for this one-second slot was actually filmed.
    The filter keeps the LAST frame that rounds into the slot, i.e. the last one before
    slot + 0.5 s (35.467 s for slot 35 at 30 fps), not the frame at the slot's start."""
    i = bisect.bisect_left(packets, slot + 0.5 / VIDEO_FPS)
    return round(packets[i - 1], 3) if i > 0 else float(slot)


def check_coverage(name: str, duration: float, times: list[float]) -> dict[str, Any]:
    """Frames must cover the whole video: about one per second, the last one at the end."""
    expected = max(1, math.floor(duration * VIDEO_FPS))
    first = min(times) if times else None
    last = max(times) if times else None
    if len(times) < expected or last is None or last < duration - TAIL_TOLERANCE:
        raise PipelineError(
            f"{name}: frames stop at {clock(last)} of a {duration:.1f}s video "
            f"({len(times)} of ~{expected} expected). Stopped rather than publish part of the walkthrough."
        )
    return {"duration": round(duration, 2), "fps": VIDEO_FPS, "extracted": len(times),
            "expected": expected, "first_t": first, "last_t": last}


def _sample_video(src: Path, out_dir: Path, prefix: str, name: str) -> tuple[list[tuple[Path, float]], dict]:
    s = config.settings
    duration = video_duration(src)
    if duration > s.max_video_seconds:
        raise PipelineError(
            f"{src.name} is {duration:.0f}s long; the limit is {s.max_video_seconds}s. Trim it or upload photos."
        )
    for stale in out_dir.glob(f"{prefix}_*.jpg"):
        stale.unlink()
    result = subprocess.run(
        [
            _require("ffmpeg"), "-nostdin", "-loglevel", "error", "-i", str(src),
            "-vf", f"fps={VIDEO_FPS:g},scale='min(1600,iw)':-2", "-q:v", "3",
            str(out_dir / f"{prefix}_%03d.jpg"),
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise PipelineError(f"Frames could not be extracted from {src.name}.")
    packets = _packet_times(src)
    samples = [
        (path, slot_time(int(path.stem.rsplit("_", 1)[-1]) - 1, packets) if packets
         else (int(path.stem.rsplit("_", 1)[-1]) - 1) / VIDEO_FPS)
        for path in sorted(out_dir.glob(f"{prefix}_*.jpg"))
    ]
    return samples, check_coverage(name, duration, [t for _, t in samples])


def _probe(path: Path) -> tuple[tuple[int, int], int, float]:
    """(size, 8x8 average hash, edge-variance sharpness) in one open."""
    with Image.open(path) as img:
        size = img.size
        gray = img.convert("L")
        pixels = list(gray.resize((8, 8)).tobytes())
        avg = sum(pixels) / len(pixels)
        hashed = 0
        for p in pixels:
            hashed = (hashed << 1) | (p > avg)
        edges = gray.filter(ImageFilter.FIND_EDGES)
        sharpness = round(ImageStat.Stat(edges).var[0], 1)
    return size, hashed, sharpness


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def coverage_line(video: dict[str, Any]) -> str:
    """One line for the console and logs: duration, frames extracted, first/last timestamp."""
    return (f"Video {video['duration']:.1f}s · {video['extracted']} frames extracted at "
            f"{video['fps']:g} fps · first {clock(video['first_t'])} · last {clock(video['last_t'])} · "
            f"{video.get('kept', video['extracted'])} kept after near-duplicates")


def extract(listing: dict[str, Any]) -> dict[str, Any]:
    s = config.settings
    lid = listing["id"]
    raw_dir = s.raw_frames_dir / lid
    raw_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[Path, float | None, int]] = []
    videos: list[dict[str, Any]] = []
    photos = 0
    for index, upload in enumerate(listing["uploads"], start=1):
        src = s.uploads_dir / upload["path"]
        if upload["kind"] == "photo":
            if photos >= s.max_photos:
                continue
            photos += 1
            dest = raw_dir / f"p{index:02d}{src.suffix.lower()}"
            shutil.copyfile(src, dest)
            candidates.append((dest, None, index))
        else:
            samples, coverage = _sample_video(src, raw_dir, f"v{index:02d}", upload.get("name") or src.name)
            videos.append({"upload": index, **coverage})
            candidates.extend((path, t, index) for path, t in samples)
    if not candidates:
        raise PipelineError("No frames could be extracted from the upload.")

    frames: list[dict[str, Any]] = []
    previous_hash: int | None = None
    dropped = 0
    for path, t, upload_index in candidates:
        (width, height), hashed, sharpness = _probe(path)
        if previous_hash is not None and _hamming(hashed, previous_hash) <= HASH_MAX_DISTANCE:
            path.unlink()
            dropped += 1
            continue
        previous_hash = hashed
        frames.append({
            "id": f"f{len(frames) + 1:02d}",
            "raw": path.name,
            "path": None,
            "t": t,
            "upload": upload_index,
            "width": width,
            "height": height,
            "sharpness": sharpness,
            "sam": None,
            "wonder": None,
            "blur": None,
        })
    if not frames:
        raise PipelineError("All extracted frames were near-duplicates.")
    listing["frames"] = frames
    for video in videos:
        video["kept"] = sum(1 for f in frames if f["upload"] == video["upload"])
    listing["videos"] = videos

    names = [u["name"] for u in listing["uploads"]]
    source = names[0] if len(names) == 1 else f"{len(names)} uploads"
    detail = f"{len(frames)} frames from {source}"
    if dropped:
        detail += f", {dropped} near-duplicates dropped"
    if videos:
        detail += f" · {coverage_line(videos[0])}"
    checklist.set_item(listing, "frames", "generated", detail)
    return listing
