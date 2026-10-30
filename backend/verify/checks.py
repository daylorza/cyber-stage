"""The verifier's checks: code checks (files, evidence, geometry, blur) and meta
checks (its own Wonder/SAM calls — never the calls that produced the listing)."""

import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageStat

import cascade
import config

GEOMETRY_MIN_CORR = 0.25
ASPECT_MAX_DEVIATION = 0.03
STRUCTURE_IOU = 0.3
STRUCTURE_EXTRA_ALLOWED = 1
STRUCTURE_EDGE_MARGIN = 0.01
FRAMING_ANCHOR_IOU = 0.5
FRAMING_MIN_ANCHORS = 3
FRAMING_MAX_DRIFT = 0.05
FRAMING_MIN_SPREAD = 0.3
GLASS_DOOR = "glass door"
MIN_REGION_DIFF = 8.0
FACE_MIN_AREA = 0.001

NUM_RE = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)([mM])?(?![\w])")
NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12,
}
WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


def numbers_in(text: str) -> list[float]:
    out = []
    for m in NUM_RE.finditer(text):
        value = float(m.group(1).replace(",", ""))
        if m.group(2):
            value *= 1_000_000
        out.append(value)
    out.extend(float(NUMBER_WORDS[m.group(1).lower()]) for m in WORD_RE.finditer(text))
    return out


def included_rooms(listing: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in listing.get("rooms") or [] if not r.get("rejected")]


def _edges_of(img: Image.Image, size: tuple[int, int] = (96, 54)) -> list[float]:
    return [float(p) for p in img.convert("L").resize(size).filter(ImageFilter.FIND_EDGES).tobytes()]


def _edge_map(path: Path, size: tuple[int, int] = (96, 54)) -> list[float]:
    with Image.open(path) as img:
        return _edges_of(img, size)


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da == 0 and db == 0:
        return 1.0
    if da == 0 or db == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (da * db)


def edge_correlation(path_a: Path, path_b: Path) -> float:
    return _pearson(_edge_map(path_a), _edge_map(path_b))


# ---------- whole-picture framing correction (Day, Oct 28: "Align + glass-door SAM") ----------
# Same rule as the door-based correction approved Oct 28, 18:12 EDT: a global stretch/shift of at
# most 5% is corrected before comparing, it is stated in the check result, and it can only rescue a
# comparison, never break one. When fewer than 3 doors match, the stretch/shift is measured from the
# whole picture (cascade.align, edge maps) instead. Thresholds (edge 0.25, IoU 0.3) are unchanged.

def image_drift(a: dict[str, float]) -> float:
    return max(abs(a["sx"] - 1), abs(a["sy"] - 1), abs(a["bx"]), abs(a["by"]),
               abs(a["sx"] + a["bx"] - 1), abs(a["sy"] + a["by"] - 1))


def _is_identity(a: dict[str, float]) -> bool:
    return a["sx"] == 1 and a["sy"] == 1 and a["bx"] == 0 and a["by"] == 0


def describe_alignment(a: dict[str, float]) -> str:
    tx, ty = a["bx"] - (1 - a["sx"]) / 2, a["by"] - (1 - a["sy"]) / 2
    return f"stretch x {a['sx']:.3f}, y {a['sy']:.3f}; shift x {tx:+.1%}, y {ty:+.1%}"


def aligned_correlation(src: Path, dst: Path, a: dict[str, float]) -> float:
    """Edge correlation after laying the staged image back over the source frame."""
    with Image.open(src) as si, Image.open(dst) as di:
        size = si.size
        source, warped = si.convert("L"), cascade.warp(di.convert("L"), a, size)
    box = cascade._valid_box(a, size, inset=4)
    return _pearson(_edges_of(source.crop(box)), _edges_of(warped.crop(box)))


