"""To-do 5: Live-In-It prepares itself on publish when VRE_AUTO_PREPARE_LIVE is on, never blocks publish."""

import dataclasses

import pytest

import config
from tests.conftest import wait_for_job
from tests.test_spec_v2 import publish, upload_photo_set
from tests.test_stage2 import publish_listing


@pytest.fixture
def auto_on(client, monkeypatch):
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, auto_prepare_live=True))
    return client


def test_off_by_default_publish_queues_nothing(client):
    assert config.settings.auto_prepare_live is False
    lid = publish_listing(client)
    listing = client.get(f"/api/listings/{lid}").json()
    assert not listing.get("live") and not listing.get("live_auto")
    assert client.get(f"/api/listings/{lid}/live").status_code == 404


def test_publish_queues_the_same_live_job(auto_on):
    client = auto_on
    lid = publish_listing(client)
    listing = client.get(f"/api/listings/{lid}").json()
    assert listing["status"] == "published"
    assert listing["live_auto"]["queued"] is True
    job_id = listing["live"]["job_id"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["kind"] == "live"
    assert wait_for_job(client, job_id)["status"] == "done"
    body = client.get(f"/api/listings/{lid}/live").json()
    assert body["status"] == "ready" and body["rooms"]


def test_republish_of_a_ready_listing_does_not_prepare_again(auto_on):
    client = auto_on
    lid = publish_listing(client)
    first = client.get(f"/api/listings/{lid}").json()["live"]["job_id"]
    wait_for_job(client, first)
    assert client.post(f"/api/listings/{lid}/unpublish").status_code == 200
    publish(client, lid)
    assert client.get(f"/api/listings/{lid}").json()["live"]["job_id"] == first


@pytest.mark.parametrize("client", [{"layout": ["bathroom", "other", "bathroom"], "blocking_checks": False}],
                         indirect=True)
def test_ineligible_listing_still_publishes_and_says_why(auto_on):
    client = auto_on
    ids = upload_photo_set(client, 3, city="Chicago")
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    publish(client, lid)
    listing = client.get(f"/api/listings/{lid}").json()
    assert listing["status"] == "published"
    assert listing["live_auto"]["queued"] is False
    assert listing["live_auto"]["reason"].startswith("No main living space")
    assert not listing.get("live")
