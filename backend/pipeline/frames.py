"""Frame extraction: photos pass through, videos are sampled with ffmpeg at ~1 fps.

Stage 1 adds scene-change detection and near-duplicate removal.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import config
from pipeline import PipelineError


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


def extract(listing: dict[str, Any]) -> dict[str, Any]:
    s = config.settings
    out_dir = s.media_dir / "frames" / listing["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for index, upload in enumerate(listing["uploads"], start=1):
        remaining = s.max_frames - len(frames)
        if remaining <= 0:
            break
        src = s.uploads_dir / upload["path"]
        if upload["kind"] == "photo":
            dest = out_dir / f"p{index:02d}{src.suffix.lower()}"
            shutil.copyfile(src, dest)
            frames.append(dest)
        else:
            frames.extend(_sample_video(src, out_dir, f"v{index:02d}", remaining))
    if not frames:
        raise PipelineError("No frames could be extracted from the upload.")
    listing["frames"] = [str(f.relative_to(s.media_dir)) for f in frames]
    return listing
