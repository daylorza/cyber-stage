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


def test_single_room_next_room_is_explicit():
    import json
    import guide
    listing = {"live": {"rooms": [{"id": "r1", "name": "Living room", "styles": {}}]}}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    tool = next(t for t in guide._tools(listing, {}, result) if t.name == "next_room")
    assert "only one room" in json.loads(tool.invoke({}))["error"]


def test_broker_note_for_price_and_deposit_but_not_pure_style():
    import guide
    note = 'A broker decides on any home decision.'
    assert guide._broker_note('How much is this?', 'It is $1,000,000.', [], None).endswith(note)
    assert guide._broker_note('Reserve it', 'Simulated deposit.', [], {'simulated': True}).endswith(note)
    assert guide._broker_note('Show me Coastal', 'Now showing Coastal.', ['switch_style'], None) == 'Now showing Coastal.'
    assert guide._broker_note('Price?', 'I cannot provide that information.', [], None) == 'I cannot provide that information.'


def test_facts_report_only_supplied_fields_and_price_missing_line():
    import json

    import guide

    listing = {"status": "published",
               "published": {"title": "Miami Residence",
                             "facts": {"beds": 3, "city": "Miami", "price": None}},
               "live": {"rooms": []}}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    facts = next(t for t in guide._tools(listing, {}, result) if t.name == "get_listing_facts")
    data = json.loads(facts.invoke({}))
    assert data["fact:beds"] == 3
    assert data["fact:title"] == "Miami Residence"
    assert data["fact:status"] == "published"
    assert data["price_missing"] == "The supplied listing facts do not include a price."
    assert "fact:lot" not in data and "fact:year_built" not in data


def test_price_is_abbreviated_in_facts_and_reply():
    import json

    import guide

    listing = {"status": "published", "published": {"facts": {"price": 3200000, "currency": "USD"}},
               "live": {"rooms": []}}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    facts = next(t for t in guide._tools(listing, {}, result) if t.name == "get_listing_facts")
    assert json.loads(facts.invoke({}))["price_display"] == "$3.2M"
    assert guide.short_money(750000) == "$750k"
    assert guide.short_money(4535000) == "$4.54M"
    assert guide.short_money(2500000, "GBP") == "£2.5M"
    text = "Asking $3200000, comps $4,400,000 to $4,670,000.00, $750,000 or $1,782 per sq ft; already $3.2M."
    assert guide._clean_chat_text(text) == "Asking $3.2M, comps $4.4M to $4.67M, $750k or $1,782 per sq ft; already $3.2M."


def test_room_reports_staged_furniture_labelled_not_included():
    import json

    import guide

    listing = {"live": {"rooms": [{"id": "r1", "styles": {"coastal": {
        "available": True, "image": "c.jpg",
        "pieces": [{"concept": "sofa"}, {"concept": "table"}, {"concept": "sofa"}]}}}]}}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    room = next(t for t in guide._tools(listing, {"style": "coastal"}, result) if t.name == "get_room")
    data = json.loads(room.invoke({}))
    assert data["staged_furniture"]["label"] == "staged furniture in this room"
    assert data["staged_furniture"]["items"] == ["sofa", "table"]
    assert data["staged_furniture"]["included_in_sale"] == "not stated in the broker record"


def test_comps_label_is_exact_and_not_a_valuation():
    import json

    import guide

    listing = {"comps": {"label": "old", "items": []}, "live": {"rooms": []}}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    comps = next(t for t in guide._tools(listing, {}, result) if t.name == "explain_comps")
    data = json.loads(comps.invoke({}))
    assert data["label"] == "Demo comps: seeded sample data, not a live MLS feed"
    assert data["not_valuation"] is True


def test_how_made_reports_checker_statuses_as_recorded():
    import json

    import guide

    listing = {"live": {"rooms": []},
               "verification": {"passed": False, "checks": [
                   {"id": "staging_geometry", "status": "pass", "reason": "ok"},
                   {"id": "comps_demo", "status": "unclear", "reason": "not run"},
                   {"id": "blur_pass", "status": "fail", "reason": "blur missed"}],
                   "flags": [{"message": "blur missed"}]},
               "frames": [{"blur": {"regions": 2}}, {"blur": None}]}
    result = {"actions_taken": [], "evidence": [], "staged_image_url": None, "deposit": None}
    how = next(t for t in guide._tools(listing, {}, result) if t.name == "explain_how_made")
    data = json.loads(how.invoke({}))
    assert [c["status"] for c in data["checker"]["checks"]] == ["pass", "unclear", "fail"]
    assert data["checker"]["passed"] is False
    assert any(step["model"] is None and "not a model" in step["does"] for step in data["steps"])
    assert data["privacy_blur"] == {"frames_with_blur": 1, "regions": 2}
    assert data["asset_origin"] == "not recorded for this listing"


def _chat_with_fake_agent(client, monkeypatch, listing_id, message, agent_text, thread):
    import db
    import guide

    listing = {"id": listing_id, "status": "published", "source": "upload",
               "live": {"status": "ready", "rooms": []}}
    with db.connect() as conn:
        db.insert_listing(conn, listing)

    class Agent:
        def invoke(self, *args, **kwargs):
            return {"messages": [type("Message", (), {"content": agent_text})()]}

    monkeypatch.setattr(guide, "_model", lambda: None)
    monkeypatch.setattr(guide, "create_agent", lambda *a, **k: Agent())
    response = client.post(f"/api/listings/{listing_id}/guide/chat",
                           json={"thread_id": thread, "message": message})
    assert response.status_code == 200
    return response.json()["text"]


def test_cyberpunk_definition_gets_locked_wording_once(client, monkeypatch):
    import guide

    text = _chat_with_fake_agent(client, monkeypatch, "cyber_def", "What is Cyberpunk?",
                                 "Cyberpunk looks futuristic.", "cyber-def")
    assert guide.CYBERPUNK_DEFINITION_LEAD in text
    assert text.count(guide.CYBERPUNK_LOCKED_SENTENCE) == 1
    assert text.count(guide.CYBERPUNK_DISCLAIMER) == 1


def test_chat_text_strips_markdown_tags_and_urls(client, monkeypatch):
    text = _chat_with_fake_agent(
        client, monkeypatch, "clean_test", "Tell me about the place",
        "**Bold** room [fact:beds] see https://example.com/page and http://localhost:5173/x",
        "clean-test")
    assert "**" not in text and "[fact:" not in text
    assert "http" not in text and "localhost" not in text
    assert "Bold room" in text
