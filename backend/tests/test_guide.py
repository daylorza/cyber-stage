def test_guide_missing_listing_returns_404(client):
    response = client.post('/api/listings/missing/guide/chat', json={'thread_id': 't', 'message': 'Hello'})
    assert response.status_code == 404


def test_guide_rejects_empty_message(client):
    response = client.post('/api/listings/missing/guide/chat', json={'thread_id': 't', 'message': ' '})
    assert response.status_code == 422


def test_tools_use_prepared_images_and_simulate_deposit():
    import json
    import guide

    listing = {"facts": {"beds": 3}, "live": {"rooms": [
        {"id": "r1", "styles": {"coastal": {"available": True, "image": "live/room.jpg"}}},
        {"id": "r2", "styles": {}},
    ]}}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    tools = {t.name: t for t in guide._tools(listing, {}, result)}
    assert json.loads(tools["get_listing_facts"].invoke({}))["fact:beds"] == 3
    assert json.loads(tools["switch_style"].invoke({"style_id": "coastal"}))["staged_image_url"] == "/api/media/live/room.jpg"
    assert json.loads(tools["next_room"].invoke({}))["room_id"] == "r2"
    assert json.loads(tools["switch_style"].invoke({"style_id": "coastal"}))["error"]
    deposit = json.loads(tools["simulated_deposit"].invoke({}))
    assert deposit["simulated"] is True and deposit["payment_taken"] is False


def test_room_reports_only_available_styles():
    import json
    import guide
    listing = {"live": {"rooms": [{"id": "r1", "styles": {
        "coastal": {"available": True, "image": "a.jpg"},
        "minimal": {"available": False, "error": "Geometry failed"},
    }}]}}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    room = next(t for t in guide._tools(listing, {}, result) if t.name == "get_room")
    assert json.loads(room.invoke({}))["available_styles"] == ["coastal"]


def test_evidence_reports_citations_from_prior_turns():
    import guide
    listing = {"facts": {"beds": 3}, "frames": [{"wonder": {"observations": [{"id": "o_f1_1", "text": "View"}]}}]}
    assert guide._cited_evidence("Three beds [fact:beds], view [o_f1_1].", listing) == ["fact:beds", "o_f1_1"]


def test_session_limit_does_not_invoke_model(client, monkeypatch):
    import db
    import guide
    listing = {"id": "cap_test", "status": "published", "source": "upload", "live": {"status": "ready"}}
    with db.connect() as conn:
        db.insert_listing(conn, listing)
    monkeypatch.setitem(guide._sessions, ("cap_test", "cap"), {"turns": 12})
    monkeypatch.setattr(guide, "_model", lambda: (_ for _ in ()).throw(AssertionError("must not invoke")))
    response = client.post("/api/listings/cap_test/guide/chat", json={"thread_id": "cap", "message": "Hello"})
    assert response.status_code == 200
    assert "12-turn limit" in response.json()["text"]
