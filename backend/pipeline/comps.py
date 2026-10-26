from typing import Any

import comps_adapter


def attach(listing: dict[str, Any]) -> dict[str, Any]:
    listing["comps"] = comps_adapter.get_adapter().comps_for(listing["facts"])
    return listing
