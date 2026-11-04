"""Broker changes a room's type; that room re-stages with the new type's prompt."""

import pytest

from pipeline import stage
from tests.conftest import wait_for_job
from tests.test_stage0 import upload_photos


def _ready(client, count=2):
    ids = upload_photos(client, count=count)
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    return ids["listing_id"]


def _room(client, lid, room_id):
    return next(r for r in client.get(f"/api/listings/{lid}").json()["rooms"] if r["id"] == room_id)


@pytest.mark.parametrize("client", [{"layout": ["living"]}], indirect=True)
def test_retype_restages_room_with_new_prompt(client):
    lid = _ready(client)
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).json()["status"] == "approved"
    before = _room(client, lid, "room_2")
    assert before["name"] == "Living room 2"

    res = client.post(f"/api/listings/{lid}/rooms/room_2/type", json={"type": "bedroom"})
    assert res.status_code == 202, res.text
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"

    listing = client.get(f"/api/listings/{lid}").json()
    room = next(r for r in listing["rooms"] if r["id"] == "room_2")
    assert room["type"] == "bedroom" and room["name"] == "Bedroom"
    assert room["after"].endswith("_bedroom.jpg") and room["after"] != before["after"]
    assert room["staging"]["prompt"] == stage.prompt_for(listing["style"], room)
    assert stage.ROOM_GUIDANCE["bedroom"] in room["staging"]["prompt"]
    assert room["staging"]["level"] == 0
    assert room["staging_history"][0]["after"] == before["after"]
    assert listing["status"] == "draft" and listing["review"]["decision"] is None
    assert "rooms" in listing["review"]["edited_fields"]
    # Stricter re-stage still starts at level 1 afterwards.
    assert _room(client, lid, "room_1")["name"] == "Living room"


@pytest.mark.parametrize("client", [{"fail_restage": True}], indirect=True)
def test_failed_retype_reverts_type(client):
    lid = _ready(client)
    before = _room(client, lid, "room_1")
    res = client.post(f"/api/listings/{lid}/rooms/room_1/type", json={"type": "bedroom"})
    assert wait_for_job(client, res.json()["job_id"])["status"] == "failed"
    room = _room(client, lid, "room_1")
    assert room["type"] == before["type"] and room["name"] == before["name"]
    assert room["after"] == before["after"]


def test_retype_refusals(client):
    lid = _ready(client)
    room = _room(client, lid, "room_1")
    url = f"/api/listings/{lid}/rooms/room_1/type"
    assert client.post(url, json={"type": room["type"]}).status_code == 409
    assert client.post(url, json={"type": "hallway"}).status_code == 422
    assert client.post(f"/api/listings/{lid}/rooms/room_99/type", json={"type": "bedroom"}).status_code == 404
    client.post(f"/api/listings/{lid}/review", json={"action": "approve"})
    client.post(f"/api/listings/{lid}/publish")
    assert client.post(url, json={"type": "bedroom"}).status_code == 409
