"""Cut one staged image into cascade pieces. Plain image maths (numpy + Pillow), no model calls.

Inputs: the staged image (Meta Image), the empty hero frame grabbed from the clip, and one
SAM 3.1 mask per piece (SAM returns a soft, lossless coverage mask with every box). Every
output is in hero-frame coordinates:

  body    RGBA crop of the piece as staged, colour-matched to the filmed light, alpha = SAM's
          own coverage (soft edges, no halo). What a piece in front of it hides is filled in
          from the piece itself, and the rug is filled in under the furniture, so nothing is
          missing while a piece falls.
  shadow  RGBA crop (black + alpha): the darkening the staging adds on the floor or rug next
          to the piece. Over the video, frame * (1 - alpha) is the staged shadow.
  base    floor-contact points: the lowest body pixel per column, overhangs dropped.

Landed, rug + shadows + bodies reproduce the staged furniture over the filmed frame.
"""

import math
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

WORK = (1024, 576)   # analysis resolution (what SAM saw)
OUT = (2048, 1152)   # texture resolution (Meta Image's own output size)
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _box1d(a: np.ndarray, r: int, axis: int) -> np.ndarray:
    if r <= 0:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, n + 2 * r + 1), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian-ish: three box passes per axis."""
    r = max(1, round((math.sqrt(4 * sigma * sigma + 1) - 1) / 2))
    a = a.astype(np.float32)
    for _ in range(3):
        a = _box1d(_box1d(a, r, 0), r, 1)
    return a


def dilate(m: np.ndarray, r: int) -> np.ndarray:
    return _box1d(_box1d(m.astype(np.float32), r, 0), r, 1) > 1e-4


def erode(m: np.ndarray, r: int) -> np.ndarray:
    return _box1d(_box1d(m.astype(np.float32), r, 0), r, 1) > 1 - 1e-4


def grey_dilate(a: np.ndarray, r: int) -> np.ndarray:
    """Max filter over a (2r+1) square."""
    out = a.copy()
    for axis in (0, 1):
        src = out.copy()
        for d in range(1, r + 1):
            out = np.maximum(out, np.roll(src, d, axis=axis))
            out = np.maximum(out, np.roll(src, -d, axis=axis))
    return out


def smoothstep(lo: float, hi: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def _load(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(img.convert("RGB").resize(size, Image.Resampling.LANCZOS), dtype=np.float32)


def _gray(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(img.convert("L").resize(size, Image.Resampling.BILINEAR), dtype=np.float32) / 255


def rect(box: list[float], size: tuple[int, int], gx: float = 0.0, gy: float = 0.0,
         gy_down: float | None = None) -> np.ndarray:
    """Boolean mask of a normalized box, grown by gx / gy (fractions of the image)."""
    w, h = size
    x1 = max(0, int(math.floor((box[0] - gx) * w)))
    x2 = min(w, int(math.ceil((box[2] + gx) * w)))
    y1 = max(0, int(math.floor((box[1] - gy) * h)))
    y2 = min(h, int(math.ceil((box[3] + (gy if gy_down is None else gy_down)) * h)))
    m = np.zeros((h, w), dtype=bool)
    m[y1:y2, x1:x2] = True
    return m


def components(m: np.ndarray) -> list[np.ndarray]:
    """4-connected components, largest first, as boolean masks."""
    h, w = m.shape
    flat = m.ravel()
    seen = np.zeros(flat.size, dtype=bool)
    out = []
    for start in np.flatnonzero(flat).tolist():
        if seen[start]:
            continue
        seen[start] = True
        queue, members = deque([start]), [start]
        while queue:
            p = queue.popleft()
            x = p % w
            for q in (p - w, p + w, p - 1 if x > 0 else -1, p + 1 if x < w - 1 else -1):
                if 0 <= q < flat.size and flat[q] and not seen[q]:
                    seen[q] = True
                    queue.append(q)
                    members.append(q)
        comp = np.zeros(flat.size, dtype=bool)
        comp[members] = True
        out.append(comp.reshape(h, w))
    return sorted(out, key=lambda c: -int(c.sum()))


def hull(m: np.ndarray) -> np.ndarray:
    """Filled convex hull of a mask (monotone chain on each row's extreme pixels)."""
    h, w = m.shape
    pts = []
    for y in np.nonzero(m.any(axis=1))[0]:
        xs = np.nonzero(m[y])[0]
        pts += [(int(xs[0]), int(y)), (int(xs[-1]), int(y))]
    pts = sorted(set(pts))
    if len(pts) < 3:
        return m.copy()

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).polygon(lower[:-1] + upper[:-1], fill=255, outline=255)
    return np.asarray(img) > 0