def geometry(src: Path, dst: Path, align: dict[str, float] | None = None) -> dict[str, Any]:
    """Same aspect ratio and same edge structure as the source frame, with the framing correction."""
    with Image.open(src) as si, Image.open(dst) as di:
        (sw, sh), (dw, dh) = si.size, di.size
    deviation = abs((dw / dh) / (sw / sh) - 1)
    corr = edge_correlation(src, dst)
    out: dict[str, Any] = {"correlation": round(corr, 3), "corrected": False}
    if deviation > ASPECT_MAX_DEVIATION:
        return {**out, "status": "fail", "reason": f"Aspect ratio changed {deviation:.1%} (> {ASPECT_MAX_DEVIATION:.0%})."}
    if corr >= GEOMETRY_MIN_CORR:
        return {**out, "status": "pass",
                "reason": f"Geometry preserved (correlation {corr:.2f}, aspect deviation {deviation:.1%})."}
    a = align if align is not None else cascade.align(src, dst)
    failed = f"Edge structure changed (correlation {corr:.3f} < {GEOMETRY_MIN_CORR})."
    if _is_identity(a):
        return {**out, "status": "fail", "reason": failed}
    drift = image_drift(a)
    if drift > FRAMING_MAX_DRIFT:
        return {**out, "status": "fail",
                "reason": f"{failed} Framing drift {drift:.1%} is over {FRAMING_MAX_DRIFT:.0%}; not corrected."}
    fixed = aligned_correlation(src, dst, a)
    out["corrected_correlation"] = round(fixed, 3)
    if fixed < GEOMETRY_MIN_CORR:
        return {**out, "status": "fail",
                "reason": f"{failed} Still {fixed:.3f} after framing correction ({describe_alignment(a)})."}
    return {**out, "status": "pass", "corrected": True,
            "reason": (f"Geometry preserved after framing correction from the whole picture "
                       f"({describe_alignment(a)}): correlation {corr:.2f} as generated, {fixed:.2f} corrected "
                       f"(threshold {GEOMETRY_MIN_CORR} unchanged).")}


def _iou(a: list[float], b: list[float]) -> float:
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    if inter <= 0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _normalized(box: list[int], size: tuple[int, int]) -> list[float]:
    w, h = size
    return [box[0] / w, box[1] / h, box[2] / w, box[3] / h]


def _region_check(raw_path: Path, blur_path: Path, box: list[int]) -> str | None:
    """None when the privacy-box region is properly blurred, else a failure reason."""
    with Image.open(raw_path) as raw_img, Image.open(blur_path) as blur_img:
        raw_img, blur_img = raw_img.convert("RGB"), blur_img.convert("RGB")
        x1, y1, x2, y2 = box
        sx, sy = blur_img.width / raw_img.width, blur_img.height / raw_img.height
        scaled = (int(x1 * sx), int(y1 * sy), max(int(x2 * sx), int(x1 * sx) + 1),
                  max(int(y2 * sy), int(y1 * sy) + 1))
        raw_crop = raw_img.crop((x1, y1, x2, y2))
        blur_crop = blur_img.crop(scaled).resize(raw_crop.size)
        mean_diff = sum(ImageStat.Stat(ImageChops.difference(raw_crop, blur_crop)).mean) / 3
        if mean_diff < MIN_REGION_DIFF:
            return f"privacy region barely changed (diff {mean_diff:.1f})"
        raw_var = ImageStat.Stat(raw_crop.convert("L").filter(ImageFilter.FIND_EDGES)).var[0]
        blur_var = ImageStat.Stat(blur_crop.convert("L").filter(ImageFilter.FIND_EDGES)).var[0]
        if blur_var >= raw_var:
            return f"edges not softened (raw {raw_var:.0f} -> blurred {blur_var:.0f})"
    return None


def check_frames(ctx, listing: dict[str, Any]) -> None:
    s = config.settings
    frames = listing.get("frames") or []
    if not frames:
        ctx.code("frames", "frames", "fail", "No frames extracted.")
        return
    missing = [
        f["id"] for f in frames
        if not f.get("raw") or not (s.raw_frames_dir / listing["id"] / f["raw"]).is_file()
    ]
    if missing:
        ctx.code("frames", "frames", "fail", f"Raw frames missing on disk: {', '.join(missing)}.")
        return
    ids = {f["id"] for f in frames}
    orphans = [r["id"] for r in listing.get("rooms") or [] if r.get("source_frame") not in ids]
    if orphans:
        ctx.code("frames", "frames", "fail", f"Rooms without a source frame: {', '.join(orphans)}.")
        return
    ctx.code("frames", "frames", "pass", f"{len(frames)} frames on disk.")
    _check_coverage(ctx, listing)


