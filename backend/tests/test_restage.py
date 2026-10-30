"""Per-room re-stage with a stricter prompt: flagged room -> new Meta call -> re-verify."""

import pytest

import config
import meta_client
from pipeline import stage
from tests.conftest import wait_for_job
from tests.test_stage0 import upload_photos
from verify import checks


def _rooms(listing):
    return {r["id"]: r for r in listing["rooms"]}


def _staging_flags(listing, room_id):
    return [
        c for c in (listing.get("verification") or {}).get("checks") or []
        if c["item"] == "staging_geometry"
        and (c.get("target") or {}).get("room") == room_id
        and c["status"] != "pass"
    ]


@pytest.mark.parametrize("client", [{"warp_room": "room_2", "fix_at_level": 1}], indirect=True)
def test_restage_fixes_flagged_room(client):
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    before = client.get(f"/api/listings/{lid}").json()
    before_rooms = _rooms(before)
    assert _staging_flags(before, "room_2"), "room_2 should be flagged by the warped staging"
    old_after = before_rooms["room_2"]["after"]
    room1_after_bytes = (config.settings.media_dir / before_rooms["room_1"]["after"]).read_bytes()

    res = client.post(f"/api/listings/{lid}/rooms/room_2/restage")
    assert res.status_code == 202, res.text
    assert res.json()["level"] == 1 and res.json()["room_id"] == "room_2"
    job = wait_for_job(client, res.json()["job_id"])
    assert job["status"] == "done" and job["stage"] == "ready", job

    listing = client.get(f"/api/listings/{lid}").json()
    rooms = _rooms(listing)
    room_2 = rooms["room_2"]
    assert listing["status"] == "draft"
    assert room_2["after"].endswith("_strict1.jpg")
    assert (config.settings.media_dir / room_2["after"]).is_file()
    assert (config.settings.media_dir / old_after).is_file(), "old staged file is kept on disk"
    assert room_2["staging"]["level"] == 1
    assert room_2["staging"]["purpose"] == "image.restage"
    assert room_2["staging"]["error"] is None
    assert room_2["staging"]["prompt"] != stage.prompt_for(listing["style"])
    assert stage.STRICT_FRAMING in room_2["staging"]["prompt"]
    history = room_2["staging_history"]
    assert len(history) == 1 and history[0]["after"] == old_after and history[0]["replaced_at"]
    assert "restage_error" not in room_2
    assert not _staging_flags(listing, "room_2"), _staging_flags(listing, "room_2")

    # Only this room changed.
    assert rooms["room_1"] == before_rooms["room_1"]
    assert (config.settings.media_dir / rooms["room_1"]["after"]).read_bytes() == room1_after_bytes
    restage_traces = [t for t in listing["trace"] if t["purpose"] == "image.restage"]
    assert len(restage_traces) == 1
    assert restage_traces[0]["target"] == {"room": "room_2", "level": 1}
    assert restage_traces[0]["cached"] is False and restage_traces[0]["ok"]

    # A broker "Re-run checks" afterwards still sees room_2 clean.
    res = client.post(f"/api/listings/{lid}/verify")
    assert res.status_code == 202
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    assert not _staging_flags(listing, "room_2")

    text = client.get(f"/api/listings/{lid}/export").text
    assert "Muse Image re-stage (stricter)" in text
    assert room_2["after"] in text


@pytest.mark.parametrize("client", [{"warp_room": "room_2", "fix_at_level": 2}], indirect=True)
def test_restage_second_attempt_and_cap(client):
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    res = client.post(f"/api/listings/{lid}/rooms/room_2/restage")
    assert res.status_code == 202 and res.json()["level"] == 1
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    room_2 = _rooms(listing)["room_2"]
    assert room_2["staging"]["level"] == 1
    assert _staging_flags(listing, "room_2"), "first stricter attempt still warps here"

    res = client.post(f"/api/listings/{lid}/rooms/room_2/restage")
    assert res.status_code == 202 and res.json()["level"] == 2
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    room_2 = _rooms(listing)["room_2"]
    assert room_2["staging"]["level"] == 2
    assert room_2["after"].endswith("_strict2.jpg")
    assert room_2["staging"]["prompt"] != room_2["staging_history"][1]["prompt"]
    assert not _staging_flags(listing, "room_2")
    level2_traces = [
        t for t in listing["trace"]
        if t["purpose"] == "image.restage" and t["target"].get("level") == 2
    ]
    assert len(level2_traces) == 1 and level2_traces[0]["cached"] is False

    assert client.post(f"/api/listings/{lid}/rooms/room_2/restage").status_code == 409


