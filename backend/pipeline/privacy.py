"""Privacy pass: blurred, publishable copies of frames under media/frames/<lid>/.

Every SAM privacy box (face, photograph, document) is Gaussian-blurred with ~10%
padding, strong enough that faces are unreadable. A frame SAM never reached is
held back entirely: no path, nothing under media_dir.
"""

from typing import Any

from PIL import Image, ImageFilter

import checklist
import config

PAD_RATIO = 0.10


def blur_regions(img: Image.Image, boxes: list[dict[str, Any]]) -> Image.Image:
    for entry in boxes:
        x1, y1, x2, y2 = entry["box"]
        pad_x, pad_y = int((x2 - x1) * PAD_RATIO), int((y2 - y1) * PAD_RATIO)
        box = (
            max(0, x1 - pad_x), max(0, y1 - pad_y),
            min(img.width, x2 + pad_x), min(img.height, y2 + pad_y),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        radius = max(12, int(0.15 * max(x2 - x1, y2 - y1)))
        img.paste(img.crop(box).filter(ImageFilter.GaussianBlur(radius)), box)
    return img


def run(listing: dict[str, Any]) -> dict[str, Any]:
    s = config.settings
    lid = listing["id"]
    out_dir = s.media_dir / "frames" / lid
    out_dir.mkdir(parents=True, exist_ok=True)
    held: list[str] = []
    for frame in listing["frames"]:
        sam = frame.get("sam")
        if sam is None:
            frame["path"] = None
            frame["blur"] = None
            held.append(frame["id"])
            continue
        img = Image.open(s.raw_frames_dir / lid / frame["raw"]).convert("RGB")
        boxes = sam.get("privacy", [])
        blur_regions(img, boxes)
        dest = out_dir / f"{frame['id']}.jpg"
        img.save(dest, "JPEG", quality=90)
        frame["path"] = f"frames/{lid}/{frame['id']}.jpg"
        frame["blur"] = {"regions": len(boxes)}

    if held:
        checklist.set_item(
            listing, "blur_pass", "failed",
            f"Frames held back: SAM did not run ({', '.join(held)}).",
        )
    else:
        checklist.set_item(listing, "blur_pass", "generated", f"{len(listing['frames'])} frames blurred")
    return listing
