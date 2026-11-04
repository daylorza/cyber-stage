"""Style rotation changes new renders while geometry retries keep their design."""

import json
from itertools import cycle
from types import SimpleNamespace

import pytest

from pipeline import stage


@pytest.mark.parametrize("style,count", [("modern-luxury", 4), ("coastal", 4), ("minimal", 4), ("2142", 4)])
def test_each_style_uses_every_direction_before_repeating(style, count, monkeypatch):
    monkeypatch.setattr(stage, "_VARIANT_BAGS", {}, raising=False)
    monkeypatch.setattr(stage, "_LAST_VARIANTS", {}, raising=False)
    orders = cycle([False, True])

    def shuffle(values):
        if next(orders):
            values.reverse()

    # Alternate orders so every refill would repeat the boundary without the guard.
    monkeypatch.setattr(stage, "random", SimpleNamespace(shuffle=shuffle), raising=False)
    prompts = [stage.prompt_for(style, {"type": "living"}) for _ in range(count * 10)]
    for start in range(0, count * 10, count):
        assert len(set(prompts[start:start + count])) == count
    assert all(left != right for left, right in zip(prompts, prompts[1:]))


@pytest.mark.parametrize("style", ["modern-luxury", "coastal", "minimal", "2142"])
def test_bedroom_guidance_does_not_force_a_sofa(style):
    room = {"type": "bedroom"}
    before = json.dumps(room)
    prompt = stage.prompt_for(style, room).lower()
    assert "bed" in prompt
    assert "sofa" not in prompt
    assert json.dumps(room) == before
    assert "sofa" in stage.prompt_for(style, {"type": "living"}).lower()


@pytest.mark.parametrize("variant", list(stage.STYLE_PRESETS["2142"]["variants"]))
def test_2142_prompts_stay_pristine(variant):
    prompt = stage.prompt_for("2142", {"type": "living"}, variant=variant).lower()
    assert "noir" not in prompt and "cyberpunk" not in prompt
    assert "2142 sofa" in prompt


def test_2142_directions_cover_each_view_and_vehicle_combination():
    combos = set()
    for text in stage.STYLE_PRESETS["2142"]["variants"].values():
        view = text.split("Exterior view:")[1]
        combos.add((view.strip().startswith("replace the view"), "exactly one sleek" in view))
        assert ("No flying vehicles." in view) != ("exactly one sleek" in view)
    assert combos == {(True, True), (True, False), (False, True), (False, False)}


def test_saved_direction_survives_serialization_and_stricter_retries():
    room = json.loads(json.dumps({
        "type": "bedroom",
        "staging": {"style": "2142", "variant": "Liquid chrome"},
    }))
    first = stage.prompt_for("2142", room)
    assert "Design direction: Liquid chrome." in first
    for _ in range(5):
        stage.prompt_for("2142")  # Other rooms do not change this room's design.
    assert stage.prompt_for("2142", room) == first
    strict = stage.restage_prompt("2142", room, None, 1)
    assert first in strict
    assert stage.restage_prompt("2142", room, None, 1) == strict


def test_legacy_restage_remains_deterministic_and_unknown_style_falls_back():
    room = {"type": "bedroom", "staging": {"style": "minimal"}}
    assert stage.restage_prompt("minimal", room, None, 1) == stage.restage_prompt("minimal", room, None, 1)
    fallback = stage.prompt_for("missing", {"type": "living"})
    assert stage.GEOMETRY_RULES in fallback
    assert stage.STYLE_PRESETS["modern-luxury"]["description"] in fallback


@pytest.mark.parametrize("client", [{"warp_live_once": True, "layout": ["living", "bedroom"]}], indirect=True)
def test_live_picker_passes_room_type_and_keeps_direction_on_retry(client, monkeypatch):
    import live
    from tests.test_stage2 import publish_listing, request_and_wait

    prompts = {}
    generate = client.fake_meta.image_stage

    def capture(image_path, prompt, **kwargs):
        if kwargs.get("purpose") == "live.image.stage":
            target = kwargs["target"]
            prompts.setdefault((target["room"], target["style"]), []).append(prompt)
        return generate(image_path, prompt, **kwargs)

    monkeypatch.setattr(client.fake_meta, "image_stage", capture)
    lid = publish_listing(client)
    source = client.get(f"/api/listings/{lid}").json()
    for room in source["rooms"]:
        saved = room["staging"]
        assert f"Design direction: {saved.get('variant')}." in saved["prompt"]
    assert request_and_wait(client, lid)["status"] == "done"
    body = client.get(f"/api/listings/{lid}/live").json()
    for room in body["rooms"]:
        first, retry = prompts[(room["id"], "coastal")]
        assert retry == first + live.RETRY_RULES
        if room["type"] == "bedroom":
            assert "sofa" not in first.lower()
        for style_id, entry in room["styles"].items():
            assert entry["variant"] in stage.STYLE_PRESETS[style_id]["variants"]


def test_dev_variant_pick_is_gated_and_used_on_rerun(client, monkeypatch):
    import dataclasses

    import config
    from tests.conftest import wait_for_job
    from tests.test_stage2 import publish_listing, request_and_wait

    lid = publish_listing(client)
    assert request_and_wait(client, lid)["status"] == "done"
    url = f"/api/listings/{lid}/live/rooms/room_1/styles/2142/rerun"
    assert "variants" not in client.get("/api/settings").json()
    assert client.post(url, params={"variant": "Glacier glass"}).status_code == 403

    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, dev_tools=True))
    assert client.get("/api/settings").json()["variants"]["2142"] == list(stage.STYLE_PRESETS["2142"]["variants"])
    assert client.post(url, params={"variant": "Warm sculptural"}).status_code == 422

    prompts = []
    generate = client.fake_meta.image_stage

    def capture(image_path, prompt, **kwargs):
        prompts.append(prompt)
        return generate(image_path, prompt, **kwargs)

    monkeypatch.setattr(client.fake_meta, "image_stage", capture)
    res = client.post(url, params={"variant": "Glacier glass"})
    assert res.status_code == 202, res.text
    assert wait_for_job(client, res.json()["job_id"])["status"] == "done"
    assert "Design direction: Glacier glass." in prompts[-1]
    body = client.get(f"/api/listings/{lid}/live").json()
    assert body["rooms"][0]["styles"]["2142"]["variant"] == "Glacier glass"
