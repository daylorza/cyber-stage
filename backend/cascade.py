"""Cascade prep for Live-In-It: plain image maths, no model calls.

Muse Image re-frames every generation a little (measured 0.6-3% shift, ~2% stretch). Laid
straight over the filmed frame, a staged image misaligns every wall, window and baseboard edge,
and a difference mask lights up along all of them: that is the halo around falling furniture.

So each generated image is first ALIGNED to the filmed frame (global stretch + shift, searched on
edge maps), and the furniture mask is the colour difference between the aligned staged image and
the aligned empty plate, with thin lines opened away, holes closed and the edge feathered.

An alignment maps the generated image into the filmed frame's normalized coordinates:
    frame = s * image + b        (per axis: sx, bx and sy, by)
so the viewer places the image at left = bx, top = by, width = sx, height = sy of the stage.
"""

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageStat

IDENTITY = {"sx": 1.0, "sy": 1.0, "bx": 0.0, "by": 0.0}
ALIGN_W = 128
MAX_SHIFT = 0.05
MASK_W = 360
MIN_GAIN = 0.03           # an alignment must beat identity by 3% to be used
BASELINE_PERCENTILE = 0.4
EDGE_LO, EDGE_HI = 14, 44
MAX_CHANGED = 0.8
MIN_CHANGED = 0.002


def _params(sx: float, sy: float, tx: float, ty: float) -> dict[str, float]:
    """Stretch about the centre, then shift the centre by (tx, ty)."""
    return {"sx": sx, "sy": sy, "bx": (1 - sx) / 2 + tx, "by": (1 - sy) / 2 + ty}


def warp(img: Image.Image, a: dict[str, float], size: tuple[int, int],
         resample: int = Image.Resampling.BILINEAR) -> Image.Image:
    """Render `img` in frame coordinates at `size` using alignment `a`."""
    w, h = size
    src = img if img.size == size else img.resize(size, resample)
    data = (1 / a["sx"], 0, -a["bx"] * w / a["sx"], 0, 1 / a["sy"], -a["by"] * h / a["sy"])
    return src.transform(size, Image.Transform.AFFINE, data, resample)


def _valid_box(a: dict[str, float], size: tuple[int, int], inset: int = 0) -> tuple[int, int, int, int]:
    w, h = size
    x1 = max(0, math.ceil(a["bx"] * w) + inset)
    y1 = max(0, math.ceil(a["by"] * h) + inset)
    x2 = min(w, math.floor((a["bx"] + a["sx"]) * w) - inset)
    y2 = min(h, math.floor((a["by"] + a["sy"]) * h) - inset)
    return x1, y1, max(x1 + 1, x2), max(y1 + 1, y2)


def _edges(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return (img.convert("L").resize(size, Image.Resampling.BILINEAR)
            .filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(1)))


def _score(ref: Image.Image, img: Image.Image, a: dict[str, float]) -> float:
    box = _valid_box(a, ref.size, inset=2)
    diff = ImageChops.difference(ref.crop(box), warp(img, a, ref.size).crop(box))
    return ImageStat.Stat(diff).mean[0]


def align(ref_path: Path, img_path: Path) -> dict[str, float]:
    """Global stretch + shift that lines `img_path` up with the filmed frame `ref_path`.
    Coarse shift search, then stretch around the best shift. Identity unless clearly better."""
    with Image.open(ref_path) as r, Image.open(img_path) as i:
        size = (ALIGN_W, max(8, round(ALIGN_W * r.height / r.width)))
        ref, img = _edges(r, size), _edges(i, size)
    w, h = size
    base = _score(ref, img, IDENTITY)
    best = (base, 1.0, 1.0, 0, 0)
    rx, ry = math.ceil(MAX_SHIFT * w), math.ceil(MAX_SHIFT * h)
    for dy in range(-ry, ry + 1):
        for dx in range(-rx, rx + 1):
            score = _score(ref, img, _params(1.0, 1.0, dx / w, dy / h))
            if score < best[0]:
                best = (score, 1.0, 1.0, dx, dy)
    _, _, _, bdx, bdy = best
    for sy in (0.96, 0.97, 0.98, 0.99, 1.0, 1.01, 1.02, 1.03, 1.04):
        for sx in (0.98, 0.99, 1.0, 1.01, 1.02):
            for dy in range(bdy - 2, bdy + 3):
                for dx in range(bdx - 1, bdx + 2):
                    score = _score(ref, img, _params(sx, sy, dx / w, dy / h))
                    if score < best[0]:
                        best = (score, sx, sy, dx, dy)
    score, sx, sy, dx, dy = best
    if score > base * (1 - MIN_GAIN):
        return {**IDENTITY, "score": round(base, 3), "identity_score": round(base, 3)}
    a = _params(sx, sy, dx / w, dy / h)
    return {k: round(v, 4) for k, v in a.items()} | {"score": round(score, 3), "identity_score": round(base, 3)}


def _smooth(lo: float, hi: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return t * t * (3 - 2 * t)


def furniture_mask(ref_path: Path, plate_path: Path, plate_align: dict[str, float],
                   staged_path: Path, staged_align: dict[str, float], out_path: Path) -> dict[str, Any]:
    """Soft alpha mask (frame coordinates) of what the staged image adds over the empty plate.
    Saved as an LA PNG (alpha = mask) usable as a CSS mask. None when it would not be useful."""
    with Image.open(ref_path) as r:
        rw, rh = r.size
    w = min(MASK_W, rw)
    size = (w, max(8, round(w * rh / rw)))
    with Image.open(plate_path) as p, Image.open(staged_path) as st:
        plate = warp(p.convert("RGB"), plate_align, size).filter(ImageFilter.GaussianBlur(1.2))
        staged = warp(st.convert("RGB"), staged_align, size).filter(ImageFilter.GaussianBlur(1.2))
    r_, g_, b_ = ImageChops.difference(plate, staged).split()
    diff = ImageChops.lighter(ImageChops.lighter(r_, g_), b_)

    valid = Image.new("L", size, 0)
    va, vb = _valid_box(staged_align, size, 3), _valid_box(plate_align, size, 3)
    box = (max(va[0], vb[0]), max(va[1], vb[1]), min(va[2], vb[2]), min(va[3], vb[3]))
    valid.paste(255, box)

    hist = diff.crop(box).histogram()
    total, seen, baseline = sum(hist), 0, 0
    for value, count in enumerate(hist):
        seen += count
        if seen >= total * BASELINE_PERCENTILE:
            baseline = value
            break
    lut = [round(255 * _smooth(baseline + EDGE_LO, baseline + EDGE_HI, v)) for v in range(256)]
    mask = ImageChops.multiply(diff.point(lut), valid)
    # Open: thin leftover edge lines and speckle disappear. Close: holes inside furniture fill.
    mask = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
    mask = mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(2.5))

    hist = mask.histogram()
    changed = sum(hist[128:]) / max(1, sum(hist))
    if not MIN_CHANGED <= changed <= MAX_CHANGED:
        return {"usable": False, "changed": round(changed, 3), "baseline": baseline}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.merge("LA", (Image.new("L", size, 255), mask)).save(out_path, optimize=True)
    return {"usable": True, "changed": round(changed, 3), "baseline": baseline, "size": list(size)}


def to_frame(box: list[float], a: dict[str, float]) -> list[float]:
    """A normalized box on the generated image, in filmed-frame coordinates."""
    return [round(a["sx"] * box[0] + a["bx"], 4), round(a["sy"] * box[1] + a["by"], 4),
            round(a["sx"] * box[2] + a["bx"], 4), round(a["sy"] * box[3] + a["by"], 4)]