@pytest.mark.parametrize("client", [{"warp_room": "room_2"}], indirect=True)
def test_restage_refusals(client):
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    assert client.post(f"/api/listings/{lid}/rooms/room_1/restage").status_code == 409
    assert client.post(f"/api/listings/{lid}/rooms/room_99/restage").status_code == 404
    assert client.post("/api/listings/lst_nope/rooms/room_2/restage").status_code == 404
    assert client.post("/api/listings/seed_miami/rooms/room_1/restage").status_code in (404, 409)

    res = client.post(f"/api/listings/{lid}/rooms/room_2/restage")
    assert res.status_code == 202
    assert client.post(f"/api/listings/{lid}/rooms/room_2/restage").status_code == 409
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"

    res = client.post(f"/api/listings/{lid}/review",
                      json={"action": "save", "rejected_rooms": ["room_2"]})
    assert res.status_code == 200
    assert client.post(f"/api/listings/{lid}/rooms/room_2/restage").status_code == 409

    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    assert client.post(f"/api/listings/{lid}/publish").status_code == 200
    assert client.post(f"/api/listings/{lid}/rooms/room_1/restage").status_code == 409


@pytest.mark.parametrize("client", [{"warp_room": "room_2", "fail_restage": True}], indirect=True)
def test_restage_failure_preserves_room(client):
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    before = _rooms(client.get(f"/api/listings/{lid}").json())["room_2"]
    res = client.post(f"/api/listings/{lid}/rooms/room_2/restage")
    assert res.status_code == 202 and res.json()["level"] == 1
    job = wait_for_job(client, res.json()["job_id"])
    assert job["status"] == "failed" and job["error"], job

    listing = client.get(f"/api/listings/{lid}").json()
    room_2 = _rooms(listing)["room_2"]
    assert listing["status"] == "draft"
    assert room_2["after"] == before["after"]
    assert room_2["staging"] == before["staging"]
    assert room_2["restage_error"]["level"] == 1
    assert "boom" in room_2["restage_error"]["error"]
    assert room_2["restage_error"]["at"]
    assert "staging_history" not in room_2

    # The failed attempt did not consume the level.
    res = client.post(f"/api/listings/{lid}/rooms/room_2/restage")
    assert res.status_code == 202 and res.json()["level"] == 1
    assert wait_for_job(client, res.json()["job_id"])["status"] == "failed"


def test_verifier_thresholds_unchanged():
    assert checks.GEOMETRY_MIN_CORR == 0.25
    assert checks.STRUCTURE_IOU == 0.3
    assert checks.ASPECT_MAX_DEVIATION == 0.03


def test_restage_prompt_building_blocks():
    room = {"id": "room_2", "name": "Kitchen", "type": "kitchen"}
    frame = {
        "id": "f02",
        "sam": {
            "privacy": [],
            "structure": [
                {"concept": "door", "box": [0, 0, 10, 10], "score": 0.9} for _ in range(9)
            ],
        },
    }
    p1 = stage.restage_prompt("modern-luxury", room, frame, 1)
    assert "9 door(s)" in p1 and "0 window(s)" in p1
    assert "This is a kitchen:" in p1
    assert stage.STRICT_FRAMING in p1 and stage.STRICT_STRUCTURE in p1

    p2 = stage.restage_prompt("modern-luxury", room, frame, 2)
    assert "on the countertop or island" in p2
    assert "in a modern luxury style" in p2
    assert "9 door(s)" in p2

    base = stage.prompt_for("modern-luxury")
    assert len({p1, p2, base}) == 3
    key = lambda p: meta_client.cache_key("muse-image-1.0", "image.restage", p, [b"x"])
    assert key(p1) != key(p2) != key(base)

    bare = stage.restage_prompt("minimal", {"id": "r1", "type": "bedroom"}, None, 1)
    assert "door(s)" not in bare and "This is a" not in bare
    assert "on the vanity countertop" in stage.restage_prompt(
        "modern-luxury", {"id": "r2", "type": "bathroom"}, frame, 2)
