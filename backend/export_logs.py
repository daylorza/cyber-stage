"""Plain-text export of everything the broker console knows about ONE listing.

Read-only renderer behind GET /api/listings/{id}/export. It takes the stored
listing dict plus its job rows and returns a pasteable text file: every frame,
room, claim, check, flag, trace entry and job, in UI wording. It never writes
to the DB, never calls a model, and scrubs API keys and raw/upload paths.
"""

import os
import re
import subprocess
from datetime import datetime
from typing import Any

import checklist
import config
from pipeline.frames import coverage_line
from pipeline.stage import STYLE_PRESETS

# Key-like shapes that must never leave the server, even inside stored content.
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{16,}",
    r"Bearer\s+\S{8,}",
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+",
]
_SECRET_RES = [re.compile(p) for p in SECRET_PATTERNS]

# Purpose labels, ported from DecisionPanel.tsx so the export matches the UI.
PURPOSE = {
    "sam.privacy": "SAM privacy masks",
    "sam.structure": "SAM structure",
    "wonder.classify": "Wonder room read",
    "image.stage": "Muse Image staging",
    "image.restage": "Muse Image re-stage (stricter)",
    "sam.staged_faces": "SAM faces on staged image",
    "spark.copy": "Spark copy",
    "verify.wonder.claim": "Wonder claim check",
    "verify.sam.structure": "SAM geometry check",
    "verify.sam.faces": "SAM face check",
}

FACT_ORDER = ["name", "address", "city", "beds", "baths", "sqft", "price", "currency",
              "estimate_price"]


def app_commit() -> str:
    """Best-effort app version stamp for the export header. Never raises."""
    commit = (os.environ.get("VRE_APP_COMMIT") or "").strip()
    if commit:
        return commit
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=config.REPO_DIR, capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def filename(listing_id: str, exported_at: datetime) -> str:
    return f"listing-{listing_id}-logs-{exported_at.strftime('%Y%m%d-%H%M')}.txt"


def scrub(text: str) -> str:
    """Last-pass safety net: redact the live API key and key-shaped strings."""
    key = os.environ.get("META_API_KEY") or ""
    if len(key) >= 8:
        text = text.replace(key, "[redacted]")
    for pattern in _SECRET_RES:
        text = pattern.sub("[redacted]", text)
    return text