def _check_coverage(ctx, listing: dict[str, Any]) -> None:
    """Independent re-read of video coverage: frames must reach the end of every video."""
    uploads = [i for i, u in enumerate(listing.get("uploads") or [], start=1) if u.get("kind") == "video"]
    if not uploads:
        return
    videos = {v.get("upload"): v for v in listing.get("videos") or []}
    frames = listing.get("frames") or []
    for index in uploads:
        target = {"upload": index}
        video = videos.get(index)
        if video is None:
            ctx.code("frames", f"frames:coverage:{index}", "fail",
                     "Video coverage was not recorded (processed before full-video extraction); "
                     "reprocess the walkthrough.", target)
            continue
        times = [f["t"] for f in frames if f.get("upload") == index and f.get("t") is not None]
        last = max(times, default=None)
        tail = video["duration"] - 2.0
        if video.get("extracted", 0) < video.get("expected", 1) or last is None \
                or (video.get("last_t") or 0) < tail:
            ctx.code("frames", f"frames:coverage:{index}", "fail",
                     f"Frames stop at {_clock(video.get('last_t'))} of a {video['duration']:.1f}s video.", target)
        else:
            ctx.code("frames", f"frames:coverage:{index}", "pass",
                     f"Whole video covered: {video['duration']:.1f}s, {video['extracted']} frames "
                     f"{_clock(video['first_t'])}–{_clock(video['last_t'])}.", target)


def _clock(t: float | None) -> str:
    if t is None:
        return "-:--"
    s = max(0, round(t))
    return f"{s // 60}:{s % 60:02d}"


def check_sam(ctx, listing: dict[str, Any]) -> None:
    frames = listing.get("frames") or []
    by_id = {f["id"]: f for f in frames}
    included = {fid for r in included_rooms(listing) for fid in r.get("frames") or []}
    if not included:
        ctx.code("sam_masks", "sam_masks", "fail", "No included rooms to check.")
        return
    missing = [fid for fid in sorted(included) if not (by_id.get(fid) or {}).get("sam")]
    held = [f["id"] for f in frames if f["id"] not in included and not f.get("sam")]
    if missing:
        ctx.code("sam_masks", "sam_masks", "fail",
                 f"SAM masks missing for included frames: {', '.join(missing)}.")
        return
    reason = f"{len(included)} included frames masked"
    if held:
        reason += f"; {len(held)} frame(s) held back, not used"
    ctx.code("sam_masks", "sam_masks", "pass", reason + ".")


def check_wonder(ctx, listing: dict[str, Any]) -> None:
    frames = listing.get("frames") or []
    by_id = {f["id"]: f for f in frames}
    included = {fid for r in included_rooms(listing) for fid in r.get("frames") or []}
    if not included:
        ctx.code("wonder_classification", "wonder_classification", "fail", "No included rooms to check.")
        return
    missing = [fid for fid in sorted(included) if not (by_id.get(fid) or {}).get("wonder")]
    if missing:
        ctx.code("wonder_classification", "wonder_classification", "fail",
                 f"Included frames not classified: {', '.join(missing)}.")
        return
    unclassified = [r["name"] for r in included_rooms(listing) if r.get("type") == "unclassified"]
    if unclassified:
        ctx.code("wonder_classification", "wonder_classification", "fail",
                 f"Unclassified rooms included: {', '.join(unclassified)}.")
        return
    held = [f["id"] for f in frames if f["id"] not in included and not f.get("wonder")]
    reason = f"{len(included)} included frames classified"
    if held:
        reason += f"; {len(held)} frame(s) held back, not used"
    ctx.code("wonder_classification", "wonder_classification", "pass", reason + ".")


