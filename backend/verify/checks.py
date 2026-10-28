"""The verifier's checks: code checks (files, evidence, geometry, blur) and meta
checks (its own Wonder/SAM calls — never the calls that produced the listing)."""

import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageStat

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


def _edge_map(path: Path, size: tuple[int, int] = (96, 54)) -> list[float]:
    with Image.open(path) as img:
        img = img.convert("L").resize(size).filter(ImageFilter.FIND_EDGES)
        return [float(p) for p in img.tobytes()]


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
        with Image.open(src) as si, Image.open(dst) as di:
            sw, sh = si.size
            dw, dh = di.size
        deviation = abs((dw / dh) / (sw / sh) - 1)
        corr = edge_correlation(src, dst)
        if deviation > ASPECT_MAX_DEVIATION:
            ctx.code("staging_geometry", check_id, "fail",
                     f"Aspect ratio changed {deviation:.1%} (> {ASPECT_MAX_DEVIATION:.0%}).", target)
        elif corr < GEOMETRY_MIN_CORR:
            ctx.code("staging_geometry", check_id, "fail",
                     f"Edge structure changed (correlation {corr:.2f} < {GEOMETRY_MIN_CORR}).", target)
        else:
            ctx.code("staging_geometry", check_id, "pass",
                     f"Geometry preserved (correlation {corr:.2f}, aspect deviation {deviation:.1%}).", target)

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


def _structure_check(ctx, room: dict[str, Any], src: Path, dst: Path) -> tuple[str, str]:
    problems: list[str] = []
    skipped: list[str] = []
    compared = rescued = 0
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
    # Muse Image re-frames slightly per generation; a small global drift is corrected so it
    # doesn't read as moved doors/windows. The correction can only rescue a match, never break one.
    framing = _framing(src_by["door"], dst_by["door"])
    correct = framing is not None and framing["drift"] <= FRAMING_MAX_DRIFT
    for concept in ("window", "door"):
        src_norm, dst_norm = src_by[concept], dst_by[concept]
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
            problems.append(f"{concept} #{i} moved or removed")
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
    elif framing is not None:
        note += (f" Framing drift {framing['drift']:.1%} ({framing['anchors']} matching doors) "
                 f"is over {FRAMING_MAX_DRIFT:.0%}; not corrected.")
    if problems:
        return "fail", f"Staging changed structure: {'; '.join(problems)}.{note}"
    if skipped and not compared:
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
