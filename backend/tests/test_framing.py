"""Verifier door/window check: small global framing drift (<= 5%) is corrected before comparing."""

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from verify import checks

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "structure_boxes.json").read_text())


class StubSam:
    def __init__(self, before: dict[str, list], after: dict[str, list]):
        self.boxes = {"before": before, "after": after}

    def sam_segment(self, path, concept, *, trace=None, purpose="", target=None):
        return [{"box": b, "concept": concept} for b in self.boxes[target["side"]].get(concept, [])]


def _run(tmp_path, before, after, src_size=(1000, 1000), dst_size=(1000, 1000)):
    src, dst = tmp_path / "before.jpg", tmp_path / "after.jpg"
    Image.new("RGB", tuple(src_size)).save(src)
    Image.new("RGB", tuple(dst_size)).save(dst)
    ctx = SimpleNamespace(client=StubSam(before, after), trace=[])
    return checks._structure_check(ctx, {"id": "room_x"}, src, dst)


def _fixture(tmp_path, name):
    f = FIXTURES[name]
    return _run(tmp_path, f["before"], f["after"], f["src_size"], f["dst_size"])


def _shift(boxes, sx=1.0, tx=0.0, sy=1.0, ty=0.0):
    """Apply a global stretch/shift (fractions of a 1000 px frame) to pixel boxes."""
    return [[round(sx * x1 + tx * 1000), round(sy * y1 + ty * 1000),
             round(sx * x2 + tx * 1000), round(sy * y2 + ty * 1000)] for x1, y1, x2, y2 in boxes]


ANCHOR_DOORS = [[100, 200, 250, 600], [400, 150, 520, 450], [650, 300, 800, 700], [300, 650, 450, 900]]
TRANSOM = [[100, 410, 240, 430]]          # 2% tall, like the Chicago transoms
TINY_DOOR = [[560, 540, 580, 570]]        # 2% x 3%, like the small far cabinet doors


def test_chicago_kitchen_drift_items_pass_real_misses_still_fail(tmp_path):
    status, reason = _fixture(tmp_path, "chicago_kitchen_initial")
    assert status == "fail"
    for window in range(1, 7):                       # transoms W1/W4 and the panes all drift-only
        assert f"window #{window} moved" not in reason, reason
    for door in (5, 11, 12):                         # no matching box at all: detection misses
        assert f"door #{door} moved or removed" in reason, reason
    assert "Framing corrected before comparing (14 matching doors" in reason
    assert "6 item(s) matched only after correction." in reason


def test_dark_gray_bar_stool_cover_still_fails_even_with_correction(tmp_path):
    # Doors are bunched in the cabinet band, so only a shift is fitted (y -1.5%, within 5%).
    status, reason = _fixture(tmp_path, "darkgray_kitchen_barstools")
    assert status == "fail"
    assert "door #3 moved or removed" in reason
    assert "Framing corrected before comparing (6 matching doors: stretch x 1.002, y 1.000" in reason
    assert "no item needed it." in reason


def test_bunched_doors_fit_shift_only(tmp_path):
    band = [[100, 300, 200, 400], [300, 320, 400, 420], [500, 310, 600, 410], [700, 300, 800, 400]]
    status, reason = _run(tmp_path, {"door": band}, {"door": _shift(band, ty=-0.02)})
    assert status == "pass", reason
    assert "stretch x 1.000, y 1.000; shift x +0.0%, y -2.0%" in reason


def test_small_drift_corrected_but_covered_door_still_fails(tmp_path):
    before = {"door": ANCHOR_DOORS + TINY_DOOR + [[850, 100, 900, 250]], "window": TRANSOM}
    drifted = {"door": _shift(ANCHOR_DOORS + TINY_DOOR, sy=1.022, ty=-0.03),  # last door covered
               "window": _shift(TRANSOM, sy=1.022, ty=-0.03)}
    status, reason = _run(tmp_path, before, drifted)
    assert status == "fail"
    assert "door #6 moved or removed" in reason
    assert "door #5" not in reason and "window #1" not in reason
    assert "2 item(s) matched only after correction." in reason


def test_drift_over_five_percent_is_not_corrected(tmp_path):
    before = {"door": ANCHOR_DOORS + TINY_DOOR, "window": TRANSOM}
    drifted = {"door": _shift(ANCHOR_DOORS + TINY_DOOR, sy=1.0, ty=-0.07),
               "window": _shift(TRANSOM, sy=1.0, ty=-0.07)}
    status, reason = _run(tmp_path, before, drifted)
    assert status == "fail"
    assert "door #5 moved or removed" in reason and "window #1 moved or removed" in reason
    assert "Framing drift 7.0% (4 matching doors) is over 5%; not corrected." in reason


def test_correction_never_breaks_a_raw_match(tmp_path):
    # Doors drift 3% down; the transom did not move. It must still pass as-is.
    before = {"door": ANCHOR_DOORS, "window": TRANSOM}
    after = {"door": _shift(ANCHOR_DOORS, ty=0.03), "window": TRANSOM}
    status, reason = _run(tmp_path, before, after)
    assert status == "pass", reason
    assert "no item needed it." in reason


def test_too_few_matching_doors_means_no_correction(tmp_path):
    before = {"door": ANCHOR_DOORS[:2], "window": TRANSOM}
    after = {"door": _shift(ANCHOR_DOORS[:2], ty=-0.03), "window": _shift(TRANSOM, ty=-0.03)}
    status, reason = _run(tmp_path, before, after)
    assert status == "fail" and "window #1 moved or removed" in reason
    assert "Framing" not in reason


def test_framing_constants_and_iou_unchanged():
    assert checks.STRUCTURE_IOU == 0.3 and checks.GEOMETRY_MIN_CORR == 0.25
    assert checks.FRAMING_MAX_DRIFT == 0.05
    assert checks.FRAMING_ANCHOR_IOU == 0.5 and checks.FRAMING_MIN_ANCHORS == 3