def _claim_code(text: str, evidences: list[dict[str, Any]], facts: dict[str, Any],
                frames_by_id: dict[str, dict[str, Any]],
                included_frame_ids: set[str]) -> tuple[str, str]:
    if not text.strip():
        return "fail", "Claim is empty."
    if not evidences:
        return "fail", f"Claim has no evidence: \"{text[:80]}\""
    attested = any(e.get("kind") == "broker" for e in evidences)
    for ev in evidences:
        kind = ev.get("kind")
        if kind == "fact":
            ref = ev.get("ref")
            if ref not in facts:
                return "fail", f"Fact evidence 'fact:{ref}' is not a supplied fact."
            if ev.get("value") != facts[ref]:
                return "fail", f"Fact evidence 'fact:{ref}' value {ev.get('value')!r} != supplied {facts[ref]!r}."
        elif kind == "visual":
            ref, frame_id = ev.get("ref"), ev.get("frame")
            frame = frames_by_id.get(frame_id)
            recorded = {o["id"] for o in ((frame or {}).get("wonder") or {}).get("observations", [])}
            if ref not in recorded:
                return "fail", f"Visual evidence '{ref}' was not recorded on frame {frame_id}."
            if frame_id not in included_frame_ids:
                return "fail", f"Visual evidence '{ref}' belongs to an excluded or unknown room."
        elif kind == "broker":
            continue
        else:
            return "fail", f"Evidence '{ev.get('ref')}' could not be resolved."
    if attested:
        return "pass", "Broker attested."
    cited: list[float] = []
    for e in evidences:
        value = e.get("value") if e.get("kind") == "fact" else None
        if isinstance(value, (int, float)):
            cited.append(value)
        elif isinstance(value, str):
            cited.extend(numbers_in(value))
    has_visual = any(e.get("kind") == "visual" for e in evidences)
    unmatched = [
        n for n in numbers_in(text)
        if not any(math.isclose(n, v, rel_tol=1e-3, abs_tol=0.5) for v in cited)
    ]
    if unmatched and not has_visual:
        return "fail", f"Claim states {unmatched[0]:g} but no supplied fact has that value."
    return "pass", "Evidence resolves."


def check_claims(ctx, listing: dict[str, Any]) -> None:
    copy = listing.get("copy") or {}
    facts = listing.get("facts") or {}
    claims: list[tuple[str, str, list[dict[str, Any]]]] = [
        ("title", copy.get("title") or "", (copy.get("evidence") or {}).get("title") or [])
    ]
    for claim in (copy.get("sentences") or []) + (copy.get("highlights") or []):
        claims.append((claim.get("id") or "claim", claim.get("text") or "", claim.get("evidence") or []))

    frames_by_id = {f["id"]: f for f in listing.get("frames") or []}
    included_frame_ids = {
        fid for room in included_rooms(listing) for fid in room.get("frames") or []
    }
    for claim_id, text, evidences in claims:
        target = {"claim": claim_id, "text": text[:120]}
        status, reason = _claim_code(text, evidences, facts, frames_by_id, included_frame_ids)
        ctx.code("claim_evidence", f"claim_evidence:{claim_id}", status, reason, target)

        has_visual = any(e.get("kind") == "visual" for e in evidences)
        attested = any(e.get("kind") == "broker" for e in evidences)
        if not has_visual or attested:
            continue
        paths: list[Path] = []
        missing: list[str] = []
        for ev in evidences:
            if ev.get("kind") != "visual":
                continue
            frame = frames_by_id.get(ev.get("frame"))
            rel = frame and frame.get("path")
            path = config.settings.media_dir / rel if rel else None
            if path and path.is_file():
                if path not in paths:
                    paths.append(path)
            else:
                missing.append(str(ev.get("ref")))
        if missing:
            ctx.code("claim_evidence", f"claim_evidence:{claim_id}:images", "unclear",
                     f"Blurred frame missing for evidence: {', '.join(missing)}.", target)
            continue

        def fn(text=text, paths=paths, claim_id=claim_id):
            result = ctx.client.wonder_verify_claim(
                text, paths, trace=ctx.trace, purpose="verify.wonder.claim",
                target={"claim": claim_id},
            )
            status = {"supported": "pass", "unsupported": "fail"}.get(result["verdict"], "unclear")
            return status, result["reason"] or result["verdict"]

        ctx.meta("claim_evidence", f"claim_evidence:{claim_id}:wonder", target, fn,
                 model=getattr(ctx.client, "wonder_model", None),
                 resolution="Remove or reword the claim, or attest it with a broker edit.")


