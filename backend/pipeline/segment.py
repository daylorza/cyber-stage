"""SAM 3.1 masks per raw frame.

Privacy concepts (face, photograph, document) drive the blur pass; structure
concepts (window, door) let the verifier check staging geometry. Calls are
threaded; any Meta error marks the item failed and the job continues.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import checklist
import config
import meta_client

PRIVACY_CONCEPTS = ("face", "photograph", "document")
STRUCTURE_CONCEPTS = ("window", "door")
WORKERS = 4


def run(listing: dict[str, Any]) -> dict[str, Any]:
    s = config.settings
    lid = listing["id"]
    meta = meta_client.get_client()
    trace = listing.setdefault("trace", [])
    # Keyed per concept: a frame is masked only when EVERY concept call succeeded.
    results: dict[str, dict[str, list]] = {}
    failed_frames: set[str] = set()
    errors: list[str] = []

    def work(frame: dict[str, Any], concept: str, group: str) -> list[dict[str, Any]]:
        path = s.raw_frames_dir / lid / frame["raw"]
        return meta.sam_segment(
            path, concept, trace=trace, purpose=f"sam.{group}",
            target={"frame": frame["id"], "concept": concept},
        )

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {}
        for frame in listing["frames"]:
            for concept in PRIVACY_CONCEPTS:
                futures[pool.submit(work, frame, concept, "privacy")] = (frame["id"], concept)
            for concept in STRUCTURE_CONCEPTS:
                futures[pool.submit(work, frame, concept, "structure")] = (frame["id"], concept)
        for future in as_completed(futures):
            frame_id, concept = futures[future]
            try:
                boxes = future.result()
            except meta_client.MetaError as exc:
                failed_frames.add(frame_id)
                errors.append(str(exc))
            else:
                results.setdefault(frame_id, {})[concept] = boxes

    all_concepts = set(PRIVACY_CONCEPTS) | set(STRUCTURE_CONCEPTS)
    for frame in listing["frames"]:
        per_concept = results.get(frame["id"])
        if frame["id"] in failed_frames or not per_concept or not all_concepts.issubset(per_concept):
            frame["sam"] = None
            continue
        frame["sam"] = {
            "privacy": [b for c in PRIVACY_CONCEPTS for b in per_concept[c]],
            "structure": [b for c in STRUCTURE_CONCEPTS for b in per_concept[c]],
        }

    total = sum(len(boxes) for per in results.values() for boxes in per.values())
    if errors:
        checklist.set_item(listing, "sam_masks", "failed", f"{errors[0]} ({len(errors)} call(s) failed)")
    else:
        checklist.set_item(listing, "sam_masks", "generated", f"{total} boxes across {len(results)} frames")
    return listing
