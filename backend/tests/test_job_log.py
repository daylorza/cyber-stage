import db
import live


def test_live_job_exposes_its_call_log(client):
    with db.connect() as conn:
        db.insert_listing(conn, {"id": "lst_log", "status": "published", "source": "upload"})
        db.insert_job(conn, "job_log", "lst_log", "live")
    trace = [{"id": "tr_1", "model": "muse-image-1.0", "purpose": "live.image.stage", "target": {"room": "room_1", "style": "coastal"},
              "at": "2026-11-01T12:00:00+00:00", "ms": 3200, "ok": True, "error": None, "cached": False, "summary": "x"}]
    live._track("job_log", trace)
    job = client.get("/api/jobs/job_log").json()
    assert job["log"] == [{"at": "2026-11-01T12:00:00+00:00", "model": "muse-image-1.0", "purpose": "live.image.stage",
                           "ms": 3200, "ok": True, "cached": False, "error": None, "target": {"room": "room_1", "style": "coastal"}}]


def test_jobs_without_a_live_trace_have_no_log(client):
    with db.connect() as conn:
        db.insert_listing(conn, {"id": "lst_plain", "status": "draft", "source": "upload"})
        db.insert_job(conn, "job_plain", "lst_plain", "listing")
    assert "log" not in client.get("/api/jobs/job_plain").json()
