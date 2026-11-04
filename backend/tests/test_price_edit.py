"""Broker can set or clear the asking price; the inventory summary carries the comps guide."""

from tests.conftest import wait_for_job
from tests.test_stage0 import upload_photos


def _ready(client, **facts):
    ids = upload_photos(client, **facts)
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    return ids["listing_id"]


def _summary(client, lid):
    return next(i for i in client.get("/api/listings").json() if i["id"] == lid)


def test_set_price_on_estimated_listing(client):
    lid = _ready(client, estimate_price="true")
    summary = _summary(client, lid)
    assert summary["facts"]["price"] is None and summary["price_display"] is None
    assert summary["price_guide"]["low"] < summary["price_guide"]["high"]

    res = client.post(f"/api/listings/{lid}/review", json={"action": "save", "price": 3900000})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["facts"]["price"] == 3900000 and body["facts"]["estimate_price"] is False
    assert "price" in body["review"]["edited_fields"]
    assert _summary(client, lid)["price_display"] == "$3,900,000"


def test_price_edit_clears_approval_and_can_be_cleared(client):
    lid = _ready(client)
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).json()["status"] == "approved"

    body = client.post(f"/api/listings/{lid}/review", json={"action": "save", "price": 5000000}).json()
    assert body["status"] == "draft" and body["facts"]["price"] == 5000000

    body = client.post(f"/api/listings/{lid}/review", json={"action": "save", "price": None}).json()
    assert body["facts"]["price"] is None and body["facts"]["estimate_price"] is True

    # Omitting price leaves it alone.
    body = client.post(f"/api/listings/{lid}/review", json={"action": "save", "notes": "x"}).json()
    assert body["facts"]["price"] is None


def test_price_must_be_positive(client):
    lid = _ready(client)
    assert client.post(f"/api/listings/{lid}/review", json={"action": "save", "price": 0}).status_code == 422


def test_published_price_needs_unpublish(client):
    lid = _ready(client)
    client.post(f"/api/listings/{lid}/review", json={"action": "approve"})
    client.post(f"/api/listings/{lid}/publish")
    assert client.post(f"/api/listings/{lid}/review", json={"action": "save", "price": 1}).status_code == 409
