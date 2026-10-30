"""Verifier door/window check: boxes cut off at the photo edge are reported as not compared."""

from types import SimpleNamespace

from PIL import Image

from verify import checks

SIZE = (200, 400)
EDGE_DOOR = [120, 346, 156, 400]      # touches the bottom edge (like the bathroom vanity door)
INNER_DOOR = [45, 202, 69, 227]       # fully in frame
INNER_WINDOW = [30, 80, 90, 160]


class StubSam:
    def __init__(self, before: dict[str, list], after: dict[str, list]):
        self.boxes = {"before": before, "after": after}

    def sam_segment(self, path, concept, *, trace=None, purpose="", target=None):
        return [{"box": b, "concept": concept} for b in self.boxes[target["side"]].get(concept, [])]


def _run(tmp_path, before, after):
    src, dst = tmp_path / "before.jpg", tmp_path / "after.jpg"
    Image.new("RGB", SIZE).save(src)
    Image.new("RGB", SIZE).save(dst)
    ctx = SimpleNamespace(client=StubSam(before, after), trace=[])
    return checks._structure_check(ctx, {"id": "room_3"}, src, dst)


def test_edge_door_missing_after_is_not_compared(tmp_path):
    status, reason = _run(tmp_path,
                          {"door": [EDGE_DOOR, INNER_DOOR], "window": [INNER_WINDOW]},
                          {"door": [INNER_DOOR], "window": [INNER_WINDOW]})
    assert status == "pass"
    assert reason == "Windows and doors preserved. Not compared (cut off at the photo edge): door #1."


def test_inner_door_missing_still_fails(tmp_path):
    status, reason = _run(tmp_path,
                          {"door": [EDGE_DOOR, INNER_DOOR]},
                          {"door": [EDGE_DOOR]})
    assert status == "fail"
    assert reason.startswith("Staging changed structure: door #2 moved or removed.")
    assert "Not compared (cut off at the photo edge): door #1." in reason


def test_only_edge_boxes_never_claims_preserved(tmp_path):
    status, reason = _run(tmp_path, {"door": [EDGE_DOOR]}, {})
    assert status == "pass"
    assert "preserved" not in reason
    assert reason == "No windows or doors fully in frame to compare. Not compared (cut off at the photo edge): door #1."


def test_extra_doors_rule_still_catches_added_in_frame_doors(tmp_path):
    status, reason = _run(tmp_path,
                          {"door": [EDGE_DOOR]},
                          {"door": [EDGE_DOOR, INNER_DOOR, [150, 50, 190, 120]]})
    assert status == "fail"
    assert "2 extra door(s) added" in reason


def test_extra_doors_rule_ignores_cut_off_doors_on_both_sides(tmp_path):
    # Like Bathroom 2: a newly detected door at the right edge plus a double door split in two.
    status, reason = _run(tmp_path,
                          {"door": [EDGE_DOOR, INNER_DOOR]},
                          {"door": [EDGE_DOOR, INNER_DOOR, [45, 230, 69, 260], [182, 150, 200, 370]]})
    assert status == "pass", reason
    assert "extra" not in reason


def test_no_edge_boxes_keeps_original_wording(tmp_path):
    assert _run(tmp_path, {"door": [INNER_DOOR]}, {"door": [INNER_DOOR]}) == ("pass", "Windows and doors preserved.")


def test_edge_rule_constants():
    assert checks.STRUCTURE_EDGE_MARGIN == 0.01
    assert checks.STRUCTURE_IOU == 0.3 and checks.GEOMETRY_MIN_CORR == 0.25
    assert checks._cut_off([0.597, 0.866, 0.781, 0.999])       # bathroom door #1 (bottom edge)
    assert not checks._cut_off([0.226, 0.506, 0.347, 0.567])   # kitchen door #3 (in frame)
