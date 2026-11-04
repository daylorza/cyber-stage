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
            assert isinstance(r["objects_added_verified"], int), "To-do 3 fills the verified count"
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


def test_use_version_refuses_unknown_and_overrides_failed_versions(client):
    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    assert client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/coastal/versions/99/use").status_code == 404
    assert rerun(client, lid, "coastal")["status"] == "done"
    listing = db.get_listing(lid)
    listing["live"]["versions"]["room_1:coastal"][0]["available"] = False
    db.save_listing(listing)
    res = client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/coastal/versions/1/use")
    assert res.status_code == 200, res.text
    v1 = res.json()["versions"]["room_1:coastal"][0]
    assert v1["is_current"] and v1["broker_override"] and not v1["available"]
    style = client.get(f"/api/listings/{lid}/live").json()["rooms"][0]["styles"]["coastal"]
    assert style["image"] == v1["image"] and style["available"] and style["broker_override"]
    assert client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/coastal/versions/2/use").status_code == 200
    assert "broker_override" not in client.get(f"/api/listings/{lid}/live").json()["rooms"][0]["styles"]["coastal"]


def test_rerun_accepts_unchecked_structure_like_preparation(client, monkeypatch):
    """A room with no detectable windows, doors or glass wall can't have its structure compared;
    full preparation shows such an image, so a single-style rerun must too."""
    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    listing = db.get_listing(lid)
    for frame in listing["frames"]:
        (frame.get("sam") or {}).pop("structure", None)
    db.save_listing(listing)
    segment = client.fake_meta.sam_segment

    def nothing_structural(image_path, concept, **kwargs):
        if kwargs.get("purpose") in ("live.sam.source_structure", "live.sam.structure"):
            return []
        return segment(image_path, concept, **kwargs)

    monkeypatch.setattr(client.fake_meta, "sam_segment", nothing_structural)
    assert rerun(client, lid, "coastal")["status"] == "done"
    latest = versions(client, lid)["room_1:coastal"][-1]
    assert latest["is_current"] and latest["checker"]["structure"]["status"] == "not_checked"


def test_rerun_treats_edge_only_glass_as_unchecked_not_failed(client, monkeypatch):
    """Glass that touches the photo edge can't be compared (same rule as preparation and the
    verifier). With nothing comparable the check is "not checked", not a failure."""
    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    listing = db.get_listing(lid)
    for frame in listing["frames"]:
        (frame.get("sam") or {}).pop("structure", None)
    db.save_listing(listing)
    segment = client.fake_meta.sam_segment

    def edge_glass_only(image_path, concept, **kwargs):
        if kwargs.get("purpose") in ("live.sam.source_structure", "live.sam.structure"):
            if concept != "glass wall":
                return []
            w, h = client.fake_meta._size(image_path)
            return [{"concept": concept, "score": 0.9, "box": [0, round(0.1 * h), round(0.3 * w), round(0.8 * h)]}]
        return segment(image_path, concept, **kwargs)

    monkeypatch.setattr(client.fake_meta, "sam_segment", edge_glass_only)
    assert rerun(client, lid, "coastal")["status"] == "done"
    structure = versions(client, lid)["room_1:coastal"][-1]["checker"]["structure"]
    assert structure["status"] == "not_checked" and "cut off at the photo edge" in structure["reason"]
