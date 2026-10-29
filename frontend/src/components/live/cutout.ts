import { media } from "../../api";

/** Where the staged image differs from the plate, as a soft alpha mask. Plain pixel maths, no model call. */
export type Cut = { url: string; w: number; h: number; alpha: Uint8Array };

const WIDTH = 384;
const MIN_PIECE_COVERAGE = 0.06;
const MAX_CHANGED = 0.85;
// Tuned on real Meta output: an AI-emptied plate regrades walls and ceiling more than the 38th percentile
// suggests, so the baseline sits at the median and the ramp starts a little higher.
const BASELINE_PERCENTILE = 0.5;
const EDGE_LO = 18;
const EDGE_HI = 52;

const cache = new Map<string, Promise<Cut | null>>();

async function load(path: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.src = media(path);
  await img.decode();
  return img;
}

const smooth = (lo: number, hi: number, x: number) => {
  const t = Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
  return t * t * (3 - 2 * t);
};

function grow(alpha: Uint8Array, w: number, h: number, r: number): Uint8Array {
  const pass = (src: Uint8Array, horizontal: boolean) => {
    const out = new Uint8Array(src.length);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        let m = 0;
        for (let k = -r; k <= r; k++) {
          const xx = horizontal ? x + k : x;
          const yy = horizontal ? y : y + k;
          if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
          const v = src[yy * w + xx];
          if (v > m) m = v;
        }
        out[y * w + x] = m;
      }
    return out;
  };
  return pass(pass(alpha, true), false);
}

async function compute(plate: string, staged: string): Promise<Cut | null> {
  const [a, b] = await Promise.all([load(plate), load(staged)]);
  const w = WIDTH;
  const h = Math.max(1, Math.round((WIDTH * b.naturalHeight) / b.naturalWidth));
  const draw = (img: HTMLImageElement) => {
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    ctx.filter = "blur(1.5px)";
    ctx.drawImage(img, 0, 0, w, h);
    return ctx.getImageData(0, 0, w, h).data;
  };
  const pa = draw(a);
  const pb = draw(b);

  const n = w * h;
  const diff = new Float32Array(n);
  const hist = new Uint32Array(256);
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    const d = (Math.abs(pa[o] - pb[o]) + Math.abs(pa[o + 1] - pb[o + 1]) + Math.abs(pa[o + 2] - pb[o + 2])) / 3;
    diff[i] = d;
    hist[Math.min(255, Math.round(d))]++;
  }
  // A low percentile of the difference is the global regrade, not furniture.
  let seen = 0;
  let baseline = 0;
  for (let v = 0; v < 256; v++) {
    seen += hist[v];
    if (seen >= n * BASELINE_PERCENTILE) {
      baseline = v;
      break;
    }
  }
  const raw = new Uint8Array(n);
  let changed = 0;
  for (let i = 0; i < n; i++) {
    const s = smooth(baseline + EDGE_LO, baseline + EDGE_HI, diff[i]);
    raw[i] = Math.round(s * 255);
    if (s > 0.5) changed++;
  }
  if (changed / n > MAX_CHANGED) return null;

  const grown = grow(raw, w, h, 2);
  const mask = document.createElement("canvas");
  mask.width = w;
  mask.height = h;
  const mctx = mask.getContext("2d")!;
  const data = mctx.createImageData(w, h);
  for (let i = 0; i < n; i++) {
    data.data[i * 4] = data.data[i * 4 + 1] = data.data[i * 4 + 2] = 255;
    data.data[i * 4 + 3] = grown[i];
  }
  mctx.putImageData(data, 0, 0);
  const soft = document.createElement("canvas");
  soft.width = w;
  soft.height = h;
  const sctx = soft.getContext("2d")!;
  sctx.filter = "blur(3px)";
  sctx.drawImage(mask, 0, 0);
  const blob = await new Promise<Blob | null>((resolve) => soft.toBlob(resolve, "image/png"));
  if (!blob) return null;
  return { url: URL.createObjectURL(blob), w, h, alpha: grown };
}

/**
 * The furniture mask with every falling piece's oval cut out of it, drawn on canvas (not
 * mask-composite, which drops the subtraction in Chrome). What remains is decor — artwork,
 * shelving, curtains — revealed during the sketch opening before the pieces drop.
 */
const decorCache = new Map<string, Promise<string | null>>();

export function maskMinusOvals(maskPath: string | null | undefined, ovals: [number, number, number, number][]): Promise<string | null> {
  if (!maskPath) return Promise.resolve(null);
  const key = `${maskPath}|${ovals.map((o) => o.map((v) => v.toFixed(3)).join(",")).join(";")}`;
  let hit = decorCache.get(key);
  if (!hit) {
    hit = (async () => {
      // The path is already a resolved URL (media() path or a blob URL), so it is not re-wrapped.
      const img = new Image();
      img.src = maskPath;
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0);
      ctx.globalCompositeOperation = "destination-out";
      const grow = 0.07;
      for (const [x1, y1, x2, y2] of ovals) {
        const w = (x2 - x1 + 2 * grow) * canvas.width;
        const h = (y2 - y1 + 2 * grow) * canvas.height;
        ctx.beginPath();
        ctx.ellipse(((x1 + x2) / 2) * canvas.width, ((y1 + y2) / 2) * canvas.height, w / 2, h / 2, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      return blob ? URL.createObjectURL(blob) : null;
    })().catch(() => null);
    decorCache.set(key, hit);
  }
  return hit;
}

/** Cached per plate and staged image. Resolves to null when the mask can't be made or isn't useful. */
export function cutout(plate: string | null | undefined, staged: string | null | undefined): Promise<Cut | null> {
  if (!plate || !staged) return Promise.resolve(null);
  const key = `${plate}|${staged}`;
  let hit = cache.get(key);
  if (!hit) {
    hit = compute(plate, staged).catch(() => null);
    cache.set(key, hit);
  }
  return hit;
}

/** Mean mask alpha (0..1) inside a normalized box. */
export function boxCoverage(cut: Cut, x1: number, y1: number, x2: number, y2: number): number {
  const ax = Math.max(0, Math.floor(x1 * cut.w));
  const bx = Math.min(cut.w, Math.ceil(x2 * cut.w));
  const ay = Math.max(0, Math.floor(y1 * cut.h));
  const by = Math.min(cut.h, Math.ceil(y2 * cut.h));
  let sum = 0;
  let count = 0;
  for (let y = ay; y < by; y++)
    for (let x = ax; x < bx; x++) {
      sum += cut.alpha[y * cut.w + x];
      count++;
    }
  return count ? sum / count / 255 : 0;
}

export const usable = (cut: Cut | null, box: [number, number, number, number]) =>
  !!cut && boxCoverage(cut, box[0], box[1], box[2], box[3]) >= MIN_PIECE_COVERAGE;
