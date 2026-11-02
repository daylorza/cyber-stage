"""Next-batch tests (To-do 15 parallel prep, To-do 3 tracking). All Meta calls are stubbed
by the FakeMeta fixture — no live Meta calls, no credits spent."""

from tests.conftest import wait_for_job
from tests.test_stage2 import publish_listing


def _prepare_live(client):
    lid = publish_listing(client)
    res = client.post(f"/api/listings/{lid}/live", json={})
    assert res.status_code == 202, res.text
    job = wait_for_job(client, res.json()["job_id"])
    assert job["status"] == "done", job
    return lid, client.get(f"/api/listings/{lid}/live").json()


def test_live_prep_keeps_all_styles_available(client):
    """To-do 15 parity: concurrent style prep produces the same four available styles."""
    lid, body = _prepare_live(client)
    assert body["status"] == "ready"
    for room in body["rooms"]:
        assert set(room["styles"]) == {"modern-luxury", "coastal", "minimal", "2142"}
        for style_id, entry in room["styles"].items():
            assert entry["available"] is True and entry["image"], (style_id, entry)


def test_live_prep_records_tracking_and_verified_counts(client):
    """To-do 3: one durable record per newly prepared image, verified count only."""
    lid, body = _prepare_live(client)
    tracking = body["tracking"]
    assert tracking["rooms"], "base geometry must be recorded once per room"
    images = tracking["images"]
    assert images, "staging-time records must exist for the prepared images"
    for key, record in images.items():
        room_id, style_id, image_hash = key.split(":", 2)
        assert record["listing_id"] == lid
        assert record["room_id"] == room_id and record["style_id"] == style_id
        assert record["image"] and len(image_hash) == 64  # sha256 of the staged image
        verified = [o for o in record["objects"] if o["status"] == "verified"]
        assert record["verified_count"] == len(verified)
        assert all(o["status"] in {"verified", "not found"} for o in record["objects"])
        assert all("box" in o for o in verified)  # mask positions recorded
    versions = client.get(f"/api/listings/{lid}/live/versions").json()["versions"]
    for room in body["rooms"]:
        for style_id, entry in room["styles"].items():
            current = next(v for v in versions[f"{room['id']}:{style_id}"] if v["is_current"])
            assert current["objects_added_verified"] == len(entry["pieces"]), current


def test_tracking_ignores_missing_images(client):
    """To-do 3: no record and no invented count for an image that is not on disk."""
    import live

    listing = {"id": "track_missing", "live": {}}
    live._record_tracking(listing, {"id": "r1"}, None, "coastal",
                          {"image": "live/nope/missing.jpg", "pieces": [{"concept": "sofa"}]})
    assert listing["live"].get("tracking", {}).get("images", {}) == {}
