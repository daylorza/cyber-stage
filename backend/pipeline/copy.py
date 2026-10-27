"""Listing copy. Every claim carries its evidence; nothing is stated that was not seen or supplied.

Spark drafts from supplied facts + Wonder's visual observations, citing ids. Ids are
mapped to Evidence objects here; a claim that cites a non-existent id keeps an
"unknown" evidence marker so the independent verifier can flag it — claims are
never silently dropped. Fallback when Spark is unavailable: facts-only writer.
"""

from typing import Any

import checklist
import meta_client

CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}


def _num(value: float) -> str:
    return f"{value:,.1f}".rstrip("0").rstrip(".")


def _plural(n: float, word: str) -> str:
    return f"{_num(n)} {word}{'' if n == 1 else 's'}"


def fact(ref: str, value: Any) -> dict[str, Any]:
    return {"kind": "fact", "ref": ref, "value": value}


def format_price(amount: int | None, currency: str | None) -> str | None:
    if not amount:
        return None
    return f"{CURRENCY_SYMBOLS.get(currency or 'USD', '')}{amount:,}"


def _observations(listing: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {f["id"]: f for f in listing["frames"]}
    out: list[dict[str, Any]] = []
    for room in listing.get("rooms", []):
        if room.get("rejected"):
            continue
        for frame_id in room.get("frames", []):
            frame = by_id.get(frame_id)
            if not frame or not frame.get("wonder"):
                continue
            for obs in frame["wonder"]["observations"]:
                out.append({
                    "id": obs["id"], "text": obs["text"], "frame": frame_id,
                    "room_id": room["id"], "t": frame.get("t"),
                })
    return out


def _evidence(ref: Any, facts: dict[str, Any], obs_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ref = str(ref)
    if ref.startswith("fact:"):
        key = ref[5:]
        if key in facts:
            return {"kind": "fact", "ref": key, "value": facts[key]}
        return {"kind": "unknown", "ref": ref}
    obs = obs_by_id.get(ref)
    if obs:
        return {
            "kind": "visual", "ref": ref, "frame": obs["frame"], "room_id": obs["room_id"],
            "text": obs["text"], "t": obs["t"],
        }
    return {"kind": "unknown", "ref": ref}


def write_facts(listing: dict[str, Any], note: str = "Facts only: Spark unavailable") -> dict[str, Any]:
    f = listing["facts"]
    highlights = []
    if f.get("beds"):
        highlights.append({"text": _plural(f["beds"], "bedroom"), "evidence": [fact("beds", f["beds"])]})
    if f.get("baths"):
        highlights.append({"text": _plural(f["baths"], "bathroom"), "evidence": [fact("baths", f["baths"])]})
    if f.get("sqft"):
        highlights.append({"text": f"{f['sqft']:,} sq ft", "evidence": [fact("sqft", f["sqft"])]})
    for i, h in enumerate(highlights, start=1):
        h["id"] = f"c{i}"

    if f.get("name"):
        title, evidence = f["name"], [fact("name", f["name"])]
    elif f.get("beds") and f.get("city"):
        title = f"{_num(f['beds'])}-bedroom residence in {f['city']}"
        evidence = [fact("beds", f["beds"]), fact("city", f["city"])]
    elif f.get("city"):
        title, evidence = f"Residence in {f['city']}", [fact("city", f["city"])]
    elif f.get("address"):
        title, evidence = f["address"], [fact("address", f["address"])]
    else:
        title, evidence = "", []

    listing["copy"] = {
        "title": title,
        "description": "",
        "sentences": [],
        "highlights": highlights,
        "evidence": {"title": evidence, "description": []},
        "generator": {"model": None, "note": note},
    }
    checklist.set_item(listing, "claim_evidence", "generated", f"{len(highlights) + 1} claims, facts only")
    return listing


def write(listing: dict[str, Any]) -> dict[str, Any]:
    meta = meta_client.get_client()
    facts = listing["facts"]
    observations = _observations(listing)
    try:
        result = meta.spark_copy(
            facts=facts, observations=observations,
            trace=listing.setdefault("trace", []), purpose="spark.copy", target={},
        )
    except meta_client.MetaError as exc:
        return write_facts(listing, note=f"Facts only: {exc}")

    obs_by_id = {o["id"]: o for o in observations}

    def claim(block: dict[str, Any], cid: int) -> dict[str, Any]:
        return {
            "id": f"c{cid}",
            "text": str(block.get("text") or ""),
            "evidence": [_evidence(r, facts, obs_by_id) for r in block.get("evidence") or []],
        }

    cid = 0
    sentences, highlights = [], []
    for block in result.get("sentences") or []:
        cid += 1
        sentences.append(claim(block, cid))
    for block in result.get("highlights") or []:
        cid += 1
        highlights.append(claim(block, cid))

    title_block = result.get("title") or {}
    title_evidence = [_evidence(r, facts, obs_by_id) for r in title_block.get("evidence") or []]
    description_evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for sentence in sentences:
        for ev in sentence["evidence"]:
            key = (ev["kind"], ev["ref"])
            if key not in seen:
                seen.add(key)
                description_evidence.append(ev)

    listing["copy"] = {
        "title": str(title_block.get("text") or ""),
        "description": " ".join(s["text"] for s in sentences),
        "sentences": sentences,
        "highlights": highlights,
        "evidence": {"title": title_evidence, "description": description_evidence},
        "generator": {
            "model": getattr(meta, "spark_model", None),
            "note": "Spark drafted; every claim cites supplied facts or Wonder observations.",
        },
    }
    checklist.set_item(
        listing, "claim_evidence", "generated",
        f"{cid + 1} claims, all evidence-carrying",
    )
    return listing