def color_match(staged: np.ndarray, plate: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """Per-channel gain + offset (a white balance) staged -> plate, fitted on unchanged room
    pixels with trimmed refits. Meta Image regrades the whole frame (here: warmer light);
    undoing that grade puts the pieces in the light the clip was filmed in. Per channel, not
    a full 3x3 mix, so the pieces keep their own hues (the cyan cushion stays cyan)."""
    xs, ys = staged[keep], plate[keep]
    step = max(1, len(xs) // 200_000)
    xs, ys = xs[::step], ys[::step]
    out = np.zeros((2, 3), dtype=np.float32)
    for c in range(3):
        x, y = xs[:, c], ys[:, c]
        sel = np.ones(len(x), dtype=bool)
        for _ in range(4):
            gain, offset = np.polyfit(x[sel], y[sel], 1)
            res = np.abs(gain * x + offset - y)
            sel = res < np.quantile(res, 0.65)
        out[:, c] = gain, offset
    # Half-way to one shared gain: full per-channel balance pushed the ivory and the jute
    # toward lemon; this keeps the staging's palette while the brightness matches the room.
    return (out + out.mean(axis=1, keepdims=True)) / 2


def apply_color(img: np.ndarray, m: np.ndarray) -> np.ndarray:
    return np.clip(img * m[0] + m[1], 0, 255)


def transplant(img: np.ndarray, valid: np.ndarray, hole: np.ndarray, max_dx: int,
               band: int = 0) -> tuple[np.ndarray, list[int]]:
    """Fill `hole` with pixels from `valid` in the SAME rows, one horizontal offset per hole
    region (per `band` rows of it, when set). With a level camera every image row is one depth
    on the floor, so a sideways copy keeps the rug's weave at the right scale. Leftovers take
    the nearest valid pixel."""
    out = img.copy()
    h, w = hole.shape
    shifts = []
    rows_with = np.nonzero(valid.any(axis=1))[0]
    if not len(rows_with):
        return out, shifts
    regions = components(hole)
    if band:
        strips = []
        for comp in regions:
            ys = np.nonzero(comp.any(axis=1))[0]
            for y0 in range(ys[0], ys[-1] + 1, band):
                strip = np.zeros_like(comp)
                strip[y0:y0 + band] = comp[y0:y0 + band]
                if strip.any():
                    strips.append(strip)
        regions = strips
    for comp in regions:
        ys, xs = np.nonzero(comp)
        best, best_frac = 0, -1.0
        for dx in sorted(range(-max_dx, max_dx + 1, 2), key=abs):
            if dx == 0:
                continue
            sx = xs + dx
            inside = (sx >= 0) & (sx < w)
            frac = float(valid[ys[inside], sx[inside]].sum()) / len(xs)
            if frac > best_frac:
                best, best_frac = dx, frac
            if frac >= 0.985:
                break
        sx = xs + best
        good = (sx >= 0) & (sx < w)
        good[good] = valid[ys[good], sx[good]]
        out[ys[good], xs[good]] = img[ys[good], sx[good]]
        shifts.append(best)
        for y in np.unique(ys[~good]):
            # Nearest row that has valid pixels (this row, when it has any), nearest x in it.
            src = rows_with[np.abs(rows_with - y).argmin()]
            vx = np.nonzero(valid[src])[0]
            row = xs[(ys == y) & ~good]
            i = np.clip(np.searchsorted(vx, row), 1, max(1, len(vx) - 1))
            left, right = vx[i - 1], vx[np.minimum(i, len(vx) - 1)]
            near = np.where(np.abs(row - left) <= np.abs(right - row), left, right)
            out[y, row] = img[src, near]
    return out, shifts


def floor_transplant(img: np.ndarray, valid: np.ndarray, hole: np.ndarray,
                     camera: dict[str, float]) -> tuple[np.ndarray, list[list[float]]]:
    """Fill a hole in something lying on the floor (the rug under the furniture) by sliding it
    ON THE FLOOR: each hole pixel is unprojected with the calibrated camera, moved by one
    (dX, dZ) metres per hole region, and sampled from clean weave there. A rigid move on the
    floor keeps the weave coherent and at the right scale for its depth."""
    out = img.copy()
    h, w = hole.shape
    fx, fy, vh = camera["fx"], camera["fy"], camera["horizon_y"]
    moves = sorted(((dx, dz) for dx in np.arange(-1.6, 1.61, 0.1) for dz in np.arange(-2.4, 1.21, 0.1)),
                   key=lambda m: m[0] ** 2 + m[1] ** 2)
    used: dict[tuple[float, float], int] = {}
    total = int(hole.sum())
    # Tile by tile (small tiles keep each move local), the nearest move whose source is clean
    # weave wins; pixels it cannot serve try the next move. Every pixel ends on clean weave.
    for ty in range(0, h, 32):
        for tx in range(0, w, 64):
            ys, xs = np.nonzero(hole[ty:ty + 32, tx:tx + 64])
            if not len(ys):
                continue
            ys, xs = ys + ty, xs + tx
            z = fy / np.maximum((ys + 0.5) / h - vh, 1e-3)   # depth, in camera heights
            x = ((xs + 0.5) / w - 0.5) * z / fx
            todo = np.ones(len(ys), dtype=bool)
            for dx, dz in moves:
                zs = z[todo] + dz
                fxs = (0.5 + fx * (x[todo] + dx) / np.maximum(zs, 0.3)) * w - 0.5
                fys = (vh + fy / np.maximum(zs, 0.3)) * h - 0.5
                ok = (zs > 0.3) & (fxs >= 0) & (fxs < w - 1.001) & (fys >= 0) & (fys < h - 1.001)
                x0, y0 = fxs.astype(int), fys.astype(int)
                ok[ok] = valid[y0[ok], x0[ok]] & valid[y0[ok] + 1, x0[ok] + 1]
                if not ok.any():
                    continue
                idx = np.nonzero(todo)[0][ok]
                x0, y0 = x0[ok], y0[ok]
                ax, ay = (fxs[ok] - x0)[:, None], (fys[ok] - y0)[:, None]
                out[ys[idx], xs[idx]] = ((img[y0, x0] * (1 - ax) + img[y0, x0 + 1] * ax) * (1 - ay)
                                         + (img[y0 + 1, x0] * (1 - ax) + img[y0 + 1, x0 + 1] * ax) * ay)
                todo[idx] = False
                key = (round(float(dx), 1), round(float(dz), 1))
                used[key] = used.get(key, 0) + len(idx)
                if not todo.any():
                    break
    top = sorted(used.items(), key=lambda kv: -kv[1])[:4]
    return out, [[dx, dz, round(n / max(1, total), 3)] for (dx, dz), n in top]


def base_points(mask: np.ndarray, samples: int = 28) -> list[list[float]]:
    """Floor contact: lowest pixel per column, then drop columns that sit clearly above the
    fitted base line (a table top's overhang, a sofa arm) and refit."""
    h, w = mask.shape
    cols = np.nonzero(mask.any(axis=0))[0]
    if len(cols) < 4:
        return []
    bottoms = np.array([np.nonzero(mask[:, x])[0][-1] for x in cols], dtype=np.float32)
    keep = np.ones(len(cols), dtype=bool)
    tol = 0.012 * h
    for _ in range(4):
        b, a = np.polyfit(cols[keep], bottoms[keep], 1)
        keep = bottoms >= (a + b * cols) - tol
    idx = np.nonzero(keep)[0]
    pick = idx[np.linspace(0, len(idx) - 1, min(samples, len(idx))).round().astype(int)]
    return [[round(float(cols[i]) / w, 4), round(float(bottoms[i] + 1) / h, 4)] for i in pick]


def rug_shading(lum: np.ndarray, rug: np.ndarray) -> np.ndarray:
    """Rug shading factor (1 = unshaded): the rug's low-passed luma over the 80th percentile of
    the rug's luma in the same rows. Rows are depths on the floor, so this is fair."""
    wsum = blur(rug.astype(np.float32), 5)
    lb = np.where(wsum > 0.05, blur(lum * rug, 5) / np.maximum(wsum, 1e-3), 0)
    out = np.ones_like(lum)
    for y in np.nonzero(rug.any(axis=1))[0]:
        band = rug[max(0, y - 8):y + 9]
        vals = lb[max(0, y - 8):y + 9][band]
        if len(vals):
            out[y] = np.where(rug[y], np.clip(lb[y] / max(1.0, float(np.quantile(vals, 0.8))), 0.3, 1.0), 1.0)
    return out


def _save_rgba(rgb: np.ndarray, alpha: np.ndarray, path: Path) -> list[float]:
    """Crop to the alpha's extent (+4 px), save, return the crop's normalized rect."""
    h, w = alpha.shape
    ys, xs = np.nonzero(alpha > 2)
    x1, x2 = max(0, xs.min() - 4), min(w, xs.max() + 5)
    y1, y2 = max(0, ys.min() - 4), min(h, ys.max() + 5)
    rgba = np.dstack([rgb[y1:y2, x1:x2], alpha[y1:y2, x1:x2]]).clip(0, 255).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)
    return [round(x1 / w, 5), round(y1 / h, 5), round(x2 / w, 5), round(y2 / h, 5)]


def _resize(a: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8)).resize(size, Image.Resampling.BILINEAR),
                      dtype=np.float32) / 255


