"""Comparable sales behind one adapter interface.

This build ships SEEDED DEMO COMPS ONLY. A live Miami Matrix (MLS) feed can implement the same
interface later, behind broker authorization; it is not part of the hackathon build.
"""

import json
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import config

DEMO_LABEL = "Demo comps: seeded sample data, not a live MLS feed"


def city_key(city: str | None) -> str:
    return (city or "").strip().lower().replace(" ", "-")


class CompsAdapter(Protocol):
    source: str

    def comps_for(self, facts: dict[str, Any]) -> dict[str, Any]: ...


class SeededDemoComps:
    source = "demo"

    def __init__(self, path: Path):
        self._data = json.loads(path.read_text())

    def comps_for(self, facts: dict[str, Any]) -> dict[str, Any]:
        items = self._data.get(city_key(facts.get("city")), [])
        return {
            "source": self.source,
            "label": DEMO_LABEL,
            "items": items,
            "suggested_range": suggested_range(items, facts.get("sqft")),
        }


class MatrixComps:
    """Miami Matrix MLS feed. Requires broker authorization; intentionally not implemented here."""

    source = "matrix"

    def comps_for(self, facts: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("The Matrix feed requires broker authorization and is out of hackathon scope.")


def suggested_range(items: list[dict[str, Any]], sqft: int | None) -> dict[str, Any] | None:
    per_sqft = [c["price"] / c["sqft"] for c in items if c.get("price") and c.get("sqft")]
    if not sqft or len(per_sqft) < 2:
        return None
    q1, median, q3 = statistics.quantiles(per_sqft, n=4, method="inclusive")
    return {
        "low": round(q1 * sqft, -4),
        "high": round(q3 * sqft, -4),
        "median_per_sqft": round(median),
        "currency": items[0].get("currency", "USD"),
        "basis": f"Interquartile price per sq ft of {len(per_sqft)} demo comps x {sqft:,} sq ft",
    }


@lru_cache(maxsize=1)
def _seeded(path: Path) -> SeededDemoComps:
    return SeededDemoComps(path)


def get_adapter() -> CompsAdapter:
    return _seeded(config.settings.seed_dir / "comps.json")
