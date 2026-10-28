"""Frame extraction: photos pass through, videos are sampled with ffmpeg at ~1 fps.

Raw frames land in raw_frames_dir/<lid>/ and are never served; only blurred copies
reach media_dir later. Near-duplicates are dropped via an 8x8 average hash
(Hamming distance <= 5 vs the previous kept frame).
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

import checklist
import config
from pipeline import PipelineError

HASH_MAX_DISTANCE = 5


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


def _sample_video(src: Path, out_dir: Path, prefix: str, limit: int) -> list[Path]:
    s = config.settings
    duration = video_duration(src)
    if duration > s.max_video_seconds:
        raise PipelineError(
            f"{src.name} is {duration:.0f}s long; the limit is {s.max_video_seconds}s. Trim it or upload photos."
        )
    result = subprocess.run(
        [
            _require("ffmpeg"), "-nostdin", "-loglevel", "error", "-i", str(src),
            "-vf", "fps=1,scale='min(1600,iw)':-2", "-frames:v", str(limit), "-q:v", "3",
            str(out_dir / f"{prefix}_%03d.jpg"),
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise PipelineError(f"Frames could not be extracted from {src.name}.")
    return sorted(out_dir.glob(f"{prefix}_*.jpg"))


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


def extract(listing: dict[str, Any]) -> dict[str, Any]:
    s = config.settings
    lid = listing["id"]
    raw_dir = s.raw_frames_dir / lid
    raw_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[Path, float | None, int]] = []
    for index, upload in enumerate(listing["uploads"], start=1):
        remaining = s.max_frames - len(candidates)
        if remaining <= 0:
            break
        src = s.uploads_dir / upload["path"]
        if upload["kind"] == "photo":
            dest = raw_dir / f"p{index:02d}{src.suffix.lower()}"
            shutil.copyfile(src, dest)
            candidates.append((dest, None, index))
        else:
            for path in _sample_video(src, raw_dir, f"v{index:02d}", remaining):
                t = float(int(path.stem.rsplit("_", 1)[-1]) - 1)
                candidates.append((path, t, index))
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

    names = [u["name"] for u in listing["uploads"]]
    source = names[0] if len(names) == 1 else f"{len(names)} uploads"
    detail = f"{len(frames)} frames from {source}"
    if dropped:
        detail += f", {dropped} near-duplicates dropped"
    checklist.set_item(listing, "frames", "generated", detail)
    return listing
