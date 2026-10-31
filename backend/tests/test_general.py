"""Generalised cascade (Work 3): enterability and calibration guards.

The end-to-end build needs numpy + a clean non-POC clip (hero footage,
due Oct 29, still open at this stage) and is not run here; the guards
that refuse a listing before any Meta call are.
"""

import pytest

from prototype import general


def listing(**over) -> dict:
    base = {
        "id": "lst_test",
        "review": {"decision": "approved"},
        "rooms": [{"id": "room_1", "after": "staged/room_1_modern.jpg"}],
        "live": {"rooms": [{"id": "room_1", "name": "Living room", "main": True, "styles": {}}]},
    }
    base.update(over)
    return base


def test_enterable_listing_passes():
    room, stage1 = general.check_enterable(listing())
    assert room["main"] and stage1["after"]


def test_unapproved_listing_is_not_enterable():
    with pytest.raises(general.Stop, match="not broker-approved"):
        general.check_enterable(listing(review={"decision": "draft"}))


def test_no_main_living_room_is_not_enterable():
    with pytest.raises(general.Stop, match="no main living room"):
        general.check_enterable(listing(live={"rooms": [{"id": "room_1", "main": False, "styles": {}}]}))


def test_main_room_without_staging_is_not_enterable():
    with pytest.raises(general.Stop, match="no approved staging"):
        general.check_enterable(listing(rooms=[{"id": "room_1", "after": None}]))


def test_poc_camera_is_never_reused_blindly():
    with pytest.raises(general.Stop, match="POC camera is not reused"):
        general.require_calibration(None, [[0, 0, 1, 1]])
    with pytest.raises(general.Stop, match="POC camera is not reused"):
        general.require_calibration([[0, 0, 1, 1]], [])
    general.require_calibration([[0, 0, 1, 1]], [[0, 0, 1, 1]])


def test_missing_clip_is_never_substituted(tmp_path):
    with pytest.raises(general.Stop, match="is not there"):
        general.probe_video(tmp_path / "nope.mp4")


def test_every_generalised_page_is_labelled():
    assert general.LABEL == "Not a real listing — AI-modified"
    assert general.REAL_CONFIRMED == set()


def test_style_sam_cannot_cut_is_off_not_a_crash():
    # Regression: a style whose staged image yields no SAM piece under the
    # cascade concepts (e.g. Minimal here) reached cut_style with zero
    # pieces and died inside dilate() on a 0-d array. It must be marked
    # off with the usual reason instead.
    from prototype import assets

    entry = {"id": "minimal", "label": "Minimal", "available": True}
    assert assets.require_pieces(entry, []) is False
    assert entry["available"] is False
    assert entry["reason_short"] == "no furniture to drop"
    entry2 = {"id": "modern-luxury", "label": "Modern Luxury", "available": True}
    assert assets.require_pieces(entry2, [{"id": "rug"}]) is True
    assert entry2["available"] is True
