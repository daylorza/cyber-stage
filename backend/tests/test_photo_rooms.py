"""Each uploaded photo is staged as its own room; terraces in frame get outdoor furniture."""

import pytest

from pipeline import stage
from tests.conftest import wait_for_job
from tests.test_stage0 import upload_photos, upload_video


@pytest.mark.parametrize("client", [{"layout": ["living"]}], indirect=True)
def test_photos_of_same_room_are_each_staged(client):
    # Wonder (fake) labels every frame living_1, as it did for two angles of one room.
    ids = upload_photos(client, count=2)
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{ids['listing_id']}").json()
    assert {f["wonder"]["room_key"] for f in listing["frames"]} == {"living_1"}
    rooms = listing["rooms"]
    assert [r["name"] for r in rooms] == ["Living room", "Living room 2"]
    assert [r["source_frame"] for r in rooms] == ["f01", "f02"]
    assert all(r["after"] for r in rooms)
    assert sum(r["main"] for r in rooms) == 1


@pytest.mark.parametrize("client", [{"layout": ["living"]}], indirect=True)
def test_video_frames_of_one_room_still_merge(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{ids['listing_id']}").json()
    assert len(listing["rooms"]) == 1 and len(listing["rooms"][0]["frames"]) > 1


def test_outdoor_note_only_for_dry_rooms_in_listing_styles():
    assert stage.OUTDOOR_NOTE in stage.prompt_for("modern-luxury", {"type": "living"})
    assert stage.OUTDOOR_NOTE in stage.prompt_for("coastal", {"type": "bedroom"})
    assert stage.OUTDOOR_NOTE not in stage.prompt_for("modern-luxury", {"type": "kitchen"})
    assert stage.OUTDOOR_NOTE not in stage.prompt_for("2142", {"type": "living"})
    # The empty-plate prompt reuses GEOMETRY_RULES and must never add furniture.
    assert stage.OUTDOOR_NOTE not in stage.GEOMETRY_RULES
