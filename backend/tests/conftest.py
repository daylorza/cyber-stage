import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import create_app

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc0f01f0005000201a5f6a1f60000000049454e44ae426082"
)


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "data", stage_delay=0)
    with TestClient(app) as c:
        yield c


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
