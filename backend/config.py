import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("VRE_DATA_DIR", str(BACKEND_DIR / "assets"))))
    stage_delay: float = field(default_factory=lambda: float(_env("VRE_STAGE_DELAY", "0.6")))
    max_upload_mb: int = field(default_factory=lambda: int(_env("VRE_MAX_UPLOAD_MB", "512")))
    max_video_seconds: int = field(default_factory=lambda: int(_env("VRE_MAX_VIDEO_SECONDS", "180")))
    # Demo default: checks run and flag, but only block Approve/Publish when this is on.
    blocking_checks: bool = field(default_factory=lambda: _env("VRE_BLOCKING_CHECKS", "0") == "1")
    # Videos are sampled over their WHOLE length (max_video_seconds bounds the count);
    # this caps photo uploads only.
    max_photos: int = 40
    max_rooms: int = 6
    seed_dir: Path = REPO_DIR / "seed"
    frontend_dist: Path = REPO_DIR / "frontend" / "dist"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def media_dir(self) -> Path:
        """Derived, publishable media only (frames, staged images). Raw uploads are never served."""
        return self.data_dir / "media"

    @property
    def raw_frames_dir(self) -> Path:
        """Raw extracted frames. Never publishable: deliberately outside media_dir."""
        return self.data_dir / "frames_raw"

    @property
    def staged_raw_dir(self) -> Path:
        """Staged images before the staged-faces check clears them. Never served."""
        return self.data_dir / "staged_raw"


settings = Settings()


def configure(**overrides) -> Settings:
    """Rebuild settings from environment defaults plus explicit overrides, and create data dirs."""
    global settings
    settings = Settings(**overrides)
    for path in (settings.data_dir, settings.uploads_dir, settings.media_dir,
                 settings.raw_frames_dir, settings.staged_raw_dir):
        path.mkdir(parents=True, exist_ok=True)
    return settings