def check_staging(ctx, listing: dict[str, Any]) -> None:
    s = config.settings
    rooms = included_rooms(listing)
    if not rooms:
        ctx.code("staging_geometry", "staging_geometry", "fail",
                 "No rooms remain after broker exclusions.")
        return
    for room in rooms:
        room_id = room["id"]
        check_id = f"staging_geometry:{room_id}"
        target = {"room": room_id}
        before, after = room.get("before"), room.get("after")
        if not after:
            ctx.code("staging_geometry", check_id, "fail", "No staged image.", target)
            continue
        src = s.media_dir / before if before else None
        dst = s.media_dir / after
        if src is None or not src.is_file() or not dst.is_file():
            ctx.code("staging_geometry", check_id, "fail", "Staged or source image missing on disk.", target)
            continue
        result = geometry(src, dst)
        ctx.code("staging_geometry", check_id, result["status"], result["reason"], target)

        def fn(room=room, src=src, dst=dst):
            return _structure_check(ctx, room, src, dst)

        ctx.meta("staging_geometry", f"{check_id}:sam", target, fn,
                 model=getattr(ctx.client, "sam_model", None),
                 resolution="Exclude the room or re-stage it; staging must not move windows or doors.")


def _cut_off(box: list[float]) -> bool:
    """A source box touching the photo edge is only partly in frame; SAM detects such
    partial doors/windows inconsistently, so they are reported as not compared."""
    return min(box[0], box[1], 1 - box[2], 1 - box[3]) <= STRUCTURE_EDGE_MARGIN


def _fit_axis(pairs: list[tuple[list[float], list[float]]], lo: int, hi: int) -> tuple[float, float]:
    """Stretch + shift on one axis. Stretch is only estimated when the matching doors span
    FRAMING_MIN_SPREAD of the frame on this axis; bunched doors give a shift-only fit."""
    xs = [s[i] for s, _ in pairs for i in (lo, hi)]
    ys = [d[i] for _, d in pairs for i in (lo, hi)]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    if max(xs) - min(xs) < FRAMING_MIN_SPREAD:
        return 1.0, my - mx
    var = sum((x - mx) ** 2 for x in xs)
    scale = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var
    return scale, my - scale * mx


def _framing(src_doors: list[list[float]], dst_doors: list[list[float]]) -> dict[str, float] | None:
    """Global stretch/shift of the staged image vs the source, fitted (least squares, per axis)
    on in-frame doors that already match well. None with fewer than FRAMING_MIN_ANCHORS.
    drift = the largest stretch or edge displacement, as a fraction of the frame."""
    anchors = []
    for s in src_doors:
        best = max(dst_doors, key=lambda d: _iou(s, d), default=None)
        if not _cut_off(s) and best is not None and _iou(s, best) >= FRAMING_ANCHOR_IOU:
            anchors.append((s, best))
    if len(anchors) < FRAMING_MIN_ANCHORS:
        return None
    sx, tx = _fit_axis(anchors, 0, 2)
    sy, ty = _fit_axis(anchors, 1, 3)
    drift = max(abs(sx - 1), abs(sy - 1), abs(tx), abs(sx + tx - 1), abs(ty), abs(sy + ty - 1))
    return {"sx": sx, "tx": tx, "sy": sy, "ty": ty, "drift": drift, "anchors": len(anchors)}


def _corrected(box: list[float], f: dict[str, float]) -> list[float]:
    return [f["sx"] * box[0] + f["tx"], f["sy"] * box[1] + f["ty"],
            f["sx"] * box[2] + f["tx"], f["sy"] * box[3] + f["ty"]]


