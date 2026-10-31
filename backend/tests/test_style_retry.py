import db


def test_style_retry_requires_prepared_room(client):
    with db.connect() as conn:
        db.insert_listing(conn, {"id": "lst_style", "status": "published", "source": "upload", "live": {"status": "ready", "rooms": []}})
    assert client.post('/api/listings/lst_style/live/rooms/missing/styles/minimal/rerun').status_code == 404
    assert client.post('/api/listings/lst_style/live/rooms/missing/styles/nope/rerun').status_code == 422


def test_new_preset_can_be_generated_for_existing_prepared_room(client):
    with db.connect() as conn:
        db.insert_listing(conn, {"id": "lst_old_styles", "status": "published", "source": "upload", "live": {"status": "ready", "rooms": [{"id": "room_1", "type": "living", "styles": {"minimal": {}}}]}})
    response = client.post('/api/listings/lst_old_styles/live/rooms/room_1/styles/2142/rerun')
    assert response.status_code == 202


def test_living_style_rerun_accepts_sofa_when_table_detection_misses(client, monkeypatch):
    import live
    from tests.conftest import wait_for_job
    from tests.test_stage2 import publish_listing, request_and_wait

    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    original = live._pieces
    monkeypatch.setattr(live, "_pieces", lambda *args: [p for p in original(*args) if p["concept"] != "table"])
    response = client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/2142/rerun")
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "done", job


def test_concept_style_may_exceed_drift_cap_on_rerun(client, monkeypatch):
    import live
    from tests.conftest import wait_for_job
    from tests.test_stage2 import publish_listing, request_and_wait

    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    monkeypatch.setattr(live.checks, "image_drift", lambda align: 0.0825)
    response = client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/2142/rerun")
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "done", job
    style = client.get(f"/api/listings/{lid}/live").json()["rooms"][0]["styles"]["2142"]
    assert style["available"] is True
    assert style["concept"] is True
    assert style["drift"]["status"] == "concept-pass"
    assert style["drift"]["value"] == 0.0825
    assert "not broker-verified" in style["drift"]["reason"]


def test_standard_style_drift_cap_still_blocks_on_rerun(client, monkeypatch):
    import live
    from tests.conftest import wait_for_job
    from tests.test_stage2 import publish_listing, request_and_wait

    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    monkeypatch.setattr(live.checks, "image_drift", lambda align: 0.0825)
    response = client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/minimal/rerun")
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "failed", job
    assert job["error"] == "Framing drift exceeds 5%; existing style retained."


def test_concept_style_retains_failed_structure_verification(client, monkeypatch):
    import live
    from tests.conftest import wait_for_job
    from tests.test_stage2 import publish_listing, request_and_wait

    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    monkeypatch.setattr(live, "_structure_check", lambda *a, **k: ({"status": "fail", "reason": "Door changed."}, {}))
    response = client.post(f"/api/listings/{lid}/live/rooms/room_1/styles/2142/rerun")
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "done", job
    style = client.get(f"/api/listings/{lid}/live").json()["rooms"][0]["styles"]["2142"]
    assert style["concept"] is True
    assert style["structure"]["status"] == "fail"
    assert style["structure"]["reason"] == "Door changed."
