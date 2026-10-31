"""Stage 1 acceptance: Meta pipeline, checklist, independent verifier, broker gate."""

import pytest
from PIL import Image

import checklist
import config
import meta_client
from tests.conftest import make_photo, wait_for_job
from tests.fake_meta import FakeMeta
from tests.test_stage0 import FACTS, upload_photos, upload_video


def items_of(listing):
    return {i["id"]: i for i in listing["checklist"]["items"]}


def test_happy_path(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    listing = client.get(f"/api/listings/{lid}").json()
    items = items_of(listing)
    assert len(items) == 7
    assert all(i["status"] == "done" for i in items.values()), items
    assert listing["verification"]["passed"] is True

    # The face SAM found on f01 is actually blurred in the publishable copy.
    frame_ids = {f["id"] for f in listing["frames"]}
    f01 = next(f for f in listing["frames"] if f["id"] == "f01")
    assert f01["sam"]["privacy"], "expected a privacy box on f01"
    box = f01["sam"]["privacy"][0]["box"]
    with Image.open(config.settings.raw_frames_dir / lid / f01["raw"]) as raw, \
            Image.open(config.settings.media_dir / f01["path"]) as blurred:
        assert raw.convert("RGB").crop(box).tobytes() != blurred.convert("RGB").crop(box).tobytes()

    for room in listing["rooms"]:
        assert room["source_frame"] in frame_ids
        assert room["before"] and room["after"]
        assert (config.settings.media_dir / room["before"]).is_file()
        assert (config.settings.media_dir / room["after"]).is_file()

    obs_ids = {
        o["id"] for f in listing["frames"] for o in (f.get("wonder") or {}).get("observations", [])
    }
    claims = listing["copy"]["sentences"] + listing["copy"]["highlights"]
    assert claims and listing["copy"]["description"]
    for claim in claims + [{"text": listing["copy"]["title"], "evidence": listing["copy"]["evidence"]["title"]}]:
        assert claim["evidence"], claim
        for ev in claim["evidence"]:
            assert ev["kind"] in ("fact", "visual"), ev
            if ev["kind"] == "fact":
                assert ev["ref"] in listing["facts"] and ev["value"] == listing["facts"][ev["ref"]]
            else:
                assert ev["ref"] in obs_ids and ev["frame"] in frame_ids

    purposes = {t["purpose"] for t in listing["trace"]}
    assert {"sam.privacy", "sam.structure", "wonder.classify", "image.stage",
            "sam.staged_faces", "spark.copy"} <= purposes
    assert {"verify.wonder.claim", "verify.sam.structure", "verify.sam.faces"} <= purposes
    assert all(t["ok"] for t in listing["trace"])

    # Raw frames are never under media_dir and never served.
    assert not config.settings.raw_frames_dir.resolve().is_relative_to(config.settings.media_dir.resolve())
    res = client.get(f"/api/media/frames_raw/{lid}/{f01['raw']}")
    assert res.status_code == 404

    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    assert client.post(f"/api/listings/{lid}/publish").status_code == 200
    page = client.get(f"/api/listings/{lid}/page").json()
    assert page["verification"]["passed"] is True
    assert page["verification"]["checks"] > 0
    assert all(not r["rejected"] for r in page["rooms"])


@pytest.mark.parametrize("client", [{"bad_claim": True}], indirect=True)
def test_bad_claim_flagged_then_broker_removes_it(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    listing = client.get(f"/api/listings/{lid}").json()
    assert items_of(listing)["claim_evidence"]["status"] == "flagged"
    flagged = [f for f in listing["verification"]["flags"] if f["item"] == "claim_evidence"]
    assert any("rooftop" in f["message"].lower() or "rooftop" in str(f["target"]).lower() for f in flagged)
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 409
    assert client.post(f"/api/listings/{lid}/publish").status_code == 409

    copy = listing["copy"]
    kept = [h["text"] for h in copy["highlights"] if "rooftop" not in h["text"].lower()]
    edit = {"title": copy["title"], "description": copy["description"], "highlights": kept}
    res = client.post(f"/api/listings/{lid}/review", json={"action": "save", "copy_edit": edit})
    assert res.status_code == 200
    cleared = items_of(res.json())["claim_evidence"]
    assert cleared["status"] == "done" and "rooftop" not in cleared["detail"].lower()
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    assert client.post(f"/api/listings/{lid}/publish").status_code == 200


@pytest.mark.parametrize("client", [{"wrong_number": True}], indirect=True)
def test_wrong_number_fails_code_check(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    assert items_of(listing)["claim_evidence"]["status"] == "flagged"
    fails = [c for c in listing["verification"]["checks"]
             if c["item"] == "claim_evidence" and c["status"] == "fail"]
    assert fails and "4" in fails[0]["reason"]


@pytest.mark.parametrize("client", [{"warp_staging": True}], indirect=True)
def test_warped_staging_flagged_then_room_excluded(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    listing = client.get(f"/api/listings/{lid}").json()
    assert items_of(listing)["staging_geometry"]["status"] == "flagged"
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 409

    res = client.post(f"/api/listings/{lid}/review",
                      json={"action": "save", "rejected_rooms": ["room_2"]})
    assert res.status_code == 200
    assert items_of(res.json())["staging_geometry"]["status"] == "done"
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    assert client.post(f"/api/listings/{lid}/publish").status_code == 200
    page = client.get(f"/api/listings/{lid}/page").json()
    assert [r["id"] for r in page["rooms"]] == ["room_1"]


@pytest.mark.parametrize("client", [{"face_survives": True}], indirect=True)
def test_face_survives_blocks_approval(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    assert items_of(listing)["blur_pass"]["status"] == "flagged"
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 409


def test_meta_not_configured_degrades_cleanly(client_no_meta):
    ids = upload_photos(client_no_meta, count=2)
    lid = ids["listing_id"]
    job = wait_for_job(client_no_meta, ids["job_id"])
    assert job["status"] == "done", job

    listing = client_no_meta.get(f"/api/listings/{lid}").json()
    items = items_of(listing)
    for item_id in ("sam_masks", "blur_pass", "wonder_classification", "staging_geometry"):
        assert items[item_id]["status"] == "failed", (item_id, items[item_id])
    assert items["frames"]["status"] == "done"
    assert all(f["path"] is None for f in listing["frames"])
    assert not list((config.settings.media_dir / "frames" / lid).glob("*.jpg"))
    assert listing["status"] == "draft"
    assert client_no_meta.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 409


def test_edits_after_approval_clear_approval(client):
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    wait_for_job(client, ids["job_id"])
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    edit = {"title": "Broker retitled", "description": "", "highlights": []}
    res = client.post(f"/api/listings/{lid}/review", json={"action": "save", "copy_edit": edit})
    assert res.json()["status"] == "draft"
    assert res.json()["review"]["decision"] is None
    assert client.post(f"/api/listings/{lid}/publish").status_code == 409


def test_number_words_checked_against_facts():
    from verify.checks import _claim_code, numbers_in

    assert numbers_in("Three bedrooms and 3.5 baths across 2,400 sq ft") == [3.5, 2400, 3]
    facts = {"beds": 3, "baths": 3.5}
    cite = [{"kind": "fact", "ref": "beds", "value": 3}]
    assert _claim_code("Three bedrooms", cite, facts, {}, set())[0] == "pass"
    status, reason = _claim_code("Four bedrooms", cite, facts, {}, set())
    assert status == "fail" and "4" in reason


def test_sam_parser():
    text = ("<0f>0<|box;x1=181;y1=365;x2=556;y2=486;w=1516;h=1600|><|mask;x=0;y=0;data=122,376,~abc|>"
            ",1<|box;x1=10;y1=20;x2=30;y2=40;w=1516;h=1600;c=0.91|><|mask;x=0;y=0;data=1,1,~a|>")
    boxes = meta_client.parse_sam_output(text, 1516, 1600)
    assert len(boxes) == 2
    assert boxes[0]["box"] == [181, 365, 556, 486] and boxes[0]["score"] is None
    assert boxes[1]["box"] == [10, 20, 30, 40] and boxes[1]["score"] == 0.91
    assert meta_client.parse_sam_output("", 1516, 1600) == []
    # Scaled back to original size when the sent image was downscaled.
    scaled = meta_client.parse_sam_output(text, 3032, 3200)
    assert scaled[0]["box"] == [362, 730, 1112, 972]


def test_meta_cache(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(make_photo(1))
    fake = FakeMeta()
    trace = []
    fake.sam_segment(image, "window", trace=trace, purpose="sam.structure")
    again = fake.sam_segment(image, "window", trace=trace, purpose="sam.structure")
    assert fake.calls == 1
    assert len(trace) == 2
    assert trace[0]["cached"] is False and trace[1]["cached"] is True and trace[1]["ok"]
    assert again[0]["concept"] == "window"
    assert again[0]["box"] == [48, 36, 144, 108]  # stable normalized box on a 320x180 image


def test_meta_status_has_no_key(client):
    res = client.get("/api/meta/status")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"configured", "base_url", "models"}
    assert set(body["models"]) == {"spark", "wonder", "image", "sam"}
    assert "key" not in res.text.lower()


# Every frame reads as living room, so the frames that survive still include the main living
# space and the token guard lets staging run.
@pytest.mark.parametrize("client", [{"fail_concept": "face", "fail_frame": "f01", "layout": ["living"]}],
                         indirect=True)
def test_partial_sam_failure_holds_frame_back(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    listing = client.get(f"/api/listings/{lid}").json()
    frames = {f["id"]: f for f in listing["frames"]}
    assert frames["f01"]["sam"] is None and frames["f01"]["path"] is None
    assert not (config.settings.media_dir / "frames" / lid / "f01.jpg").exists()
    others = [f for fid, f in frames.items() if fid != "f01"]
    assert others and all(f["sam"] and f["path"] for f in others)

    item = items_of(listing)["sam_masks"]
    assert item["status"] in ("failed", "done") and "failed" in item["detail"]
    assert any(t["purpose"] == "sam.privacy" and t["ok"] is False for t in listing["trace"])

    # The held-back frame is excluded from everything published; the rest verifies clean.
    assert all("f01" not in (r.get("frames") or []) for r in listing["rooms"])
    assert listing["verification"]["passed"] is True
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200


@pytest.mark.parametrize("client", [{"fail_staged_faces": True}], indirect=True)
def test_failed_staged_face_check_keeps_media_clean(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    listing = client.get(f"/api/listings/{lid}").json()
    assert items_of(listing)["staging_geometry"]["status"] == "failed"
    assert all(r["after"] is None for r in listing["rooms"])
    assert all(r["staging"]["error"] for r in listing["rooms"])
    assert not list((config.settings.media_dir / "staged" / lid).glob("*.jpg"))
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 409


def test_reprocess_after_meta_becomes_available(client_no_meta):
    ids = upload_photos(client_no_meta, count=2)
    lid = ids["listing_id"]
    assert wait_for_job(client_no_meta, ids["job_id"])["status"] == "done"
    assert items_of(client_no_meta.get(f"/api/listings/{lid}").json())["sam_masks"]["status"] == "failed"

    meta_client.set_client(FakeMeta())
    res = client_no_meta.post(f"/api/listings/{lid}/reprocess")
    assert res.status_code == 202, res.text
    job = wait_for_job(client_no_meta, res.json()["job_id"])
    assert job["status"] == "done"

    listing = client_no_meta.get(f"/api/listings/{lid}").json()
    assert listing["status"] == "draft"
    assert listing["job_id"] == res.json()["job_id"]
    assert all(i["status"] == "done" for i in listing["checklist"]["items"])
    assert client_no_meta.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200


def test_reprocess_rejected_for_unknown_and_processing(client):
    # Seeded hero listings were removed: unknown ids 404.
    assert client.post("/api/listings/seed_new_york/reprocess").status_code == 404
    assert client.post("/api/listings/seed_new_york/verify").status_code == 404


def test_verify_job_preserves_content_and_checklist(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    before = client.get(f"/api/listings/{lid}").json()
    verify_traces = sum(1 for t in before["trace"] if t["purpose"].startswith("verify."))
    assert verify_traces > 0

    res = client.post(f"/api/listings/{lid}/verify")
    assert res.status_code == 202, res.text
    job = wait_for_job(client, res.json()["job_id"])
    assert job["status"] == "done" and job["stage"] == "ready"

    after = client.get(f"/api/listings/{lid}").json()
    assert after["status"] == "draft"
    assert [i["id"] for i in after["checklist"]["items"]] == [i["id"] for i in before["checklist"]["items"]]
    assert all(i["status"] == "done" for i in after["checklist"]["items"])
    assert after["copy"]["title"] == before["copy"]["title"]
    new_verify = [t for t in after["trace"] if t["purpose"].startswith("verify.")]
    assert len(new_verify) > verify_traces

    # Verify job on an approved listing clears the approval back to draft.
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    res = client.post(f"/api/listings/{lid}/verify")
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    assert listing["status"] == "draft" and listing["review"]["decision"] is None
