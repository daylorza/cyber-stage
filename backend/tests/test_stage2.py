"""Stage 2 acceptance: Live-In-It preparation job, gated endpoints, payload contract."""

import pytest

import config
import db
from tests.conftest import wait_for_job
from tests.test_stage0 import upload_photos  # FACTS there are already Miami facts


def publish_listing(client) -> str:
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    assert client.post(f"/api/listings/{lid}/publish").status_code == 200
    return lid


def request_and_wait(client, lid: str) -> dict:
    # Seeded home-page residences were removed: prepare without a residence link.
    res = client.post(f"/api/listings/{lid}/live", json={})
    assert res.status_code == 202, res.text
    return wait_for_job(client, res.json()["job_id"])


def test_live_gating(client):
    ids = upload_photos(client, count=1)
    lid = ids["listing_id"]
    wait_for_job(client, ids["job_id"])

    # Draft listing: request refused, payload absent.
    res = client.post(f"/api/listings/{lid}/live", json={})
    assert res.status_code == 409
    assert client.get(f"/api/listings/{lid}/live").status_code == 404

    # No seeded home-page residences exist anymore: any residence link is 422,
    # and the residence-scoped endpoint always 404s.
    published = publish_listing(client)
    res = client.post(f"/api/listings/{published}/live", json={"residence": "seed_miami"})
    assert res.status_code == 422
    assert "no seeded" in res.json()["detail"].lower()
    assert client.get(f"/api/listings/{published}/live").status_code == 404
    assert client.get("/api/residences/seed_miami/live").status_code == 404
    assert client.get("/api/residences/seed_los_angeles/live").status_code == 404


def test_live_happy_path(client):
    lid = publish_listing(client)
    page = client.get(f"/api/listings/{lid}/page").json()
    snapshot = client.get(f"/api/listings/{lid}").json()
    for key in ("updated_at", "live", "job"):
        snapshot.pop(key, None)

    res = client.post(f"/api/listings/{lid}/live", json={})
    assert res.status_code == 202, res.text
    live_job_id = res.json()["job_id"]

    # While preparing, the payload exists but rooms/moments stay empty.
    res = client.post(f"/api/listings/{lid}/live", json={})
    assert res.status_code == 409
    job = wait_for_job(client, live_job_id)
    assert job["status"] == "done", job
    assert job["stage"] == "ready" and job["progress"] == 100

    body = client.get(f"/api/listings/{lid}/live").json()
    assert body["status"] == "ready" and body["error"] is None
    assert body["listing_id"] == lid and body["residence"] is None
    assert body["job_id"] == live_job_id and body["prepared_at"]
    assert body["title"] == page["title"]
    assert body["facts"] == page["facts"]
    assert body["price_display"] == "$4,250,000"
    assert body["approved_at"] and body["published_at"]
    # No seeded placeholder note anymore: upload listings carry no note unless labeled.
    assert body["note"] is None
    assert [s["id"] for s in body["styles"]] == ["modern-luxury", "coastal", "minimal", "2142"]
    assert body["default_style"] == "modern-luxury"
    assert body["calls"] > 0 and sum(body["calls_by_purpose"].values()) <= body["calls"]
    assert all(p.startswith("live.") for p in body["calls_by_purpose"])

    published_rooms = page["rooms"]
    assert [r["id"] for r in body["rooms"]] == [r["id"] for r in published_rooms]
    for room, published_room in zip(body["rooms"], published_rooms):
        assert room["name"] == published_room["name"] and room["type"] == published_room["type"]
        assert room["before"] == published_room["before"]
        assert room["plate"] == room["before"] and room["plate_source"] == "before"
        assert room["plate_check"] is None and room["plate_furnished"] is False
        assert set(room["styles"]) == {"modern-luxury", "coastal", "minimal", "2142"}
        assert isinstance(room["size"], list) and len(room["size"]) == 2
        for style_id, entry in room["styles"].items():
            if style_id == "modern-luxury":
                assert entry["source"] == "stage1"
                assert entry["image"] == published_room["after"]
            else:
                assert entry["source"] == "live"
                path = config.settings.media_dir / entry["image"]
                assert path.is_file(), entry
                assert client.get(f"/api/media/{entry['image']}").status_code == 200
            assert entry["available"] is True and entry["error"] is None
            assert entry["geometry"]["status"] == "pass"
            assert entry["structure"]["status"] == "pass"
            assert entry["pieces"], entry
            for piece in entry["pieces"]:
                assert piece["concept"] and len(piece["box"]) == 4
                assert all(0.0 <= v <= 1.0 for v in piece["box"])

    moments = {m["id"]: m for m in body["moments"]}
    assert moments["view"]["label"] == "Look out at the view"
    view_room = next(r for r in body["rooms"] if r["id"] == moments["view"]["room_id"])
    assert moments["view"]["focus"] == view_room["window"]
    assert "sit" in moments and moments["sit"]["label"] == "Sit down"
    assert "coffee" in moments and moments["coffee"]["label"] == "Make coffee"
    assert moments["coffee"]["images"], moments["coffee"]
    for rel in moments["coffee"]["images"].values():
        assert (config.settings.media_dir / rel).is_file()

    # No seeded residences: the residence-scoped endpoint stays empty.
    assert client.get("/api/residences/seed_miami/live").status_code == 404

    # Stage 1 data is untouched: identical except updated_at/live/job.
    after = client.get(f"/api/listings/{lid}").json()
    for key in ("updated_at", "live", "job"):
        after.pop(key, None)
    assert after == snapshot
    assert after["status"] == "published"


