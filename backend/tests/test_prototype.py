"""Prototype Testing assets: the exact-clip guard, the camera calibration, SAM mask parsing.
The image cutting itself needs numpy (added only by `make prototype`) and is not run here."""

from pathlib import Path

import pytest

import meta_client
from prototype import assets


def test_refuses_any_clip_but_the_poc(tmp_path: Path):
    with pytest.raises(assets.Stop, match="is not there"):
        assets.verify_video(tmp_path / assets.POC_NAME)
    other = tmp_path / "sample_vid.mp4"
    other.write_bytes(b"x" * 10)
    with pytest.raises(assets.Stop, match="is not there"):
        assets.verify_video(other)
    wrong = tmp_path / assets.POC_NAME
    wrong.write_bytes(b"x" * 10)
    with pytest.raises(assets.Stop, match="expected 30,987,086"):
        assets.verify_video(wrong)


def test_calibration_from_square_vanishing_points():
    # Synthetic level camera: f = 800 px on 1600x900, vanishing points at x = cx -/+ f.
    f, cx, cy = 800.0, 800.0, 450.0
    left, right = (cx - f, cy), (cx + f, cy)
    lines_a = ((left[0] + 400, cy - 200, left[0] + 800, cy - 400), (left[0] + 300, cy + 150, left[0] + 900, cy + 450))
    lines_b = ((right[0] - 400, cy + 200, right[0] - 800, cy + 400), (right[0] - 300, cy - 150, right[0] - 900, cy - 450))
    cal = assets.calibrate(lines_a, lines_b, (1600, 900))
    assert cal["focal_px"] == pytest.approx(f, rel=1e-3)
    assert cal["horizon_y"] == pytest.approx(0.5, abs=1e-4)
    assert abs(cal["pitch_deg"]) < 0.01 and abs(cal["roll_deg"]) < 0.01


def test_poc_calibration_is_a_plausible_wide_lens():
    cal = assets.calibrate()
    assert 85 < cal["hfov_deg"] < 105
    assert abs(cal["pitch_deg"]) < 2 and abs(cal["roll_deg"]) < 2


def test_sam_masks_keep_box_and_mask_together():
    text = ("<0f>0<|box;x1=375;y1=394;x2=514;y2=479;w=1024;h=576|><|mask;x=0;y=0;data=86,140,~!!!8m!0c|>,"
            "1<|box;x1=10;y1=20;x2=30;y2=40;w=1024;h=576;c=0.9|><|mask;x=0;y=0;c=0.9;data=21,21,!abc|>")
    recs = meta_client.parse_sam_masks(text, 2048, 1152)
    assert [r["box"] for r in recs] == [[750, 788, 1028, 958], [20, 40, 60, 80]]
    assert recs[0]["mask"] == {"height": 86, "width": 140, "encoding": "lossless", "payload": "~!!!8m!0c"}
    assert recs[1]["mask"]["encoding"] == "one_bit" and recs[1]["score"] == 0.9
    assert recs[0]["source_box"] == [375, 394, 514, 479] and recs[0]["source_size"] == [1024, 576]
    # Boxes alone still parse the old way.
    assert meta_client.parse_sam_output(text, 2048, 1152)[0]["box"] == [750, 788, 1028, 958]


def test_floor_anchor_check():
    floor = [0.0, 0.64, 0.7, 1.0]
    inside = [{"id": "sofa", "box": [0.1, 0.6, 0.4, 0.8], "base": [[0.2, 0.8], [0.4, 0.75]]}]
    assert assets.floor_contact_inside(inside, floor)["status"] == "pass"
    outside = [{"id": "lamp", "box": [0.8, 0.3, 0.9, 0.5], "base": [[0.85, 0.5]]}]
    assert assets.floor_contact_inside(outside, floor) == {
        "status": "fail", "outside": ["lamp"], "reason": "Outside the SAM floor box: lamp."}
    assert assets.floor_contact_inside(inside, None)["status"] == "not_checked"
