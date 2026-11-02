"""To-do 4: style images are versioned (room_1_coastal_v1.jpg, v2, ...); a rerun never overwrites."""

import config
import db
from tests.conftest import wait_for_job
from tests.test_stage2 import publish_listing, request_and_wait


def versions(client, lid: str) -> dict:
    res = client.get(f"/api/listings/{lid}/live/versions")
    assert res.status_code == 200, res.text
    return res.json()["versions"]


def rerun(client, lid: str, style: str) -> dict:
    res = client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/{style}/rerun")
    assert res.status_code == 202, res.text
    return wait_for_job(client, res.json()["job_id"])


def current_image(client, lid: str, style: str) -> str:
    return client.get(f"/api/listings/{lid}/live").json()["rooms"][0]["styles"][style]["image"]


def test_prepare_records_one_current_version_per_room_style(client):
    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    found = versions(client, lid)
    assert set(found) >= {"room_1:modern-luxury", "room_1:coastal", "room_1:minimal", "room_1:2142"}
    for key, records in found.items():
        assert sum(r["is_current"] for r in records) == 1, key
        for r in records:
            assert r["model"] == "muse-image-1.0"
            assert r["preset_id"] == key.split(":")[1] and r["preset_version"]
            assert r["created_at"] and r["created_by"]
            assert r["checker"]["geometry"]["status"] == "pass"
            assert r["objects_added_verified"] is None, "no verified count until To-do 3"
            assert "entry" not in r
    stage1 = found["room_1:modern-luxury"][0]
    assert stage1["broker_approved"] is True and stage1["created_by"] == "stage 1 (broker-approved)"
    coastal = found["room_1:coastal"][0]
    assert coastal["version"] == 1 and coastal["image"] == f"live/{lid}/room_1_coastal_v1.jpg"
    assert coastal["broker_approved"] is False
    assert current_image(client, lid, "coastal") == coastal["image"]


def test_v1_survives_v2_and_can_be_selected_again_without_meta_calls(client, monkeypatch):
    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    v1 = versions(client, lid)["room_1:2142"][-1]
    assert v1["is_current"]

    assert rerun(client, lid, "2142")["status"] == "done"
    records = versions(client, lid)["room_1:2142"]
    v2 = records[-1]
    assert v2["version"] == v1["version"] + 1 and v2["image"].endswith(f"_v{v2['version']}.jpg")
    assert v2["created_by"].startswith("style rerun job ")
    old = next(r for r in records if r["version"] == v1["version"])
    assert old["image"] == v1["image"] and not old["is_current"] and v2["is_current"]
    assert (config.settings.media_dir / v1["image"]).is_file(), "v1 kept on disk"
    assert (config.settings.media_dir / v2["image"]).is_file()
    assert current_image(client, lid, "2142") == v2["image"]

    def no_meta(*args, **kwargs):
        raise AssertionError("Use this version must not call Meta")
    monkeypatch.setattr(client.fake_meta, "image_stage", no_meta)
    monkeypatch.setattr(client.fake_meta, "sam_segment", no_meta)
    res = client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/2142/versions/{v1['version']}/use")
    assert res.status_code == 200, res.text
    after = res.json()["versions"]["room_1:2142"]
    assert [r["version"] for r in after if r["is_current"]] == [v1["version"]]
    assert len(after) == len(records), "newer version kept"
    assert current_image(client, lid, "2142") == v1["image"]


def test_full_re_prepare_continues_numbering_and_keeps_old_files(client):
    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    first = versions(client, lid)["room_1:coastal"]
    assert request_and_wait(client, lid)["status"] == "done"
    second = versions(client, lid)["room_1:coastal"]
    assert [r["version"] for r in second[:len(first)]] == [r["version"] for r in first]
    assert second[-1]["version"] > first[-1]["version"] and second[-1]["is_current"]
    for r in second:
        assert (config.settings.media_dir / r["image"]).is_file()
    stage1 = versions(client, lid)["room_1:modern-luxury"]
    assert len(stage1) == 1, "the broker-approved Stage 1 image is one version, not re-added per prepare"


def test_images_from_before_versioning_are_kept_as_a_version(client):
    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    listing = db.get_listing(lid)
    legacy_image = listing["live"]["rooms"][0]["styles"]["minimal"]["image"]
    listing["live"].pop("versions")
    db.save_listing(listing)

    assert rerun(client, lid, "minimal")["status"] == "done"
    records = versions(client, lid)["room_1:minimal"]
    assert records[0]["image"] == legacy_image and records[0]["created_by"] == "before versioning"
    assert records[0]["version"] == 1 and not records[0]["is_current"]
    assert records[1]["version"] == 2 and records[1]["is_current"]


def test_use_version_refuses_unknown_and_unavailable_versions(client):
    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    assert client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/coastal/versions/99/use").status_code == 404
    listing = db.get_listing(lid)
    listing["live"]["versions"]["room_1:coastal"][0]["available"] = False
    db.save_listing(listing)
    res = client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/coastal/versions/1/use")
    assert res.status_code == 409 and "didn't pass" in res.json()["detail"]