def _inside(box: list[float], outer: list[float]) -> float:
    """Share of `box` that lies inside `outer`."""
    inter = max(0.0, min(box[2], outer[2]) - max(box[0], outer[0])) * \
        max(0.0, min(box[3], outer[3]) - max(box[1], outer[1]))
    area = (box[2] - box[0]) * (box[3] - box[1])
    return inter / area if area > 0 else 0.0


def _outside_view(box: list[float], src_by: dict[str, list[list[float]]]) -> bool:
    """A window seen THROUGH the room's own glass (a building across the street): it sits inside
    a much larger window box, or inside a glass door box that shows several such windows (a
    facade seen through a sliding door). Muse Image redraws the outside view, so these are
    reported separately from the room's own structure. A single window inside a door box (a
    transom or door pane) is NOT treated as outside view and stays a room-structure problem."""
    area = (box[2] - box[0]) * (box[3] - box[1])
    windows = src_by.get("window", [])

    def holds(outer: list[float]) -> bool:
        return outer is not box and (outer[2] - outer[0]) * (outer[3] - outer[1]) >= 2.5 * area \
            and _inside(box, outer) >= 0.8

    # Inside a much larger window, or anywhere inside a glass door (SAM "glass door" on the source).
    if any(holds(other) for other in windows + src_by.get(GLASS_DOOR, [])):
        return True
    return any(
        holds(door) and sum(1 for w in windows if w is not box and _inside(w, door) >= 0.8) >= 1
        for door in src_by.get("door", [])
    )


def compare_structure(src_by: dict[str, list[list[float]]],
                      dst_by: dict[str, list[list[float]]],
                      image_align: dict[str, float] | None = None) -> dict[str, Any]:
    """Windows/doors (normalized boxes) on the staged image vs the source frame.

    Cut-off boxes are not compared; a small global framing drift (<= 5%) is corrected before
    comparing, fitted on doors that already match or, with fewer than 3 of those, measured from the
    whole picture (`image_align`, staged -> frame); IoU stays 0.3. Windows seen through the room's
    own glass (`src_by["glass door"]`) are reported as `outside`, separately from `problems`.
    """
    problems: list[str] = []
    outside: list[str] = []
    skipped: list[str] = []
    compared = rescued = 0
    # Muse Image re-frames slightly per generation; a small global drift is corrected so it
    # doesn't read as moved doors/windows. The correction can only rescue a match, never break one.
    framing = _framing(src_by.get("door", []), dst_by.get("door", []))
    correct = framing is not None and framing["drift"] <= FRAMING_MAX_DRIFT
    whole = (not correct and image_align is not None and not _is_identity(image_align)
             and image_drift(image_align) <= FRAMING_MAX_DRIFT)
    moved_dst = ({k: [cascade.to_frame(b, image_align) for b in v] for k, v in dst_by.items()}
                 if whole and image_align is not None else {})
    for concept in ("window", "door"):
        src_norm, dst_norm = src_by.get(concept, []), dst_by.get(concept, [])
        for i, box in enumerate(src_norm, start=1):
            if _cut_off(box):
                skipped.append(f"{concept} #{i}")
                continue
            compared += 1
            if any(_iou(box, d) >= STRUCTURE_IOU for d in dst_norm):
                continue
            if correct and any(_iou(_corrected(box, framing), d) >= STRUCTURE_IOU for d in dst_norm):
                rescued += 1
                continue
            if whole and any(_iou(box, d) >= STRUCTURE_IOU for d in moved_dst.get(concept, [])):
                rescued += 1
                continue
            label = f"{concept} #{i} moved or removed"
            (outside if concept == "window" and _outside_view(box, src_by) else problems).append(label)
        in_src = sum(not _cut_off(b) for b in src_norm)
        in_dst = sum(not _cut_off(b) for b in dst_norm)
        if in_dst > in_src + STRUCTURE_EXTRA_ALLOWED:
            problems.append(f"{in_dst - in_src} extra {concept}(s) added")
    note = f" Not compared (cut off at the photo edge): {', '.join(skipped)}." if skipped else ""
    if correct:
        note += (f" Framing corrected before comparing ({framing['anchors']} matching doors: "
                 f"stretch x {framing['sx']:.3f}, y {framing['sy']:.3f}; "
                 f"shift x {framing['tx']:+.1%}, y {framing['ty']:+.1%}): "
                 + (f"{rescued} item(s) matched only after correction." if rescued else "no item needed it."))
    elif whole and image_align is not None:
        note += (f" Framing corrected from the whole picture before comparing (fewer than 3 matching "
                 f"doors; {describe_alignment(image_align)}): "
                 + (f"{rescued} item(s) matched only after correction." if rescued else "no item needed it."))
    elif framing is not None:
        note += (f" Framing drift {framing['drift']:.1%} ({framing['anchors']} matching doors) "
                 f"is over {FRAMING_MAX_DRIFT:.0%}; not corrected.")
    if outside:
        note += f" Outside view (seen through the room's glass, reported separately): {'; '.join(outside)}."
    return {"problems": problems, "outside": outside, "skipped": skipped, "compared": compared,
            "rescued": rescued, "framing": framing, "corrected": correct or whole, "note": note}


