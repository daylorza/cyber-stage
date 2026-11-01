import pytest


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
    assert json.loads(room.invoke({}))["available_styles"] == ["Coastal"]


@pytest.mark.parametrize(("requested", "expected"), [
    ("cyberpunk", "2142"), ("cyberpunk-2142", "2142"),
    ("  CYBERPUNK  --  2142 ", "2142"), ("2142", "2142"),
    ("Modern", "modern-luxury"), ("modern luxury", "modern-luxury"),
    ("coastal", "coastal"), ("minimal", "minimal"),
])
def test_style_aliases_select_prepared_image(requested, expected):
    import json
    import guide
    styles = {key: {"available": True, "image": f"{key}.jpg"} for key in ("2142", "modern-luxury", "coastal", "minimal")}
    session = {}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    switch = next(t for t in guide._tools({"live": {"rooms": [{"id": "r1", "styles": styles}]}}, session, result) if t.name == "switch_style")
    response = json.loads(switch.invoke({"style_id": requested}))
    assert session["style"] == expected
    assert response["staged_image_url"] == f"/api/media/{expected}.jpg"


@pytest.mark.parametrize("requested", ["unknown", "original", "unstaged", "minimal"])
def test_unavailable_style_reports_confirmed_options_without_switch(requested):
    import json
    import guide
    styles = {"2142": {"available": True, "image": "cyber.jpg"}, "minimal": {"available": False, "error": "Geometry failed"}}
    session = {"style": "modern-luxury"}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    switch = next(t for t in guide._tools({"live": {"rooms": [{"id": "r1", "styles": styles}]}}, session, result) if t.name == "switch_style")
    response = json.loads(switch.invoke({"style_id": requested}))
    assert response["error"]
    assert response["available_styles"] == ["Cyberpunk"]
    assert session["style"] == "modern-luxury"
    assert result["staged_image_url"] is None


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


def test_chat_syncs_viewed_room_and_style(client, monkeypatch):
    import db
    import guide
    listing = {"id": "sync_test", "status": "published", "source": "upload", "live": {"status": "ready", "rooms": [
        {"id": "r1", "styles": {}}, {"id": "r2", "styles": {"coastal": {"available": True, "image": "r2.jpg"}}}
    ]}}
    with db.connect() as conn:
        db.insert_listing(conn, listing)
    class Agent:
        def invoke(self, *args, **kwargs):
            import json
            room = next(t for t in self.tools if t.name == "get_room")
            data = json.loads(room.invoke({}))
            assert data["id"] == "r2"
            assert data["style"] == "Coastal"
            return {"messages": [type("Message", (), {"content": "Ready"})()]}
    def create(*args, **kwargs):
        agent = Agent()
        agent.tools = args[1]
        return agent
    monkeypatch.setattr(guide, "_model", lambda: None)
    monkeypatch.setattr(guide, "create_agent", create)
    response = client.post('/api/listings/sync_test/guide/chat', json={"thread_id": "sync", "message": "Hello", "room_id": "r2", "style_id": "coastal"})
    assert response.status_code == 200