def clock(seconds: float) -> str:
    s = max(0, round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def _pct(coverage: Any) -> str:
    try:
        return f"{round(float(coverage) * 100)}%"
    except (TypeError, ValueError):
        return "unknown"


def _media(path: Any) -> str:
    """Only blurred/staged media paths may appear; anything else is held back."""
    if not isinstance(path, str) or not path:
        return "none"
    if path.startswith("/") or any(bad in path for bad in ("frames_raw", "staged_raw", "uploads/")):
        return "[held back]"
    return path


def _rooms(listing: dict[str, Any]) -> list[dict[str, Any]]:
    return listing.get("rooms") or []


def _room_name(listing: dict[str, Any], room_id: Any) -> str:
    for room in _rooms(listing):
        if room.get("id") == room_id:
            return room.get("name") or str(room_id)
    return str(room_id)


def _frame_room(listing: dict[str, Any], frame_id: str) -> dict[str, Any] | None:
    for room in _rooms(listing):
        if frame_id in (room.get("frames") or []):
            return room
    return None


def _model_name(model: Any) -> str:
    m = str(model or "").lower()
    if "wonder" in m:
        return "Wonder"
    if "sam" in m:
        return "SAM 3.1"
    if "spark" in m:
        return "Spark"
    if "image" in m:
        return "Muse Image"
    return str(model) if model else "Code"


def _evidence_line(ev: dict[str, Any], listing: dict[str, Any]) -> str:
    kind = ev.get("kind")
    if kind == "fact":
        return f"Fact · {ev.get('ref')} = {ev.get('value')}"
    if kind == "broker":
        return "Broker attested"
    if kind == "visual":
        room = _room_name(listing, ev.get("room_id"))
        line = f"Seen · {room} · {ev.get('text')}"
        if ev.get("t") is not None:
            line += f" · {clock(ev['t'])}"
        return line
    return "Unresolved pointer"


def _evidence_detail(ev: dict[str, Any], listing: dict[str, Any]) -> str:
    line = _evidence_line(ev, listing)
    refs = [f"ref={ev.get('ref')}"]
    if ev.get("frame"):
        refs.append(f"frame={ev['frame']}")
    if ev.get("room_id"):
        refs.append(f"room={ev['room_id']}")
    return f"{line} ({', '.join(refs)})"


def _checks(listing: dict[str, Any]) -> list[dict[str, Any]]:
    return ((listing.get("verification") or {}).get("checks")) or []


def _claim_result(listing: dict[str, Any], claim_id: Any, evidence: Any) -> str:
    checks = _checks(listing)
    own = [c for c in checks if claim_id and (c.get("target") or {}).get("claim") == claim_id]
    if not own:
        return "Checks run on save"
    bad = next((c for c in own if c.get("status") == "fail"), None) or next(
        (c for c in own if c.get("status") == "unclear"), None)
    if bad:
        label = "Not supported" if bad.get("status") == "fail" else "Unclear"
        return f"{label} · {bad.get('reason')}"
    meta = next((c for c in own if c.get("kind") == "meta"), None)
    if meta:
        return f"Verified by {_model_name(meta.get('model'))}"
    if any((e or {}).get("kind") == "fact" for e in (evidence or [])):
        return "Matches supplied fact"
    return "Evidence resolves"


def _flag_target(flag: dict[str, Any], listing: dict[str, Any]) -> str:
    target = flag.get("target") or {}
    claim, room = target.get("claim"), target.get("room")
    if claim == "title":
        return "Title (claim: title)"
    if claim:
        return f"{target.get('text') or claim} (claim: {claim})"
    if room:
        return f"{_room_name(listing, room)} (room: {room})"
    items = (listing.get("checklist") or {}).get("items") or []
    label = next((i.get("label") for i in items if i.get("id") == flag.get("item")), None)
    return f"{label or flag.get('item')} (item: {flag.get('item')})"


def _target_text(target: Any, listing: dict[str, Any]) -> str:
    t = target or {}
    parts: list[str] = []
    room = t.get("room")
    if isinstance(room, str):
        parts.append(_room_name(listing, room))
    if isinstance(t.get("frame"), str):
        parts.append(t["frame"])
    claim = t.get("claim")
    if isinstance(claim, str):
        copy = listing.get("copy") or {}
        if claim == "title":
            text = copy.get("title")
        else:
            claims = (copy.get("highlights") or []) + (copy.get("sentences") or [])
            found = next((c for c in claims if c.get("id") == claim), None)
            text = found.get("text") if found else None
        parts.append(str(text or claim))
    if isinstance(t.get("concept"), str):
        parts.append(t["concept"])
    if isinstance(t.get("side"), str):
        parts.append(t["side"])
    if not parts and isinstance(t.get("frames"), (int, float)):
        parts.append(f"{t['frames']} frames")
    return " · ".join(parts)


def _summary_line(listing: dict[str, Any]) -> str:
    items = (listing.get("checklist") or {}).get("items") or []
    open_items = [i for i in items if i.get("status") != "done"]
    verification = listing.get("verification")
    if not open_items and verification and verification.get("passed"):
        return f"All checks passed · {verification.get('ran_at')}"
    if not open_items:
        return "Awaiting verification"
    if not checklist.checks_block(listing):
        return f"{len(open_items)} open · warnings only (demo mode, not blocking Approve/Publish)"
    return f"Publish blocked · {len(open_items)} open"


def _claim_rows(listing: dict[str, Any]) -> list[tuple[str, Any, str, list[dict[str, Any]]]]:
    copy = listing.get("copy") or {}
    rows: list[tuple[str, Any, str, list[dict[str, Any]]]] = []
    if copy:
        rows.append(("title", "title", copy.get("title") or "",
                     (copy.get("evidence") or {}).get("title") or []))
    for claim in (copy.get("highlights") or []):
        rows.append(("highlight", claim.get("id"), claim.get("text") or "", claim.get("evidence") or []))
    for claim in (copy.get("sentences") or []):
        rows.append(("sentence", claim.get("id"), claim.get("text") or "", claim.get("evidence") or []))
    return rows


def _section_listing(listing: dict[str, Any], meta: dict[str, Any], lines: list[str]) -> None:
    copy = listing.get("copy") or {}
    review = listing.get("review") or {}
    facts = listing.get("facts") or {}
    uploads = listing.get("uploads") or []
    style = listing.get("style") or "modern-luxury"
    preset = STYLE_PRESETS.get(style) or {}

    lines.append("## 1. Listing")
    lines.append("")
    lines.append(f"ID: {listing.get('id')}")
    lines.append(f"Title: {copy.get('title') or '(no listing copy yet)'}")
    if listing.get("note"):
        lines.append(f"Label: {listing['note']}")
    lines.append(f"Status: {listing.get('status')}")
    lines.append(f"Source: {listing.get('source')}")
    lines.append(
        f"Review: decision={review.get('decision') or 'none'} · "
        f"decided_at={review.get('decided_at') or 'none'}"
    )
    if review.get("open_checks"):
        lines.append(f"Approved with open checks: {', '.join(review['open_checks'])}")
    lines.append(f"Checks mode: {'blocking' if checklist.checks_block(listing) else 'warnings only (demo mode)'}")
    lines.append(f"Edited fields: {', '.join(review.get('edited_fields') or []) or 'none'}")
    lines.append(f"Broker notes: {review.get('notes') or 'none'}")
    lines.append(f"Style preset: {style} ({preset.get('label', 'unknown preset')})")
    lines.append("Supplied facts:")
    ordered = [k for k in FACT_ORDER if k in facts]
    ordered += [k for k in facts if k not in FACT_ORDER]
    if not ordered:
        lines.append("  (none supplied)")
    for key in ordered:
        value = facts.get(key)
        lines.append(f"  {key} = {value if value is not None else '(not supplied)'}")
    if uploads:
        kinds: dict[str, int] = {}
        for upload in uploads:
            kinds[upload.get("kind") or "?"] = kinds.get(upload.get("kind") or "?", 0) + 1
        kinds_text = ", ".join(f"{kind} x{count}" for kind, count in sorted(kinds.items()))
        lines.append(f"Uploads: {len(uploads)} file(s) · kinds: {kinds_text} (names and paths withheld)")
    else:
        lines.append("Uploads: none")
    lines.append(f"created_at: {listing.get('created_at')}")
    lines.append(f"updated_at: {listing.get('updated_at')}")
    lines.append(f"Current job: {listing.get('job_id') or 'none'}")
    lines.append(f"Listing error: {listing.get('error') or 'none'}")
    models = (meta or {}).get("models") or {}
    model_text = ", ".join(f"{k}={models.get(k)}" for k in ("spark", "wonder", "image", "sam"))
    lines.append(f"Meta status: configured={'yes' if (meta or {}).get('configured') else 'no'} · models: {model_text}")
    published = listing.get("published")
    if published:
        ver = published.get("verification") or {}
        lines.append("Published snapshot:")
        lines.append(f"  published_at: {published.get('published_at')}")
        lines.append(f"  approved_at: {published.get('approved_at')}")
        lines.append(f"  Verification passed: {'yes' if ver.get('passed') else 'no'}")
        lines.append(f"  verification ran_at: {ver.get('ran_at')}")
        lines.append(f"  checks: {ver.get('checks')}")
        names = [f"{r.get('name')} ({r.get('id')})" for r in published.get("rooms") or []]
        lines.append(f"  published rooms: {', '.join(names) or 'none'}")
    else:
        lines.append("Published snapshot: not published")
    lines.append("")


def _section_video(listing: dict[str, Any], lines: list[str]) -> None:
    lines.append("## 1b. Walkthrough video · main living room · token guard")
    lines.append("")
    videos = listing.get("videos") or []
    if not videos:
        has_video = any(u.get("kind") == "video" for u in listing.get("uploads") or [])
        lines.append("Video coverage: not recorded (processed before full-video extraction)" if has_video
                     else "Video coverage: no video upload")
    for video in videos:
        lines.append(f"Upload {video.get('upload')}: {coverage_line(video)}")
        lines.append(f"  duration: {video.get('duration')} s · frames extracted: {video.get('extracted')} "
                     f"(expected >= {video.get('expected')}) · first frame t={video.get('first_t')} s · "
                     f"last frame t={video.get('last_t')} s · kept: {video.get('kept')}")
        lines.append(f"  published video: {video.get('status') or 'not built'} · {_media(video.get('path'))} · "
                     f"{video.get('detail') or ''}".rstrip())
        if video.get("note"):
            lines.append(f"  note: {video['note']}")
    main = listing.get("main_room") or {}
    lines.append(f"Main living room: {main.get('detail') or 'not decided yet'}")
    guard = listing.get("token_guard") or {}
    if guard:
        lines.append(f"Token guard: {guard.get('status')} · {guard.get('detail')}")
        lines.append(f"  staging order: {', '.join(guard.get('order') or []) or 'none'} · "
                     f"held: {', '.join(guard.get('skipped') or []) or 'none'} · at {guard.get('at')}")
    else:
        lines.append("Token guard: not recorded")
    lines.append("")


def _section_live(listing: dict[str, Any], lines: list[str]) -> None:
    live_block = listing.get("live") or {}
    lines.append("## 7b. Live-In-It preparation")
    lines.append("")
    if not live_block:
        lines.append("Not prepared.")
        lines.append("")
        return
    trace = live_block.get("trace") or []
    spent = sum(1 for t in trace if not t.get("cached"))
    lines.append(f"Status: {live_block.get('status')} · prepared_at: {live_block.get('prepared_at') or 'none'} · "
                 f"error: {live_block.get('error') or 'none'}")
    lines.append(f"Meta calls: {len(trace)} traced · {spent} new · {len(trace) - spent} from cache")
    guard = live_block.get("guard") or {}
    if guard:
        lines.append(f"Order: {', '.join(guard.get('order') or [])} (main room {guard.get('main_room')} first) · "
                     f"utility rooms walked past, not staged: {', '.join(guard.get('skipped_utility') or []) or 'none'}"
                     + (f" · held: {', '.join(guard['held'])}" if guard.get("held") else ""))
    for room in live_block.get("rooms") or []:
        lines.append(f"- {room.get('name')} ({room.get('id')}) · t={room.get('t')} · plate: {room.get('plate_source')}")
        for style_id, entry in (room.get("styles") or {}).items():
            state = "available" if entry.get("available") else f"disabled: {entry.get('error') or ''}"
            if not entry.get("available"):
                for key in ("geometry", "structure"):
                    check = entry.get(key) or {}
                    if check.get("status") == "fail":
                        state += f" {check.get('reason')}"
            align = entry.get("align") or {}
            lines.append(f"    {style_id}: {state.strip()} · pieces: {len(entry.get('pieces') or [])} · "
                         f"mask: {_media(entry.get('mask'))} · align: "
                         + (f"stretch {align.get('sx')}/{align.get('sy')} shift {align.get('bx')}/{align.get('by')}"
                            if align else "none"))
            outside = (entry.get("structure") or {}).get("outside_view") or []
            if outside:
                lines.append(f"      outside view (reported separately, not blocking): {'; '.join(outside)}")
    lines.append("")


def _section_checks(listing: dict[str, Any], lines: list[str]) -> None:
    checklist = listing.get("checklist") or {}
    verification = listing.get("verification")

    lines.append("## 2. Pipeline checks")
    lines.append("")
    lines.append(_summary_line(listing))
    lines.append(f"Checklist created_at: {checklist.get('created_at') or 'none'}")
    items = checklist.get("items") or []
    if not items:
        lines.append("(no checklist items)")
    for item in items:
        detail = f" — {item.get('detail')}" if item.get("detail") else ""
        lines.append(f"[{item.get('status')}] {item.get('label')}{detail} (updated {item.get('updated_at')})")
    lines.append("")
    if verification is None:
        lines.append("Verification: not run")
    else:
        checks = verification.get("checks") or []
        flags = verification.get("flags") or []
        lines.append(
            f"Verification: ran_at={verification.get('ran_at')} · "
            f"passed={'yes' if verification.get('passed') else 'no'} · "
            f"checks={len(checks)} · flags={len(flags)}"
        )
        lines.append("Checks:")
        if not checks:
            lines.append("  (no checks recorded)")
        for check in checks:
            target = _target_text(check.get("target"), listing) or "-"
            lines.append(
                f"- {check.get('id')} · {check.get('item')} · {check.get('kind')} · "
                f"{check.get('model') or 'code'} · {check.get('status')} · "
                f"{target} · {check.get('reason')}"
            )
    lines.append("")


def _section_flags(listing: dict[str, Any], lines: list[str]) -> None:
    flags = ((listing.get("verification") or {}).get("flags")) or []
    lines.append(f"## 3. Needs your attention · {len(flags)}")
    lines.append("")
    if not flags:
        lines.append("Nothing flagged.")
    for flag in flags:
        lines.append(f"- {flag.get('id')} · item={flag.get('item')} · {_flag_target(flag, listing)}")
        lines.append(f"  message: {flag.get('message')}")
        lines.append(f"  resolution: {flag.get('resolution')}")
    lines.append("")


def _room_issues(listing: dict[str, Any], room_id: Any) -> list[dict[str, Any]]:
    return [
        c for c in _checks(listing)
        if (c.get("target") or {}).get("room") == room_id and c.get("status") != "pass"
    ]


def _room_lines(listing: dict[str, Any], room: dict[str, Any], lines: list[str]) -> None:
    frames = {f.get("id"): f for f in listing.get("frames") or []}
    hero = frames.get(room.get("source_frame"))
    hero_cov = ((hero or {}).get("wonder") or {}).get("coverage")
    staging = room.get("staging")

    lines.append(f"- {room.get('name')} ({room.get('id')}) · type={room.get('type')} · "
                 f"excluded: {'yes' if room.get('rejected') else 'no'}"
                 + (" · MAIN LIVING ROOM" if room.get("main") else ""))
    if room.get("t") is not None:
        span = room.get("span") or [room["t"], room["t"]]
        lines.append(f"  video: hero at {clock(room['t'])} · segment {clock(span[0] or 0)}–{clock(span[1] or 0)}")
    lines.append(f"  hero frame: {room.get('source_frame') or 'none'} · coverage {_pct(hero_cov)} · "
                 f"{room.get('hero_reason') or ''}".rstrip())
    lines.append(f"  frames: {', '.join(room.get('frames') or []) or 'none'}")
    lines.append(f"  before: {_media(room.get('before'))} · after: {_media(room.get('after'))}")
    if staging:
        lines.append(f"  staged style: {staging.get('style') or room.get('style') or 'none'} · "
                     f"model: {staging.get('model') or 'none'}"
                     + (f" · stricter re-stage, level {staging['level']}"
                        if staging.get("level") else ""))
        lines.append(f"  staging error: {staging.get('error') or 'none'}")
        lines.append(f"  staging prompt: {staging.get('prompt') or 'none'}")
    else:
        lines.append("  staging: not staged")
    for entry in room.get("staging_history") or []:
        lines.append(
            f"  earlier staging: level {entry.get('level') or 'initial'} · "
            f"after: {_media(entry.get('after'))} · "
            f"replaced_at: {entry.get('replaced_at') or 'none'} · "
            f"error: {entry.get('error') or 'none'}"
        )
    restage_error = room.get("restage_error")
    if restage_error:
        lines.append(
            f"  re-stage error: level {restage_error.get('level')} · "
            f"{restage_error.get('error')} · at {restage_error.get('at') or 'none'}"
        )
    issues = _room_issues(listing, room.get("id"))
    if issues:
        lines.append("  checks needing attention:")
        for check in issues:
            lines.append(f"    - {check.get('id')} · {check.get('status')} · {check.get('reason')}")
    else:
        lines.append("  checks needing attention: none")


def _section_rooms(listing: dict[str, Any], lines: list[str]) -> None:
    rooms = _rooms(listing)
    lines.append(f"## 4. Rooms · {len(rooms)}")
    lines.append("")
    if not rooms:
        lines.append("No rooms.")
    for room in rooms:
        _room_lines(listing, room, lines)
    lines.append("")


def _claim_block(listing: dict[str, Any], label: str, claim_id: Any, text: str,
                 evidence: list[dict[str, Any]], lines: list[str]) -> None:
    lines.append(f"- [{label}] {claim_id}: {text}")
    if evidence:
        lines.append("  evidence:")
        for ev in evidence:
            lines.append(f"    {_evidence_detail(ev, listing)}")
    else:
        lines.append("  evidence: none")
    lines.append(f"  check: {_claim_result(listing, claim_id, evidence)}")


def _section_copy(listing: dict[str, Any], lines: list[str]) -> None:
    copy = listing.get("copy")
    lines.append("## 5. Listing copy")
    lines.append("")
    if not copy:
        lines.append("No listing copy yet.")
        lines.append("")
        return
    generator = copy.get("generator") or {}
    lines.append(f"Generator: {generator.get('model') or 'none'} · {generator.get('note') or ''}".rstrip())
    _claim_block(listing, "title", "title", copy.get("title") or "",
                 (copy.get("evidence") or {}).get("title") or [], lines)
    lines.append("")
    lines.append("Description:")
    lines.append(copy.get("description") or "(empty)")
    lines.append("")
    lines.append("Sentences:")
    if not copy.get("sentences"):
        lines.append("  (none)")
    for claim in copy.get("sentences") or []:
        _claim_block(listing, "sentence", claim.get("id"), claim.get("text") or "",
                     claim.get("evidence") or [], lines)
    lines.append("Highlights:")
    if not copy.get("highlights"):
        lines.append("  (none)")
    for claim in copy.get("highlights") or []:
        _claim_block(listing, "highlight", claim.get("id"), claim.get("text") or "",
                     claim.get("evidence") or [], lines)
    lines.append("")


def _frame_line(listing: dict[str, Any], frame: dict[str, Any], lines: list[str]) -> None:
    when = clock(frame["t"]) if frame.get("t") is not None else f"Upload {frame.get('upload')}"
    wonder = frame.get("wonder")
    sam = frame.get("sam")
    blur = frame.get("blur")
    room = _frame_room(listing, frame.get("id"))
    belongs = f"{room['name']} ({room['id']})" if room else "unassigned"

    if wonder:
        head = (f"- {frame.get('id')} · {when} · {wonder.get('room_type')} ({wonder.get('room_key')}) "
                f"in {belongs} · coverage {_pct(wonder.get('coverage'))} · "
                f"{'usable' if wonder.get('usable') else 'not usable'}")
        if wonder.get("condition"):
            head += f" · condition: {wonder['condition']}"
    else:
        head = f"- {frame.get('id')} · {when} · not classified · in {belongs}"
    lines.append(head)
    lines.append(f"  media: {_media(frame.get('path'))}")
    if sam:
        lines.append(f"  sam: privacy boxes={len(sam.get('privacy') or [])} · "
                     f"structure boxes={len(sam.get('structure') or [])}")
    else:
        lines.append("  sam: not run")
    lines.append(f"  blur regions: {blur.get('regions') if blur else 'not recorded'}")
    observations = (wonder or {}).get("observations") or []
    if observations:
        lines.append("  observations:")
        for obs in observations:
            lines.append(f"    {obs.get('id')}: {obs.get('text')}")
    else:
        lines.append("  observations: none")


def _section_decisions(listing: dict[str, Any], lines: list[str]) -> None:
    frames = listing.get("frames") or []
    rooms = _rooms(listing)
    checklist = listing.get("checklist") or {}
    flags = ((listing.get("verification") or {}).get("flags")) or []

    lines.append("## 6. What the model saw and decided")
    lines.append("")
    lines.append(f"### Saw · {len(frames)} frames")
    if not frames:
        lines.append("No frames: this listing has no walkthrough footage.")
    for frame in frames:
        _frame_line(listing, frame, lines)
    lines.append("")

    lines.append("### Decided")
    lines.append("Rooms:")
    if not rooms:
        lines.append("- No rooms decided.")
    for room in rooms:
        staging = room.get("staging")
        staged = (f"staged {staging.get('style')} by {staging.get('model') or 'no model'}"
                  if staging else "not staged")
        lines.append(f"- {room.get('name')} ({room.get('id')}): hero {room.get('source_frame') or 'none'} · "
                     f"{room.get('hero_reason') or ''} · {staged}".rstrip())
        if staging and staging.get("prompt"):
            lines.append(f"  staging prompt: {staging['prompt']}")
    lines.append("Claims:")
    rows = _claim_rows(listing)
    if not rows:
        lines.append("- No claims.")
    for label, claim_id, text, evidence in rows:
        refs = ", ".join(str(e.get("ref")) for e in evidence) or "none"
        lines.append(f"- [{label}] \"{text}\" · evidence: {refs} · "
                     f"check: {_claim_result(listing, claim_id, evidence)}")
    lines.append("")

    lines.append("### Still open")
    open_items = [i for i in checklist.get("items") or [] if i.get("status") != "done"]
    if not open_items and not flags:
        lines.append("Nothing open. Every check passed.")
    for item in open_items:
        detail = f" — {item.get('detail')}" if item.get("detail") else ""
        lines.append(f"- checklist [{item.get('status')}] {item.get('label')}{detail}")
    for flag in flags:
        lines.append(f"- flag {flag.get('id')} · {_flag_target(flag, listing)}: {flag.get('message')}")
        lines.append(f"  resolution: {flag.get('resolution')}")
    lines.append("")


def _section_trace(listing: dict[str, Any], lines: list[str]) -> None:
    trace = listing.get("trace") or []
    independent = [t for t in trace if str(t.get("purpose", "")).startswith("verify.")]
    generator = [t for t in trace if not str(t.get("purpose", "")).startswith("verify.")]
    cached = sum(1 for t in trace if t.get("cached"))

    lines.append(f"## 7. Meta calls · {len(trace)} total · {len(independent)} independent · {cached} cached")
    lines.append("")

    def emit(title: str, rows: list[dict[str, Any]], start: int) -> int:
        lines.append(f"### {title} · {len(rows)}")
        if not rows:
            lines.append("  None recorded.")
        for i, entry in enumerate(rows, start=start):
            purpose = entry.get("purpose") or ""
            label = PURPOSE.get(purpose, purpose)
            target = _target_text(entry.get("target"), listing) or "-"
            outcome = "ok" if entry.get("ok") else f"error: {entry.get('error')}"
            lines.append(
                f"  {i}. {purpose} ({label}) · {entry.get('model')} · {target} · "
                f"{entry.get('ms')} ms · cached: {'yes' if entry.get('cached') else 'no'} · "
                f"{outcome} · {entry.get('summary')} · at {entry.get('at')} · {entry.get('id')}"
            )
        return start + len(rows)

    nxt = emit("Generator", generator, 1)
    lines.append("")
    emit("Independent checks", independent, nxt)
    lines.append("")


def _section_jobs(listing: dict[str, Any], jobs: list[dict[str, Any]], lines: list[str]) -> None:
    lines.append(f"## 8. Job history · {len(jobs)}")
    lines.append("")
    if not jobs:
        lines.append("No jobs recorded.")
    for job in jobs:
        current = " · CURRENT" if job.get("id") == listing.get("job_id") else ""
        lines.append(
            f"- {job.get('id')} · kind={job.get('kind')} · status={job.get('status')} · "
            f"stage={job.get('stage')} · progress={job.get('progress')} · "
            f"error={job.get('error') or '-'} · created={job.get('created_at')} · "
            f"updated={job.get('updated_at')}{current}"
        )
    lines.append("")


def render(listing: dict[str, Any], jobs: list[dict[str, Any]], *, meta: dict[str, Any],
           commit: str, exported_at: datetime) -> str:
    lid = listing.get("id")
    lines: list[str] = [
        f"LISTING LOGS EXPORT · {lid}",
        f"Exported at: {exported_at.isoformat(timespec='seconds')} UTC",
        f"App commit: {commit}",
        "This file contains no API keys, no raw frames and no raw uploads; images are "
        "referenced by blurred/staged media path only. It covers one listing only.",
        "",
    ]
    _section_listing(listing, meta, lines)
    _section_video(listing, lines)
    _section_checks(listing, lines)
    _section_flags(listing, lines)
    _section_rooms(listing, lines)
    _section_copy(listing, lines)
    _section_decisions(listing, lines)
    _section_trace(listing, lines)
    _section_live(listing, lines)
    _section_jobs(listing, jobs, lines)
    lines.append(f"-- end of export · {lid} --")
    return scrub("\n".join(lines) + "\n")