def _structure_check(ctx, room: dict[str, Any], src: Path, dst: Path) -> tuple[str, str]:
    with Image.open(src) as si, Image.open(dst) as di:
        src_size, dst_size = si.size, di.size
    src_by: dict[str, list[list[float]]] = {}
    dst_by: dict[str, list[list[float]]] = {}
    for concept in ("window", "door"):
        src_boxes = ctx.client.sam_segment(
            src, concept, trace=ctx.trace, purpose="verify.sam.structure",
            target={"room": room["id"], "concept": concept, "side": "before"})
        dst_boxes = ctx.client.sam_segment(
            dst, concept, trace=ctx.trace, purpose="verify.sam.structure",
            target={"room": room["id"], "concept": concept, "side": "after"})
        src_by[concept] = [_normalized(b["box"], src_size) for b in src_boxes]
        dst_by[concept] = [_normalized(b["box"], dst_size) for b in dst_boxes]
    # The room's own glass doors (sliding/balcony): windows behind them are outside view.
    glass = ctx.client.sam_segment(
        src, GLASS_DOOR, trace=ctx.trace, purpose="verify.sam.structure",
        target={"room": room["id"], "concept": GLASS_DOOR, "side": "before"})
    src_by[GLASS_DOOR] = [_normalized(b["box"], src_size) for b in glass]
    result = compare_structure(src_by, dst_by, image_align=cascade.align(src, dst))
    note = result["note"]
    if result["problems"]:
        return "fail", f"Staging changed structure: {'; '.join(result['problems'])}.{note}"
    if result["outside"]:
        # Still flagged, but labelled: the room's own windows and doors held.
        return "fail", f"Room structure preserved; only the outside view changed.{note}"
    if result["skipped"] and not result["compared"]:
        return "pass", f"No windows or doors fully in frame to compare.{note}"
    return "pass", f"Windows and doors preserved.{note}"


def check_comps(ctx, listing: dict[str, Any]) -> None:
    comps = listing.get("comps") or {}
    if comps.get("source") == "demo" and "demo" in str(comps.get("label", "")).lower():
        ctx.code("comps_demo", "comps_demo", "pass", str(comps["label"]))
    else:
        ctx.code("comps_demo", "comps_demo", "fail", "Comps are not labeled demo.")


