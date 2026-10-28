"""Claim number check: digits inside a cited text fact (e.g. the address) count as supplied."""

from verify import checks

FACTS = {"address": "123 Main St", "city": "Chicago", "beds": 2, "baths": 2.0, "sqft": 2000}


def _fact(ref):
    return {"kind": "fact", "ref": ref, "value": FACTS[ref]}


def _check(text, refs):
    return checks._claim_code(text, [_fact(r) for r in refs], FACTS, {}, set())


def test_address_number_from_cited_address_passes():
    text = ("Located at 123 Main St in Chicago, this residence offers 2 bedrooms and 2 baths "
            "across 2000 square feet.")
    assert _check(text, ["address", "city", "beds", "baths", "sqft"]) == ("pass", "Evidence resolves.")


def test_wrong_address_number_still_fails():
    status, reason = _check("Located at 125 Main St in Chicago.", ["address", "city"])
    assert status == "fail" and "125" in reason


def test_address_number_without_citing_the_address_still_fails():
    status, reason = _check("Located at 123 Main St, with 2 bedrooms.", ["beds"])
    assert status == "fail" and "123" in reason


def test_numeric_facts_unchanged():
    assert _check("Offers 2 bedrooms across 2,000 square feet.", ["beds", "sqft"])[0] == "pass"
    assert _check("Offers 3 bedrooms.", ["beds"])[0] == "fail"