@pytest.mark.parametrize("client", [{"furnished_before": True}], indirect=True)
def test_furnished_room_gets_empty_plate(client):
    lid = publish_listing(client)
    job = request_and_wait(client, lid)
    assert job["status"] == "done", job
    body = client.get(f"/api/listings/{lid}/live").json()
    assert body["status"] == "ready"
    for room in body["rooms"]:
        assert room["plate_source"] == "generated", room
        assert room["plate"] == f"live/{lid}/{room['id']}_empty.jpg"
        assert (config.settings.media_dir / room["plate"]).is_file()
        assert room["plate_check"]["status"] == "pass"
        assert room["plate_furnished"] is False  # the plate shown is the emptied one


@pytest.mark.parametrize("client", [{"warp_live": True}], indirect=True)
def test_warped_style_marked_unavailable(client):
    lid = publish_listing(client)
    job = request_and_wait(client, lid)
    assert job["status"] == "done", job
    body = client.get(f"/api/listings/{lid}/live").json()
    assert body["status"] == "ready"
    for room in body["rooms"]:
        coastal = room["styles"]["coastal"]
        assert coastal["available"] is False and coastal["attempts"] == 2
        assert coastal["geometry"]["status"] == "fail"
        for other in ("modern-luxury", "minimal"):
            assert room["styles"][other]["available"] is True


@pytest.mark.parametrize("client", [{"warp_live_once": True}], indirect=True)
def test_drifted_style_is_retried_once(client):
    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    body = client.get(f"/api/listings/{lid}/live").json()
    for room in body["rooms"]:
        coastal = room["styles"]["coastal"]
        assert coastal["available"] is True and coastal["attempts"] == 2
        assert coastal["geometry"]["status"] == "pass" and coastal["pieces"]
        assert room["styles"]["minimal"]["attempts"] == 1
        assert room["styles"]["modern-luxury"]["attempts"] == 1


@pytest.mark.parametrize("client", [{"fail_live_image": True}], indirect=True)
def test_failed_live_images_degrade_per_style(client):
    lid = publish_listing(client)
    job = request_and_wait(client, lid)
    assert job["status"] == "done", job
    body = client.get(f"/api/listings/{lid}/live").json()
    assert body["status"] == "ready"
    for room in body["rooms"]:
        assert room["styles"]["modern-luxury"]["available"] is True
        for style_id in ("coastal", "minimal", "2142"):
            entry = room["styles"][style_id]
            assert entry["available"] is False and entry["error"]
            assert entry["image"] is None


def test_reserve_reports_no_payment(client):
    lid = publish_listing(client)
    res = client.post(f"/api/listings/{lid}/reserve")
    assert res.status_code == 201, res.text
    hold = res.json()
    assert hold["simulated"] is True and hold["charged"] is False
    assert hold["payment_taken"] is False and hold["provider"] is None
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM reservations WHERE listing_id = ?", (lid,)
        ).fetchone()
    assert row is not None and row["simulated"] == 1


def test_no_banned_names_in_product_code():
    root = config.REPO_DIR
    targets = (
        [p for p in (root / "frontend" / "src").rglob("*") if p.is_file()]
        + [p for p in (root / "seed").rglob("*") if p.is_file()]
        + list((root / "backend").glob("*.py"))
        + [p for p in (root / "backend" / "pipeline").rglob("*.py") if p.is_file()]
        + [p for p in (root / "backend" / "verify").rglob("*.py") if p.is_file()]
    )
    assert targets, "guard scanned no files"
    banned = ("london", "teleport", "lumina")
    # "london" is allowed ONLY in the home-menu entries (Day's explicit Oct 31
    # direction: Miami / Los Angeles / London are separate spaces); banned elsewhere.
    menu = root / "frontend" / "src" / "residences.ts"
    for path in targets:
        text = path.read_text(errors="ignore").lower()
        words = [w for w in banned if not (w == "london" and path == menu)]
        for word in words:
            assert word not in text, f"{word!r} found in {path}"