def _hex(px: np.ndarray) -> str:
    r, g, b = (int(round(v)) for v in px.mean(axis=0))
    return f"#{r:02x}{g:02x}{b:02x}"


def _bottoms(mask: np.ndarray) -> np.ndarray:
    """Lowest mask row per column, -1 where the column is empty."""
    h = mask.shape[0]
    rows = np.where(mask, np.arange(h)[:, None], -1)
    return rows.max(axis=0)


def cut_style(staged: Image.Image, plate: Image.Image, pieces: list[dict[str, Any]], camera: dict[str, float],
              out_dir: Path, prefix: str, debug_dir: Path | None = None) -> dict[str, Any]:
    """`staged` and each piece's `coverage` (a SAM mask, L image) are in hero-frame coordinates.
    Each piece: {id, kind: rug|upright, box, coverage}. `camera`: fx, fy, horizon_y (normalized)."""
    if not pieces:
        raise ValueError("cut_style needs at least one SAM piece; this style has nothing to drop")
    s_out, p_out = _load(staged, OUT), _load(plate, OUT)
    s, p = _load(staged, WORK), _load(plate, WORK)
    # SAM's coverage tops out just under 1 inside a piece (0.97-0.99) and dips where it is
    # unsure; firm it up so a landed piece is fully opaque and only its very edge is soft.
    cov = {i: smoothstep(0.1, 0.9, _gray(pc["coverage"], WORK)) for i, pc in enumerate(pieces)}
    cov_out = {i: smoothstep(0.1, 0.9, _gray(pc["coverage"], OUT)) for i, pc in enumerate(pieces)}
    uprights = [i for i, pc in enumerate(pieces) if pc["kind"] != "rug"]
    rugs = [i for i, pc in enumerate(pieces) if pc["kind"] == "rug"]
    solid = {i: cov[i] > 0.5 for i in cov}
    any_piece = np.logical_or.reduce(list(solid.values()))
    cm = color_match(s, p, ~dilate(any_piece, 24))
    sm, sm_out = apply_color(s, cm), apply_color(s_out, cm)

    # Who is in front of whom: where one piece's mask reaches into another's outline, the
    # one standing nearer the camera (lower base in those columns) is in front. SAM masks
    # are the visible part, so the overlap is decided once, here.
    front_of: dict[int, set[int]] = {i: set() for i in uprights}
    hulls = {i: hull(solid[i]) for i in uprights}
    bottoms = {i: _bottoms(solid[i]) for i in uprights}
    for a in uprights:
        for b in uprights:
            if a == b:
                continue
            reach = hulls[b] & dilate(solid[a], 2)
            if reach.sum() < 0.004 * solid[b].sum():
                continue
            cols = np.nonzero(reach.any(axis=0))[0]
            ba, bb = bottoms[a][cols], bottoms[b][cols]
            both = (ba >= 0) & (bb >= 0)
            if both.any() and np.median(ba[both]) > np.median(bb[both]):
                front_of[b].add(a)
    for b in uprights:
        for a in front_of[b]:
            cov[b] = cov[b] * (1 - cov[a])
            cov_out[b] = cov_out[b] * (1 - cov_out[a])
            solid[b] &= ~solid[a]

    # Contact shadows: a dip in the STAGED floor's own brightness next to a piece, relative to
    # the staged floor around it (Meta Image also regrades the floor; that is not a shadow).
    lum_s = sm @ LUMA
    floor_rows = np.zeros_like(any_piece)
    floor_rows[int(0.62 * WORK[1]):] = True
    floor_px = floor_rows & ~dilate(any_piece, 14)
    wsum = blur(floor_px.astype(np.float32), 18)
    ambient = np.where(wsum > 0.02, blur(lum_s * floor_px, 18) / np.maximum(wsum, 1e-3), lum_s)
    shade = np.clip(lum_s / np.maximum(ambient, 1.0), 0, 1)

    # SAM leaves out a piece's dark recessed base (a sofa plinth). Pixels just under a piece's
    # mask that are much darker than the floor around them, and belong to no other mask, are
    # that base: they fall with the piece instead of staying behind as a dark stain.
    taken = any_piece.copy()
    for i in uprights:
        bottom = _bottoms(solid[i])
        rows = np.arange(WORK[1])[:, None]
        below = (rows > bottom[None, :]) & (rows <= bottom[None, :] + int(0.035 * WORK[1])) & (bottom[None, :] >= 0)
        base = below & (shade < 0.4) & (lum_s < 90) & ~taken
        comps = [c for c in components(base) if (dilate(c, 1) & solid[i]).any()]
        if comps:
            plinth = np.logical_or.reduce(comps)
            solid[i] |= plinth
            cov[i] = np.maximum(cov[i], plinth)
            cov_out[i] = np.maximum(cov_out[i], blur(_resize(plinth.astype(np.float32), OUT), 0.8))
            taken |= plinth
    sam_any, any_piece = any_piece, np.logical_or.reduce(list(solid.values()))
    shadows: dict[int, np.ndarray] = {}
    for i in uprights:
        bx = pieces[i]["box"]
        band = rect([bx[0], bx[1] + 0.55 * (bx[3] - bx[1]), bx[2], bx[3]], WORK, 0.03, 0.0, 0.05)
        # The base is in the zone too: its soft lower edge must sit on shadow, not bare rug.
        shadows[i] = band & dilate(solid[i], 10) & ~sam_any & (shade < 0.95)

    result: dict[str, Any] = {"color_match": cm.round(4).tolist(), "pieces": []}
    layers: list[tuple[str, np.ndarray, np.ndarray]] = []
    any_body = np.logical_or.reduce([solid[i] for i in uprights] or [np.zeros_like(any_piece)])
    rug_area = np.zeros_like(any_piece)

    for r in rugs:
        vis = solid[r] & ~any_body
        # Shading on the rug next to a piece is that piece's shadow, not the rug's colour.
        f = rug_shading(lum_s, vis)
        owner = np.full(f.shape, -1)
        weight = np.zeros_like(f)
        for i in uprights:
            bx = pieces[i]["box"]
            near = blur(rect([bx[0], bx[1] + 0.5 * (bx[3] - bx[1]), bx[2], bx[3]], WORK, 0.05, 0.0, 0.07)
                        .astype(np.float32), 6)
            better = near > weight
            owner[better], weight[better] = i, near[better]
        f_eff = np.where(vis, 1 - (1 - f) * weight, 1.0)
        for i in uprights:
            shadows[i] = (shadows[i] & ~vis) | (vis & (owner == i) & (f_eff < 0.97))
        shade = np.where(vis, f_eff, shade)
        rug_area |= vis
        # Under the furniture (inside the rug's outline only) the rug is hidden: fill it with
        # clean, unshaded weave from the same rows so it is whole while it falls. A few pixels
        # past each piece's edge too, so no soft mask edge lets the bare floor show through.
        hidden = hull(vis) & dilate(any_body, 7)
        k_out = _resize(f_eff, OUT)
        vis_out = _resize(vis.astype(np.float32), OUT) > 0.5
        hidden_out = _resize(hidden.astype(np.float32), OUT) > 0.5
        # Un-shading by brightness alone leaves shaded weave sky-blue (shadows are lit by the
        # window's sky) next to warm lit weave. The rug is one material: its colour is the lit
        # rug's median colour everywhere, its brightness the un-shaded local brightness, and
        # its weave each pixel's own detail. One colour, no seams, before anything lands.
        lit = vis_out & (k_out > 0.97)
        tone = np.median(sm_out[lit], axis=0) if lit.any() else np.median(sm_out[vis_out], axis=0)
        vis_f = vis_out.astype(np.float32)
        lp_vis = blur(sm_out * vis_f[..., None], 10) / np.maximum(blur(vis_f, 10), 1e-3)[..., None]
        k3 = np.maximum(k_out, 0.3)[..., None]
        albedo = tone / max(float(tone @ LUMA), 1.0) * (lp_vis @ LUMA)[..., None] / k3 + (sm_out - lp_vis) / k3
        # Copy only from lit weave well away from the furniture: shaded weave is sky-blue,
        # and brightening it back leaves a pale blue patch.
        near_body = _resize(dilate(any_body, 14).astype(np.float32), OUT) > 0.5
        clean = erode(vis_out, 3) & (k_out > 0.97) & ~near_body
        filled, shifts = floor_transplant(albedo, clean, hidden_out, camera)
        # Keep the copied weave's detail but take the colour of the rug around the hole (the
        # far rows are window-lit and cooler): swap the hole's low frequencies for its own.
        hole_f, ref_f = hidden_out.astype(np.float32), (vis_out & ~hidden_out).astype(np.float32)
        lp_hole = blur(filled * hole_f[..., None], 40) / np.maximum(blur(hole_f, 40), 1e-3)[..., None]
        lp_ref = blur(filled * ref_f[..., None], 40) / np.maximum(blur(ref_f, 40), 1e-3)[..., None]
        filled = np.where(hidden_out[..., None], np.clip(filled - lp_hole + lp_ref, 0, 255), filled)
        alpha = np.clip(np.maximum(cov_out[r], blur(hidden_out.astype(np.float32), 1.2)) * 255, 0, 255)
        rect_out = _save_rgba(filled, alpha, out_dir / f"{prefix}_{pieces[r]['id']}.png")
        layers.append(("rug", filled, alpha))
        result["pieces"].append({
            **{k: v for k, v in pieces[r].items() if k != "coverage"},
            "texture": f"{prefix}_{pieces[r]['id']}.png", "rect": rect_out,
            "palette": _hex(sm_out[vis_out]), "palette_staged": _hex(s_out[vis_out]),
            "filled_hidden": round(float(hidden.sum()) / max(1, float((vis | hidden).sum())), 3),
            "fill_floor_moves_m": shifts,
        })

    order = _topo(uprights, front_of, pieces)
    bodies_out: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    shadows_out: dict[int, np.ndarray] = {}
    for i in order:
        pc = pieces[i]
        body = solid[i]
        hidden = np.zeros_like(body)
        if front_of[i]:
            hidden = hulls[i] & np.logical_or.reduce([solid[j] for j in front_of[i]])
        body_out = cov_out[i] > 0.5
        hidden_out = _resize(hidden.astype(np.float32), OUT) > 0.5
        filled, shifts = sm_out, []
        if hidden.any():
            filled, shifts = transplant(sm_out, erode(body_out, 3), hidden_out & ~body_out, 500)
        bodies_out[i] = (filled, np.clip(np.maximum(blur(cov_out[i], 1.2), hidden_out) * 255, 0, 255))
        # On the floor: soft, low-passed darkening, spread a few pixels under the piece's own
        # edge so it is full strength where the piece meets the floor (no bright rim). On the
        # rug: exactly the shading taken out of the rug, so the landed rug is the staged rug.
        dark = np.clip(1 - shade, 0, 1) * shadows[i]
        shadows_out[i] = _resize(np.where(rug_area, dark, blur(grey_dilate(dark * ~rug_area, 3), 2.5)), OUT)
        result["pieces"].append({
            **{k: v for k, v in pc.items() if k != "coverage"},
            "base": base_points(body | hidden),
            "in_front_of": sorted(pieces[j]["id"] for j in uprights if i in front_of[j]),
            "behind": sorted(pieces[j]["id"] for j in front_of[i]),
            "palette": _hex(sm_out[body_out]), "palette_staged": _hex(s_out[body_out]),
            "filled_hidden": round(float(hidden.sum()) / max(1, float((body | hidden).sum())), 3),
            "fill_shifts_px": [int(v) for v in shifts],
        })

    def compose() -> tuple[np.ndarray, np.ndarray]:
        """Landed frame (rug, shadows, bodies back to front) and the frame under the bodies."""
        under = p_out.copy()
        for _, rgb, alpha in layers:
            a = alpha[..., None] / 255
            under = under * (1 - a) + rgb * a
        for i in order:
            under = under * (1 - shadows_out[i][..., None])
        final = under.copy()
        for i in order:
            rgb, alpha = bodies_out[i]
            a = alpha[..., None] / 255
            final = final * (1 - a) + rgb * a
        return final, under

    # Where a piece meets the rug or floor, the staging has a thin, near-black contact line
    # that SAM's mask stops just short of. Whatever is still brighter there than the staged
    # image, right around a piece, becomes part of that piece's shadow: landed matches staged.
    final, under = compose()
    lum = lambda a: a @ LUMA  # noqa: E731
    for i in order:
        _, alpha = bodies_out[i]
        a = alpha / 255
        bx = pieces[i]["box"]
        foot = rect([bx[0], bx[1] + 0.55 * (bx[3] - bx[1]), bx[2], bx[3]], WORK, 0.03, 0.0, 0.05)
        ring = _resize((dilate(solid[i], 9) & ~erode(solid[i], 1) & foot).astype(np.float32), OUT) > 0.5
        ring &= a < 0.95
        b = lum(bodies_out[i][0])
        want_under = (lum(sm_out) - a * b) / np.maximum(1 - a, 0.05)
        extra = np.clip(1 - want_under / np.maximum(lum(under), 1.0), 0, 0.95) * ring
        shadows_out[i] = 1 - (1 - shadows_out[i]) * (1 - blur(extra, 0.8))
    final, _ = compose()

    for entry, i in zip(result["pieces"][len(rugs):], order):
        pid = pieces[i]["id"]
        filled, alpha = bodies_out[i]
        entry["texture"], entry["rect"] = f"{prefix}_{pid}.png", _save_rgba(filled, alpha, out_dir / f"{prefix}_{pid}.png")
        sh = shadows_out[i] * 255
        entry["shadow"] = None
        if sh.max() > 8:
            entry["shadow"] = {"texture": f"{prefix}_{pid}_shadow.png", "max_darkening": round(float(sh.max()) / 255, 3),
                               "rect": _save_rgba(np.zeros_like(sm_out), sh, out_dir / f"{prefix}_{pid}_shadow.png")}

    composite = final
    near = dilate(any_piece, 10)
    err = np.abs(_load(Image.fromarray(composite.clip(0, 255).astype(np.uint8)), WORK) - sm).mean(axis=2)
    result["check"] = {
        "landed_vs_staged_mean_abs": round(float(err[near].mean()), 2),
        "landed_vs_staged_note": "mean colour difference (0-255) around the furniture, landed render vs "
                                 "colour-matched staged image; the rest of the frame is the filmed room",
    }
    result["draw_order"] = [pieces[r]["id"] for r in rugs] + [pieces[i]["id"] for i in order]
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        Image.fromarray(composite.clip(0, 255).astype(np.uint8)).save(debug_dir / f"{prefix}_landed.jpg", quality=92)
        Image.fromarray(sm_out.clip(0, 255).astype(np.uint8)).save(debug_dir / f"{prefix}_staged_matched.jpg", quality=92)
    return result


def _topo(items: list[int], front_of: dict[int, set[int]], pieces: list[dict[str, Any]]) -> list[int]:
    """Back-to-front order: a piece comes after every piece it is in front of."""
    placed: list[int] = []
    left = sorted(items, key=lambda i: pieces[i]["box"][3])
    while left:
        for i in left:
            if all(j in placed for j in items if i in front_of[j]):
                placed.append(i)
                left.remove(i)
                break
        else:
            placed += left
            break
    return placed
