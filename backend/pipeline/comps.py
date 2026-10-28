from typing import Any

import checklist
import comps_adapter


def attach(listing: dict[str, Any]) -> dict[str, Any]:
    listing["comps"] = comps_adapter.get_adapter().comps_for(listing["facts"])
    checklist.set_item(listing, "comps_demo", "generated", listing["comps"]["label"])
    return listing
