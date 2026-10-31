"""Stage 0 acceptance, updated to Stage 1 shapes: upload -> job -> review -> publish -> page."""

from dataclasses import replace

import config
from tests.conftest import make_photo, wait_for_job

FACTS = {"address": "Test unit", "city": "Miami", "beds": "3", "baths": "2.5", "sqft": "2,400", "price": "4250000"}


def upload_video(client, video, **facts):
    with video.open("rb") as fh:
        res = client.post("/api/listings", data={**FACTS, **facts}, files=[("files", ("walk.mp4", fh, "video/mp4"))])
    assert res.status_code == 202, res.text
    return res.json()


def upload_photos(client, count=2, **facts):
    files = [("files", (f"shot{i}.png", make_photo(i + 1), "image/png")) for i in range(count)]
    res = client.post("/api/listings", data={**FACTS, **facts}, files=files)
    assert res.status_code == 202, res.text
    return res.json()


def test_upload_to_published_page(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    job = wait_for_job(client, ids["job_id"])
    assert job["status"] == "done", job
    assert job["progress"] == 100

    listing = client.get(f"/api/listings/{ids['listing_id']}").json()
    assert listing["status"] == "draft"
    assert listing["facts"]["sqft"] == 2400 and listing["facts"]["beds"] == 3
    frame_ids = {f["id"] for f in listing["frames"]}
    assert 1 <= len(listing["rooms"]) <= config.settings.max_rooms
    for room in listing["rooms"]:
        assert room["source_frame"] in frame_ids
        assert room["before"] and (config.settings.media_dir / room["before"]).is_file()
        assert client.get(f"/api/media/{room['before']}").status_code == 200

    for claim in listing["copy"]["highlights"]:
        assert claim["evidence"], claim
    assert listing["copy"]["title"] == "3-bedroom residence in Miami"

    comps = listing["comps"]
    assert comps["source"] == "demo" and "not a live" in comps["label"]
    assert comps["suggested_range"]["low"] < comps["suggested_range"]["high"]

    lid = ids["listing_id"]
    assert client.post(f"/api/listings/{lid}/publish").status_code == 409
    assert client.get(f"/api/listings/{lid}/page").status_code == 404
    assert client.post(f"/api/listings/{lid}/reserve").status_code == 409

    res = client.post(f"/api/listings/{lid}/review", json={"action": "approve"})
    assert res.status_code == 200 and res.json()["status"] == "approved"

    res = client.post(f"/api/listings/{lid}/publish")
    assert res.status_code == 200 and res.json()["status"] == "published"

    page = client.get(f"/api/listings/{lid}/page").json()
    assert page["title"] == "3-bedroom residence in Miami"
    assert page["price_display"] == "$4,250,000"
    assert page["approved_at"] and page["published_at"]

    hold = client.post(f"/api/listings/{lid}/reserve").json()
    assert hold["simulated"] is True and hold["charged"] is False


def test_photo_fallback(client):
    res = client.post(
        "/api/listings",
        data={"city": "New York", "estimate_price": "true", "price": "999", "sqft": "3850", "currency": "USD"},
        files=[("files", ("living.png", make_photo(1), "image/png")), ("files", ("kitchen.png", make_photo(2), "image/png"))],
    )
    assert res.status_code == 202, res.text
    job = wait_for_job(client, res.json()["job_id"])
    assert job["status"] == "done", job
    listing = client.get(f"/api/listings/{res.json()['listing_id']}").json()
    assert len(listing["rooms"]) == 2
    assert listing["facts"]["price"] is None
    assert listing["comps"]["suggested_range"]["currency"] == "USD"


def test_broker_edits_clear_approval_and_reject_rooms(client):
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    wait_for_job(client, ids["job_id"])

    client.post(f"/api/listings/{lid}/review", json={"action": "approve"})
    edit = {"title": "Edited title", "description": "Broker wrote this.", "highlights": ["3 bedrooms", "Ocean view"]}
    listing = client.post(f"/api/listings/{lid}/review", json={"action": "save", "copy_edit": edit,
                                                             "rejected_rooms": ["room_2"]}).json()
    assert listing["status"] == "draft"
    assert listing["review"]["decision"] is None
    assert listing["rooms"][1]["rejected"] is True
    by_text = {h["text"]: h["evidence"] for h in listing["copy"]["highlights"]}
    assert by_text["3 bedrooms"][0]["kind"] == "fact"
    assert by_text["Ocean view"][0]["kind"] == "broker"
    assert client.post(f"/api/listings/{lid}/publish").status_code == 409

    client.post(f"/api/listings/{lid}/review", json={"action": "approve"})
    page_rooms = client.post(f"/api/listings/{lid}/publish").json()["published"]["rooms"]
    assert [r["id"] for r in page_rooms] == ["room_1"]
    assert client.post(f"/api/listings/{lid}/review", json={"action": "save"}).status_code == 409


def test_reject_and_unknown_rooms(client):
    ids = upload_photos(client, count=1)
    lid = ids["listing_id"]
    wait_for_job(client, ids["job_id"])
    assert client.post(f"/api/listings/{lid}/review", json={"action": "reject"}).json()["status"] == "rejected"
    bad = client.post(f"/api/listings/{lid}/review", json={"action": "save", "rejected_rooms": ["room_99"]})
    assert bad.status_code == 422


def test_rejects_unsupported_files(client):
    res = client.post("/api/listings", data=FACTS, files=[("files", ("plan.pdf", b"%PDF", "application/pdf"))])
    assert res.status_code == 415
    assert "isn't supported" in res.json()["detail"]


def test_video_over_length_limit_fails_job(client, walkthrough_video, monkeypatch):
    monkeypatch.setattr(config, "settings", replace(config.settings, max_video_seconds=1))
    ids = upload_video(client, walkthrough_video)
    job = wait_for_job(client, ids["job_id"])
    assert job["status"] == "failed" and "limit is 1s" in job["error"]
    assert client.get(f"/api/listings/{ids['listing_id']}").json()["status"] == "failed"


def test_seeded_inventory(client):
    seeds = [item for item in client.get("/api/listings").json() if item["source"] == "seed"]
    assert {item["id"] for item in seeds} == {"seed-miami", "seed-los-angeles", "seed-london"}
    assert all(client.get(f"/api/listings/{item['id']}").status_code == 200 for item in seeds)
    assert client.get("/api/listings/seed_miami").status_code == 404
    assert client.get("/api/listings/seed_los_angeles").status_code == 404
    assert client.get("/api/listings/seed_new_york").status_code == 404


def test_seeds_dropped_from_seed_file_are_removed(client):
    import db
    import listings

    stale = listings.new_listing("seed_retired", source="seed", facts={"city": "London"}, uploads=[], status="draft")
    with db.connect() as conn:
        db.insert_listing(conn, stale)
    listings.seed_inventory()
    assert db.get_listing("seed_retired") is None
    assert db.get_listing("seed_new_york") is None