def check_blur(ctx, listing: dict[str, Any]) -> None:
    s = config.settings
    media_root = s.media_dir.resolve()
    raw_dir = s.raw_frames_dir / listing["id"]
    frames = listing.get("frames") or []
    problems: list[str] = []
    held: list[str] = []
    good_paths: set[str] = set()
    if raw_dir.resolve().is_relative_to(media_root):
        problems.append("raw frames directory is inside media_dir")
    if not frames:
        problems.append("no frames")
    for frame in frames:
        rel = frame.get("path")
        if not rel:
            held.append(frame["id"])
            continue
        resolved = (s.media_dir / rel).resolve()
        if not resolved.is_relative_to(media_root) or not resolved.is_file():
            problems.append(f"{frame['id']} publishable copy missing or outside media_dir")
            continue
        ok = True
        raw = raw_dir / (frame.get("raw") or "")
        for box in (frame.get("sam") or {}).get("privacy", []):
            issue = _region_check(raw, resolved, box["box"])
            if issue:
                problems.append(f"{frame['id']}: {issue}")
                ok = False
        if ok:
            good_paths.add(rel)
    rooms = included_rooms(listing)
    if frames and not rooms:
        problems.append("no included rooms")
    for room in rooms:
        if room.get("before") not in good_paths:
            problems.append(f"{room['id']} before image is not a blurred frame")
    if problems:
        ctx.code("blur_pass", "blur_pass", "fail", "; ".join(problems[:4]) + ".")
    else:
        reason = "All publishable frames blurred"
        if held:
            reason += f"; {len(held)} frame(s) held back, never served"
        ctx.code("blur_pass", "blur_pass", "pass", reason + ".")

    for video in listing.get("videos") or []:
        status, reason = _video_check(listing, video, raw_dir)
        ctx.code("blur_pass", f"blur_pass:video:{video.get('upload')}", status, reason,
                 {"upload": video.get("upload")})

    for room in included_rooms(listing):
        for side in ("before", "after"):
            rel = room.get(side)
            if not rel:
                continue

            def fn(path=s.media_dir / rel, room=room, side=side):
                return _face_check(ctx, room, path, side)

            ctx.meta("blur_pass", f"blur_pass:faces:{room['id']}:{side}",
                     {"room": room["id"], "side": side}, fn,
                     model=getattr(ctx.client, "sam_model", None),
                     resolution="Re-run the blur pass or exclude the room before publishing.")


def _video_check(listing: dict[str, Any], video: dict[str, Any], raw_dir: Path) -> tuple[str, str]:
    """The published video must live under media_dir, carry no audio, and show every SAM privacy
    region blurred at the frame where SAM found it (read back from the encoded file)."""
    s = config.settings
    if video.get("status") != "ready" or not video.get("path"):
        return "pass", f"Walkthrough video not published ({video.get('detail') or 'held back'}); nothing served."
    path = (s.media_dir / video["path"]).resolve()
    if not path.is_relative_to(s.media_dir.resolve()) or not path.is_file():
        return "fail", "Published walkthrough video is missing or outside media_dir."
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=False,
    )
    if "audio" in probe.stdout:
        return "fail", "Published walkthrough video still has an audio track."
    frames = [f for f in listing.get("frames") or []
              if f.get("upload") == video.get("upload") and (f.get("sam") or {}).get("privacy")]
    checked = 0
    with tempfile.TemporaryDirectory() as tmp:
        for frame in frames:
            still = Path(tmp) / f"{frame['id']}.png"
            # Times are rounded to 1 ms: seek 4 ms early so the frame itself is not skipped
            # (ffmpeg drops frames stamped before the seek point; 1/30 s of pan moves a lot).
            subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{max(0.0, frame['t'] - 0.004):.3f}",
                 "-i", str(path),
                 "-frames:v", "1", str(still)],
                capture_output=True, check=False,
            )
            if not still.is_file():
                return "fail", f"Could not read the published video at {_clock(frame['t'])} to check the blur."
            for box in frame["sam"]["privacy"]:
                issue = _region_check(raw_dir / frame["raw"], still, box["box"])
                if issue:
                    return "fail", f"Published video at {_clock(frame['t'])} ({frame['id']}): {issue}."
                checked += 1
    return "pass", (f"Published video {video['duration']:.1f}s, no audio; {checked} privacy region(s) "
                    "read back from the encoded file and blurred.")


def _face_check(ctx, room: dict[str, Any], path: Path, side: str) -> tuple[str, str]:
    with Image.open(path) as img:
        area = img.width * img.height
    boxes = ctx.client.sam_segment(
        path, "face", trace=ctx.trace, purpose="verify.sam.faces",
        target={"room": room["id"], "side": side})
    big = [
        b for b in boxes
        if (b["box"][2] - b["box"][0]) * (b["box"][3] - b["box"][1]) >= FACE_MIN_AREA * area
    ]
    if big:
        return "fail", f"A face may still be visible in {room['name']} ({side})."
    return "pass", f"No faces in {side}."
