"""Listing copy. Every claim carries its evidence; nothing is stated that was not seen or supplied.

Stage 0 writes only from supplied facts. Stage 1: Spark drafts from facts + Wonder's visual evidence,
and any claim without evidence is dropped before the broker sees it.
"""

from typing import Any

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


def write(listing: dict[str, Any]) -> dict[str, Any]:
    f = listing["facts"]
    highlights = []
    if f.get("beds"):
        highlights.append({"text": _plural(f["beds"], "bedroom"), "evidence": [fact("beds", f["beds"])]})
    if f.get("baths"):
        highlights.append({"text": _plural(f["baths"], "bathroom"), "evidence": [fact("baths", f["baths"])]})
    if f.get("sqft"):
        highlights.append({"text": f"{f['sqft']:,} sq ft", "evidence": [fact("sqft", f["sqft"])]})

    if f.get("beds") and f.get("city"):
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
        "highlights": highlights,
        "evidence": {"title": evidence, "description": []},
    }
    return listing
