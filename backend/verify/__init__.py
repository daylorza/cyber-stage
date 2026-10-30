"""Independent verification of the generator's output.

This package lives outside pipeline/: it never calls a generator function and
never reuses the model call that produced the work. It re-reads the listing and
the files on disk and makes its OWN Meta calls for meta checks. With meta=False
(broker re-reviews) previous meta verdicts are reused by check id, costing no calls.
"""

from datetime import UTC, datetime
from typing import Any, Callable

import checklist
import meta_client
from verify import checks as _checkers


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


DEFAULT_RESOLUTION = "Resolve in the broker console; the listing cannot publish while this is open."
WARNING_RESOLUTION = "Warning only (demo mode): review it in the broker console; it does not block publishing."


class _Ctx:
    def __init__(self, listing: dict[str, Any], use_meta: bool):
        self.default_resolution = (
            DEFAULT_RESOLUTION if checklist.checks_block(listing) else WARNING_RESOLUTION)
        self.use_meta = use_meta
        self.client = meta_client.get_client() if use_meta else None
        self.trace = listing.setdefault("trace", [])
        self.checks: list[dict[str, Any]] = []
        self.flags: list[dict[str, Any]] = []
        self.prev_meta = {
            c["id"]: c for c in (listing.get("verification") or {}).get("checks", [])
            if c.get("kind") == "meta"
        }

    def _flag(self, item: str, target: dict | None, message: str, resolution: str | None) -> None:
        self.flags.append({
            "id": f"flag_{len(self.flags) + 1}",
            "item": item,
            "target": target or {},
            "message": message,
            "resolution": resolution or self.default_resolution,
        })

    def code(self, item: str, check_id: str, status: str, reason: str,
             target: dict | None = None, resolution: str | None = None) -> None:
        self.checks.append({
            "id": check_id, "item": item, "kind": "code", "target": target or {},
            "status": status, "reason": reason, "model": None,
        })
        if status != "pass":
            self._flag(item, target, reason, resolution)

    def meta(self, item: str, check_id: str, target: dict | None,
             fn: Callable[[], tuple[str, str]], model: str | None = None,
             resolution: str | None = None) -> None:
        if not self.use_meta:
            prev = self.prev_meta.get(check_id)
            if prev is None:
                self.checks.append({
                    "id": check_id, "item": item, "kind": "meta", "target": target or {},
                    "status": "unclear", "reason": "Not yet checked", "model": None,
                })
                self._flag(item, target, "Independent model check has not run yet.", resolution)
            else:
                self.checks.append(dict(prev))
                if prev["status"] != "pass":
                    self._flag(item, target, prev["reason"], resolution)
            return
        try:
            status, reason = fn()
        except meta_client.MetaError as exc:
            status, reason = "unclear", str(exc)
        except Exception as exc:
            status, reason = "unclear", f"Check errored: {exc.__class__.__name__}"
        self.checks.append({
            "id": check_id, "item": item, "kind": "meta", "target": target or {},
            "status": status, "reason": reason, "model": model,
        })
        if status != "pass":
            self._flag(item, target, reason, resolution)


def _item_flag(ctx: _Ctx, item: dict[str, Any]) -> None:
    ctx.flags.append({
        "id": f"flag_{len(ctx.flags) + 1}",
        "item": item["id"],
        "target": {},
        "message": f"{item['label']}: {item.get('detail') or 'did not run'}",
        "resolution": "Resolve the pipeline stage output, then re-save the review.",
    })


def _passed_detail(related: list[dict[str, Any]]) -> str:
    if len(related) == 1:
        return related[0]["reason"]
    independent = sum(c["kind"] == "meta" for c in related)
    return f"{len(related)} checks passed" + (f", {independent} by independent model calls" if independent else "")


def run(listing: dict[str, Any], *, meta: bool = True) -> dict[str, Any]:
    ctx = _Ctx(listing, meta)
    checkers = [
        ("frames", _checkers.check_frames),
        ("sam_masks", _checkers.check_sam),
        ("wonder_classification", _checkers.check_wonder),
        ("claim_evidence", _checkers.check_claims),
        ("staging_geometry", _checkers.check_staging),
        ("comps_demo", _checkers.check_comps),
        ("blur_pass", _checkers.check_blur),
    ]
    for item_id, fn in checkers:
        try:
            fn(ctx, listing)
        except Exception as exc:
            ctx.code(item_id, item_id, "fail", f"Check errored: {exc.__class__.__name__}")

    for item in (listing.get("checklist") or {}).get("items", []):
        item_id = item["id"]
        related = [c for c in ctx.checks if c["item"] == item_id]
        all_pass = bool(related) and all(c["status"] == "pass" for c in related)
        if item["status"] in ("generated", "done", "flagged"):
            if all_pass:
                checklist.set_item(listing, item_id, "done", _passed_detail(related))
            else:
                worst = next(
                    (c for c in related if c["status"] == "fail"),
                    next((c for c in related if c["status"] == "unclear"), None),
                )
                checklist.set_item(listing, item_id, "flagged",
                                   worst["reason"] if worst else "No checks ran.")
        elif item["status"] == "failed":
            if all_pass:
                checklist.set_item(listing, item_id, "done",
                                   f"{_passed_detail(related)} (generator: {item['detail']})")
            else:
                _item_flag(ctx, item)
        else:
            _item_flag(ctx, item)

    listing["verification"] = {
        "ran_at": _now(),
        "passed": all(c["status"] == "pass" for c in ctx.checks) and checklist.is_clear(listing),
        "checks": ctx.checks,
        "flags": ctx.flags,
    }
    return listing
