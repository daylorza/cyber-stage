"""Live-In-It Spec v2: full video, main living room as hero, token guard, video-first
published page, any-listing Live-In-It, aligned cascade masks, outside-view reporting."""

import io
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageStat

import cascade
import config
import listings
from pipeline import PipelineError, frames
from tests.conftest import make_photo, wait_for_job
from tests.test_stage0 import FACTS, upload_video
from verify import checks

CHICAGO = {"city": "Chicago", "address": "123 Main St", "beds": "2", "baths": "2", "sqft": "2000",
           "price": "320000"}


@pytest.fixture(scope="session")
def long_video(tmp_path_factory) -> Path:
    """30 s walkthrough whose every second differs (no near-duplicates): longer than 24 frames."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    out = tmp_path_factory.mktemp("long") / "long.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
         "cellauto=s=160x90:rate=10:rule=110,format=yuv420p", "-t", "30", str(out)],
        check=True,
    )
    return out


def upload_photo_set(client, count: int, **data):
    files = [("files", (f"shot{i}.png", make_photo(i + 1), "image/png")) for i in range(count)]
    res = client.post("/api/listings", data={**FACTS, **data}, files=files)
    assert res.status_code == 202, res.text
    return res.json()


def publish(client, lid: str) -> None:
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    assert client.post(f"/api/listings/{lid}/publish").status_code == 200


# ---------- 1. full video, no frame cap ----------

def test_coverage_check_rejects_a_truncated_extraction():
    with pytest.raises(PipelineError, match=r"frames stop at 0:23 of a 55.8s video \(24 of ~55"):
        frames.check_coverage("tour.mp4", 55.83, [float(t) for t in range(24)])
    with pytest.raises(PipelineError, match="frames stop at 0:49"):
        frames.check_coverage("tour.mp4", 55.83, [float(t) for t in range(50)] + [49.0] * 10)
    ok = frames.check_coverage("tour.mp4", 55.83, [float(t) for t in range(56)])
    assert ok["extracted"] == 56 and ok["last_t"] == 55.0 and ok["first_t"] == 0.0


def test_frame_times_are_when_the_kept_frame_was_filmed():
    # ffmpeg's fps filter keeps the LAST frame before slot + 0.5 s. Live-In-It pauses the video at this
    # time and lays the hero frame over it, and the video blur windows use it, so it must be exact.
    packets = [i / 30 for i in range(1675)]                     # 55.8 s at 30 fps
    assert frames.slot_time(35, packets) == pytest.approx(35.467, abs=0.001)
    assert frames.slot_time(0, packets) == pytest.approx(0.467, abs=0.001)
    assert frames.slot_time(3, []) == 3.0


def test_truncated_video_fails_the_job_instead_of_publishing_part(client, walkthrough_video, monkeypatch):
    # The file claims 30 s but only 4 s of frames come out: the job must stop, not publish.
    monkeypatch.setattr(frames, "video_duration", lambda src: 30.0)
    ids = upload_video(client, walkthrough_video)
    job = wait_for_job(client, ids["job_id"])
    assert job["status"] == "failed"
    assert "frames stop at 0:03 of a 30.0s video" in job["error"]
    listing = client.get(f"/api/listings/{ids['listing_id']}").json()
    assert listing["status"] == "failed" and not listing["rooms"]


def test_whole_video_sampled_and_classified_in_batches(client, long_video):
    ids = upload_video(client, long_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()

    video = listing["videos"][0]
    assert video["duration"] == 30.0 and video["extracted"] == 30 and video["last_t"] >= 28
    assert len(listing["frames"]) > 24, "no 24-frame cap"
    assert max(f["t"] for f in listing["frames"]) >= 28
    frames_item = next(i for i in listing["checklist"]["items"] if i["id"] == "frames")
    assert frames_item["status"] == "done"
    coverage = next(c for c in listing["verification"]["checks"] if c["id"] == "frames:coverage:1")
    assert coverage["status"] == "pass" and "Whole video covered: 30.0s, 30 frames 0:00–0:29" in coverage["reason"]

    batches = client.fake_meta.classify_batches
    assert len(batches) == 2 and all(len(b["frames"]) <= 24 for b in batches)
    assert batches[0]["known_rooms"] == "" and "living_1 (living" in batches[1]["known_rooms"]
    assert all(f["wonder"] for f in listing["frames"] if f["path"]), "every frame of the video was read"

    text = client.get(f"/api/listings/{lid}/export").text
    assert "Video 30.0s · 30 frames extracted at 1 fps · first 0:00 · last 0:29" in text


# ---------- 2. main living room is the hero; token guard ----------

UTILITY_FIRST = ["bathroom", "bedroom", "other", "kitchen", "exterior", "office", "terrace", "living"]


@pytest.mark.parametrize("client", [{"layout": UTILITY_FIRST}], indirect=True)
def test_living_room_is_hero_kept_and_staged_first(client):
    ids = upload_photo_set(client, len(UTILITY_FIRST))
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()

    rooms = listing["rooms"]
    assert len(rooms) == config.settings.max_rooms
    types = [r["type"] for r in rooms]
    # 8 rooms, cap 6: utility rooms go first (exterior, laundry/other); the living room stays.
    assert types == ["bathroom", "bedroom", "kitchen", "office", "terrace", "living"]
    living = rooms[-1]
    assert living["main"] is True and living["name"] == "Living room"
    assert listing["main_room"]["found"] and listing["main_room"]["room"] == living["id"]

    guard = listing["token_guard"]
    assert guard["status"] == "main_first" and guard["order"][0] == living["id"]
    assert guard["order"][-1] == rooms[0]["id"], "the utility bathroom stages last"
    staged = [t["target"]["room"] for t in listing["trace"] if t["purpose"] == "image.stage"]
    assert staged[0] == living["id"]
    assert "Living room confirmed and staged first" in guard["detail"]


@pytest.mark.parametrize("client", [{"layout": ["bathroom", "other", "bathroom"], "blocking_checks": False}],
                         indirect=True)
def test_no_living_space_spends_nothing_on_staging_and_says_why(client):
    ids = upload_photo_set(client, 3, city="Chicago")
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()

    assert listing["main_room"]["found"] is False
    assert not [t for t in listing["trace"] if t["purpose"].startswith("image.")], "no Meta Image spend"
    item = next(i for i in listing["checklist"]["items"] if i["id"] == "staging_geometry")
    assert item["status"] != "done" and "no main living space" in item["detail"].lower()
    assert listing["token_guard"]["status"] == "no_main_room"
    assert all("no main living space" in r["staging"]["error"] for r in listing["rooms"])

    publish(client, lid)  # demo mode: broker may still publish with open warnings
    page = client.get(f"/api/listings/{lid}/page").json()
    assert page["live"]["eligible"] is False
    assert page["live"]["reason"].startswith("No main living space found in this video")
    res = client.post(f"/api/listings/{lid}/live", json={})
    assert res.status_code == 422 and "No main living space" in res.json()["detail"]


# ---------- 3/5. published page = video; Live-In-It for any listing ----------

def test_published_page_plays_the_blurred_full_video_and_chicago_is_enterable(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video, **CHICAGO, test_listing="true")
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    assert listing["note"] == listings.TEST_NOTE

    video = listing["videos"][0]
    assert video["status"] == "ready" and video["path"] == f"video/{lid}/walkthrough_01.mp4"
    assert video["blurred_boxes"] >= 1, "FakeMeta's face on f01 is blurred in the video"
    check = next(c for c in listing["verification"]["checks"] if c["id"] == "blur_pass:video:1")
    assert check["status"] == "pass" and "read back from the encoded file" in check["reason"]

    publish(client, lid)
    page = client.get(f"/api/listings/{lid}/page").json()
    assert page["video"]["path"] == video["path"] and page["video"]["duration"] == pytest.approx(4.0, abs=0.2)
    assert page["note"] == listings.TEST_NOTE
    assert page["live"] == {"eligible": True, "reason": None, "status": None,
                            "main_room": page["rooms"][0]["id"], "main_room_name": "Living room"}
    served = client.get(f"/api/media/{video['path']}")
    assert served.status_code == 200 and served.headers["content-type"] == "video/mp4"
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json",
         str(config.settings.media_dir / video["path"])], capture_output=True, text=True, check=True).stdout
    assert '"video"' in probe and '"audio"' not in probe

    # Not Miami: no residence needed. Enter residence prepares from this listing.
    res = client.post(f"/api/listings/{lid}/live", json={})
    assert res.status_code == 202, res.text
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"
    body = client.get(f"/api/listings/{lid}/live").json()
    assert body["status"] == "ready" and body["residence"] is None
    assert body["note"] == listings.TEST_NOTE and body["video"] == page["video"]
    assert [p["id"] for p in body["path"]] == [r["id"] for r in sorted(page["rooms"], key=lambda r: r["t"])]
    assert all(p["prepared"] for p in body["path"])
    room = next(r for r in body["rooms"] if r["main"])
    assert room["t"] is not None and room["span"]
    for entry in room["styles"].values():
        assert entry["available"] and entry["pieces"]
        assert set(entry["align"]) >= {"sx", "sy", "bx", "by"}
        assert entry["mask"] is None or (config.settings.media_dir / entry["mask"]).is_file()


@pytest.mark.parametrize("client", [{"layout": ["bathroom", "living"]}], indirect=True)
def test_live_walks_past_utility_rooms_without_staging_them(client):
    ids = upload_photo_set(client, 2, city="Chicago")
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    publish(client, lid)
    res = client.post(f"/api/listings/{lid}/live", json={})
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    bathroom = next(r for r in listing["rooms"] if r["type"] == "bathroom")
    live = listing["live"]
    assert [r["type"] for r in live["rooms"]] == ["living"]
    assert live["guard"]["skipped_utility"] == [bathroom["id"]]
    assert not [t for t in live["trace"] if t["target"].get("room") == bathroom["id"]]


def test_reprocessing_a_published_listing_takes_it_down_until_reapproved(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video, **CHICAGO)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    publish(client, lid)
    res = client.post(f"/api/listings/{lid}/reprocess")
    assert res.status_code == 202, res.text
    assert client.get(f"/api/listings/{lid}/page").status_code == 404
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    assert listing["status"] == "draft" and "published" not in listing and "live" not in listing
    assert client.post(f"/api/listings/{lid}/publish").status_code == 409, "broker approval still gates publish"


def test_tampered_video_without_blur_fails_the_check(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    listing = client.get(f"/api/listings/{lid}").json()
    published = config.settings.media_dir / listing["videos"][0]["path"]
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(walkthrough_video), "-an",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(published)], check=True)
    res = client.post(f"/api/listings/{lid}/review", json={"action": "save"})
    check = next(c for c in res.json()["verification"]["checks"] if c["id"] == "blur_pass:video:1")
    assert check["status"] == "fail" and "Published video at 0:00 (f01)" in check["reason"]


def test_test_label_is_not_an_edit(client, walkthrough_video):
    ids = upload_video(client, walkthrough_video)
    lid = ids["listing_id"]
    assert wait_for_job(client, ids["job_id"])["status"] == "done"
    assert client.post(f"/api/listings/{lid}/review", json={"action": "approve"}).status_code == 200
    res = client.post(f"/api/listings/{lid}/review", json={"action": "save", "test_listing": True}).json()
    assert res["note"] == listings.TEST_NOTE and res["status"] == "approved"
    summary = next(s for s in client.get("/api/listings").json() if s["id"] == lid)
    assert summary["note"] == listings.TEST_NOTE


# ---------- 3. cascade prep: alignment + clean furniture mask ----------

def _room_image(size=(360, 640)) -> Image.Image:
    img = Image.new("RGB", size, (200, 198, 192))
    d = ImageDraw.Draw(img)
    w, h = size
    d.rectangle([0, int(h * 0.62), w, h], fill=(140, 110, 80))                     # floor
    d.rectangle([int(w * 0.15), int(h * 0.2), int(w * 0.55), int(h * 0.5)], fill=(150, 190, 230))  # window
    d.line([0, int(h * 0.62), w, int(h * 0.62)], fill=(255, 255, 255), width=4)   # baseboard
    d.rectangle([int(w * 0.7), int(h * 0.25), int(w * 0.92), int(h * 0.62)], outline=(90, 90, 90), width=5)
    return img


def test_alignment_recovers_drift_and_mask_keeps_furniture_not_edges(tmp_path):
    ref = _room_image()
    ref_path = tmp_path / "before.jpg"
    ref.save(ref_path, quality=95)
    drift = cascade._params(1.0, 1.022, 0.0, -0.03)
    inverse = {"sx": 1 / drift["sx"], "sy": 1 / drift["sy"],
               "bx": -drift["bx"] / drift["sx"], "by": -drift["by"] / drift["sy"]}
    staged = cascade.warp(ref, inverse, ref.size).resize((576, 1024))
    ImageDraw.Draw(staged).rectangle([100, 700, 420, 860], fill=(60, 70, 90))     # the "sofa"
    staged_path = tmp_path / "staged.jpg"
    staged.save(staged_path, quality=95)

    a = cascade.align(ref_path, staged_path)
    assert a["sy"] == pytest.approx(1.022, abs=0.011) and a["by"] == pytest.approx(drift["by"], abs=0.01)
    assert a["score"] < a["identity_score"]

    info = cascade.furniture_mask(ref_path, ref_path, cascade.IDENTITY, staged_path, a, tmp_path / "m.png")
    assert info["usable"]
    alpha = Image.open(tmp_path / "m.png").split()[1]
    sofa = cascade.to_frame([100 / 576, 700 / 1024, 420 / 576, 860 / 1024], a)
    w, h = alpha.size
    inside = alpha.crop((int(sofa[0] * w) + 6, int(sofa[1] * h) + 6, int(sofa[2] * w) - 6, int(sofa[3] * h) - 6))
    top = alpha.crop((0, 0, w, int(h * 0.55)))
    assert ImageStat.Stat(inside).mean[0] > 230, "furniture is in the mask"
    assert ImageStat.Stat(top).mean[0] < 8, "walls/window edges are not (no halo)"

    unaligned = cascade.furniture_mask(ref_path, ref_path, cascade.IDENTITY, staged_path, cascade.IDENTITY,
                                       tmp_path / "raw.png")
    assert unaligned["changed"] > info["changed"], "without alignment, edges leak into the mask"


# ---------- 6. whole-picture framing correction (Day, Oct 28: "Align + glass-door SAM") ----------

def test_framing_correction_from_the_whole_picture_rescues_drift_only(tmp_path):
    ref = Image.open(io.BytesIO(make_photo(3, (360, 640)))).convert("RGB")
    ref_path = tmp_path / "before.jpg"
    ref.save(ref_path, quality=95)
    drift = cascade._params(1.0, 1.02, 0.0, -0.035)                 # 3.5% shift, 2% stretch, no doors
    inverse = {"sx": 1 / drift["sx"], "sy": 1 / drift["sy"],
               "bx": -drift["bx"] / drift["sx"], "by": -drift["by"] / drift["sy"]}
    staged = cascade.warp(ref, inverse, ref.size)
    ImageDraw.Draw(staged).rectangle([60, 420, 260, 520], fill=(60, 70, 90))
    staged_path = tmp_path / "staged.jpg"
    staged.save(staged_path, quality=95)

    raw = checks.edge_correlation(ref_path, staged_path)
    assert raw < checks.GEOMETRY_MIN_CORR, "the drift alone fails the uncorrected check"
    result = checks.geometry(ref_path, staged_path)
    assert result["status"] == "pass" and result["corrected"], result
    assert result["reason"].startswith("Geometry preserved after framing correction from the whole picture")
    assert "shift x +0.0%, y -3.5%" in result["reason"] and "threshold 0.25 unchanged" in result["reason"]
    assert checks.GEOMETRY_MIN_CORR == 0.25 and checks.FRAMING_MAX_DRIFT == 0.05

    # A real change (mirrored room) is not rescued, and drift over 5% is never corrected.
    mirrored = tmp_path / "mirrored.jpg"
    staged.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(mirrored, quality=95)
    assert checks.geometry(ref_path, mirrored)["status"] == "fail"
    far = dict(cascade._params(1.0, 1.0, 0.0, -0.08))
    failed = checks.geometry(ref_path, staged_path, align=far)
    assert failed["status"] == "fail" and "Framing drift 8.0% is over 5%; not corrected" in failed["reason"]

    # Windows/doors: with fewer than 3 matching doors, the same alignment rescues drift-only boxes.
    window = [0.15, 0.2, 0.55, 0.5]
    moved = [(window[0] - drift["bx"]) / drift["sx"], (window[1] - drift["by"]) / drift["sy"],
             (window[2] - drift["bx"]) / drift["sx"], (window[3] - drift["by"]) / drift["sy"]]
    transom = [0.6, 0.1, 0.7, 0.12]
    src = {"window": [window, transom], "door": []}
    dst = {"window": [moved, [(transom[0] - drift["bx"]) / drift["sx"], (transom[1] - drift["by"]) / drift["sy"],
                              (transom[2] - drift["bx"]) / drift["sx"], (transom[3] - drift["by"]) / drift["sy"]]],
           "door": []}
    assert checks.compare_structure(src, dst)["problems"] == ["window #2 moved or removed"]
    fixed = checks.compare_structure(src, dst, image_align=drift)
    assert fixed["problems"] == [] and fixed["rescued"] == 1
    assert "Framing corrected from the whole picture before comparing (fewer than 3 matching doors" in fixed["note"]
    covered = checks.compare_structure(src, {"window": [moved], "door": []}, image_align=drift)
    assert covered["problems"] == ["window #2 moved or removed"], "a covered window still fails"


def test_windows_behind_a_glass_door_are_outside_view():
    slider = [0.688, 0.445, 0.999, 0.648]                            # SAM "glass door" on the source
    facade = [0.776, 0.535, 0.831, 0.569]                            # a window across the street
    own = [0.332, 0.38, 0.539, 0.59]                                 # the room's own side window
    src = {"window": [own, facade], "door": [], checks.GLASS_DOOR: [slider]}
    result = checks.compare_structure(src, {"window": [own], "door": []})
    assert result["problems"] == [] and result["outside"] == ["window #2 moved or removed"]
    lost_own = checks.compare_structure(src, {"window": [], "door": []})
    assert lost_own["problems"] == ["window #1 moved or removed"]


# ---------- 6b. outside-view windows reported separately ----------

def test_outside_view_windows_are_reported_separately():
    glass = [0.1, 0.2, 0.9, 0.7]
    far = [[0.2, 0.3, 0.25, 0.36], [0.5, 0.3, 0.56, 0.36]]          # windows across the street
    door = [0.05, 0.3, 0.12, 0.9]
    src = {"window": [glass] + far, "door": [door]}
    moved_far = {"window": [glass, [0.3, 0.45, 0.35, 0.5], [0.6, 0.45, 0.66, 0.5]], "door": [door]}
    result = checks.compare_structure(src, moved_far)
    assert result["problems"] == [] and result["outside"] == ["window #2 moved or removed",
                                                             "window #3 moved or removed"]
    assert "Outside view (seen through the room's glass, reported separately)" in result["note"]

    covered = checks.compare_structure(src, {"window": moved_far["window"], "door": []})
    assert covered["problems"] == ["door #1 moved or removed"], "the room's own door still fails"

    # A facade seen through a sliding glass door (several windows inside one door box) is outside view;
    # a single window inside a door box (a transom or pane) stays a room-structure problem.
    slider = [0.09, 0.39, 0.32, 0.64]
    facade = [[0.15, 0.48, 0.165, 0.49], [0.2, 0.43, 0.22, 0.45], [0.17, 0.59, 0.18, 0.61]]
    through = checks.compare_structure({"window": facade, "door": [slider]},
                                       {"window": [[0.15, 0.5, 0.165, 0.51]], "door": [slider]})
    assert through["problems"] == [] and len(through["outside"]) == 3
    pane = checks.compare_structure({"window": facade[:1], "door": [slider]}, {"window": [], "door": [slider]})
    assert pane["problems"] == ["window #1 moved or removed"] and pane["outside"] == []
