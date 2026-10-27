import io
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import meta_client
from main import create_app
from tests.fake_meta import FakeMeta


def make_photo(seed: int, size: tuple[int, int] = (320, 180)) -> bytes:
    """A real test image with high-frequency content everywhere (so blur is measurable)."""
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    w, h = size
    for y in range(h):
        for x in range(0, w, 8):
            shade = (x * 7 + y * 5 + seed * 31) % 256
            draw.rectangle([x, y, min(x + 7, w), y], fill=(shade, (shade + seed * 40) % 256, 255 - shade))
    for i in range(4):
        cx, cy = (seed * 53 + i * 67) % w, (seed * 29 + i * 41) % h
        draw.ellipse([cx, cy, cx + 30, cy + 20], outline=(255, 255, 255), width=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path: Path, request):
    knobs = getattr(request, "param", None) or {}
    fake = FakeMeta(**knobs)
    meta_client.set_client(fake)
    app = create_app(data_dir=tmp_path / "data", stage_delay=0)
    with TestClient(app) as c:
        c.fake_meta = fake
        yield c
    meta_client.set_client(None)


@pytest.fixture
def client_no_meta(tmp_path: Path):
    meta_client.set_client(meta_client.MetaClient(api_key=None))
    app = create_app(data_dir=tmp_path / "data", stage_delay=0)
    with TestClient(app) as c:
        yield c
    meta_client.set_client(None)


@pytest.fixture(scope="session")
def walkthrough_video(tmp_path_factory) -> Path:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    out = tmp_path_factory.mktemp("video") / "walkthrough.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=4:size=640x360:rate=24",
         "-pix_fmt", "yuv420p", str(out)],
        check=True,
    )
    return out


def wait_for_job(client: TestClient, job_id: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")
