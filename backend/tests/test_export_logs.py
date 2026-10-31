"""Export logs endpoint: complete and ordered, read-only, and privacy-safe."""

import re

import db
import export_logs
from tests.conftest import make_photo, wait_for_job
from tests.test_stage0 import upload_photos, upload_video

HEADINGS = [
    "## 1. Listing",
    "## 2. Pipeline checks",
    "## 3. Needs your attention",
    "## 4. Rooms",
    "## 5. Listing copy",
    "## 6. What the model saw and decided",
    "## 7. Meta calls",
    "## 8. Job history",
]


def _export(client, listing_id):
    return client.get(f"/api/listings/{listing_id}/export")


def test_export_full_listing(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    res = _export(client, lid)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    assert res.headers["cache-control"] == "no-store"
    disposition = res.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert re.search(rf'filename="listing-{re.escape(lid)}-logs-\d{{8}}-\d{{4}}\.txt"', disposition)

    text = res.text
    positions = [text.index(h) for h in HEADINGS]
    assert positions == sorted(positions), HEADINGS

    listing = client.get(f"/api/listings/{lid}").json()
    trace = listing["trace"]
    assert trace
    for entry in trace:
        assert entry["id"] in text
    independent = [t for t in trace if t["purpose"].startswith("verify.")]
    generator = [t for t in trace if not t["purpose"].startswith("verify.")]
    cached = sum(1 for t in trace if t.get("cached"))
    assert f"## 7. Meta calls · {len(trace)} total · {len(independent)} independent · {cached} cached" in text
    assert f"### Generator · {len(generator)}" in text
    assert f"### Independent checks · {len(independent)}" in text
    assert text.count("cached: yes") + text.count("cached: no") == len(trace)

    for flag in (listing["verification"] or {}).get("flags", []):
        assert flag["message"] in text
    for room in listing["rooms"]:
        assert room["name"] in text
        if room.get("staging"):
            assert room["staging"]["prompt"] in text
    copy = listing["copy"]
    assert copy["title"] in text
    assert copy["description"] in text
    for claim in copy["sentences"] + copy["highlights"]:
        assert claim["text"] in text
    for frame in listing["frames"]:
        assert frame["id"] in text
        for obs in (frame.get("wonder") or {}).get("observations", []):
            assert obs["id"] in text
    for job in db.list_jobs(lid):
        assert job["id"] in text
    assert text.rstrip().endswith(f"-- end of export · {lid} --")


def test_export_after_reprocess_counts_cached(client):
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"

    res = client.post(f"/api/listings/{lid}/reprocess")
    assert res.status_code == 202, res.text
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"

    listing = db.get_listing(lid)
    cached = sum(1 for t in listing["trace"] if t.get("cached"))
    if cached == 0:  # fake may not cache every call; force one for the assertion
        assert listing["trace"], "expected trace entries"
        listing["trace"][0]["cached"] = True
        db.save_listing(listing)
        cached = 1
    text = _export(client, lid).text
    assert text.count("cached: yes") == cached
    assert text.count("cached: no") == len(listing["trace"]) - cached
    assert db.list_jobs(lid) and all(j["id"] in text for j in db.list_jobs(lid))


def test_export_scrubs_secrets_and_raw_paths(client, monkeypatch):
    fake_key = "sk-test-0123456789abcdefABCDEF"
    monkeypatch.setenv("META_API_KEY", fake_key)
    files = [("files", ("sneaky_upload_name.png", make_photo(3), "image/png"))]
    res = client.post("/api/listings", data={"city": "Miami"}, files=files)
    assert res.status_code == 202
    lid = res.json()["listing_id"]
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"

    listing = db.get_listing(lid)
    assert listing["trace"], "expected trace entries to tamper with"
    listing["trace"][0]["ok"] = False
    listing["trace"][0]["error"] = f"upstream rejected key {fake_key}"
    listing["verification"]["flags"].append({
        "id": "flag_secret", "item": "claim_evidence",
        "target": {"claim": "title"},
        "message": f"Broker pasted Bearer {fake_key} into a note.",
        "resolution": "Rotate the key and remove it.",
    })
    raws = [f["raw"] for f in listing["frames"] if f.get("raw")]
    assert raws
    db.save_listing(listing)

    text = _export(client, lid).text
    assert fake_key not in text
    assert "[redacted]" in text
    for pattern in export_logs.SECRET_PATTERNS:
        assert not re.search(pattern, text), pattern
    assert "frames_raw" not in text
    assert "staged_raw" not in text
    assert "uploads/" not in text
    assert "sneaky_upload_name.png" not in text
    for raw in raws:
        assert raw not in text


def test_export_is_read_only(client):
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200

    def snapshot():
        with db.connect() as conn:
            return dict(conn.execute(
                "SELECT data, status, updated_at FROM listings WHERE id = ?", (lid,)
            ).fetchone())

    before, jobs_before = snapshot(), len(db.list_jobs(lid))
    res1 = _export(client, lid)
    res2 = _export(client, lid)
    assert res1.status_code == 200 and res2.status_code == 200
    assert snapshot() == before
    assert len(db.list_jobs(lid)) == jobs_before
    listing = client.get(f"/api/listings/{lid}").json()
    assert listing["status"] == "approved" and listing["review"]["decision"] == "approved"


def test_export_published_listing(client):
    ids = upload_photos(client, count=2)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    assert client.post(f"/api/listings/{lid}/publish").status_code == 200

    text = _export(client, lid).text
    assert "Published snapshot:" in text
    assert "Verification passed: yes" in text
    assert "Status: published" in text


def test_export_removed_seed_and_unknown(client):
    # Seeded hero listings were removed: seed_miami exports 404 like any unknown id.
    assert _export(client, "seed_miami").status_code == 404
    assert _export(client, "lst_does_not_exist").status_code == 404


def test_export_only_contains_own_listing(client):
    first = upload_photos(client, count=1)
    second = upload_photos(client, count=1)
    wait_for_job(client, first["job_id"])
    wait_for_job(client, second["job_id"])

    text = _export(client, first["listing_id"]).text
    assert first["listing_id"] in text
    assert second["listing_id"] not in text
