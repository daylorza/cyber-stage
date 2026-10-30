"""Demo mode (default): checks run and flag, but open items never block Approve/Publish on uploads."""

import pytest

from tests.conftest import wait_for_job
from tests.test_stage0 import upload_photos
from verify import WARNING_RESOLUTION

DEMO = {"blocking_checks": False, "bad_claim": True}


def _flagged_upload(client):
    ids = upload_photos(client, count=2)
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{ids['listing_id']}").json()
    assert listing["verification"]["flags"], "bad_claim should leave an open flag"
    return listing


@pytest.mark.parametrize("client", [DEMO], indirect=True)
def test_demo_mode_approves_and_publishes_with_open_flags(client):
    assert client.get("/api/settings").json() == {"blocking_checks": False}
    listing = _flagged_upload(client)
    lid = listing["id"]
    assert not any("cannot publish" in f["resolution"] for f in listing["verification"]["flags"])

    res = client.post(f"/api/listings/{lid}/review", json={"action": "approve"})
    assert res.status_code == 200, res.text
    approved = res.json()
    assert approved["status"] == "approved"
    assert "Every claim has evidence" in approved["review"]["open_checks"]
    assert approved["verification"]["flags"], "flags stay visible after approval"

    res = client.post(f"/api/listings/{lid}/publish")
    assert res.status_code == 200, res.text
    page = client.get(f"/api/listings/{lid}/page").json()
    assert page["verification"]["passed"] is False      # never shown as verified
    assert page["verification"]["open"] >= 1

    text = client.get(f"/api/listings/{lid}/export").text
    assert "Checks mode: warnings only (demo mode)" in text
    assert "Approved with open checks: Every claim has evidence" in text


@pytest.mark.parametrize("client", [{"blocking_checks": False}], indirect=True)
def test_demo_mode_keeps_seeded_placeholders_blocked(client):
    assert client.post("/api/listings/seed_miami/review", json={"action": "approve"}).status_code == 409


@pytest.mark.parametrize("client", [{"bad_claim": True}], indirect=True)
def test_blocking_mode_still_blocks(client):
    assert client.get("/api/settings").json() == {"blocking_checks": True}
    listing = _flagged_upload(client)
    assert client.post(f"/api/listings/{listing['id']}/review", json={"action": "approve"}).status_code == 409
    assert client.post(f"/api/listings/{listing['id']}/publish").status_code == 409


def test_default_flag_wording_follows_mode():
    import config
    from verify import DEFAULT_RESOLUTION, _Ctx

    upload, seed = {"source": "upload"}, {"source": "seed"}
    config.configure(data_dir=config.settings.data_dir, blocking_checks=False)
    assert _Ctx(upload, use_meta=False).default_resolution == WARNING_RESOLUTION
    assert _Ctx(seed, use_meta=False).default_resolution == DEFAULT_RESOLUTION
    config.configure(data_dir=config.settings.data_dir, blocking_checks=True)
    assert _Ctx(upload, use_meta=False).default_resolution == DEFAULT_RESOLUTION
