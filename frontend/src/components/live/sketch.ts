import { media } from "../../api";

/**
 * A grayscale pencil-sketch render of an image: warm paper, ink edges, a faint tonal wash.
 * Plain canvas maths on an already-published image — no model call. Used for the
 * sketch -> finished opening that plays before the cascade.
 */
const WIDTH = 512;
const PAPER = 243;
const WASH = 0.3;
const INK = 1.15;

const cache = new Map<string, Promise<string | null>>();

async function load(path: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.src = media(path);
  await img.decode();
  return img;
}

async function compute(path: string): Promise<string | null> {
  const img = await load(path);
  const w = WIDTH;
  const h = Math.max(1, Math.round((WIDTH * img.naturalHeight) / img.naturalWidth));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0, w, h);
  const src = ctx.getImageData(0, 0, w, h).data;

  const n = w * h;
  const gray = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    gray[i] = 0.2126 * src[o] + 0.7152 * src[o + 1] + 0.0722 * src[o + 2];
  }

  const out = ctx.createImageData(w, h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      let ink = 0;
      if (x > 0 && x < w - 1 && y > 0 && y < h - 1) {
        const gx =
          -gray[i - w - 1] - 2 * gray[i - 1] - gray[i + w - 1] + gray[i - w + 1] + 2 * gray[i + 1] + gray[i + w + 1];
        const gy =
          -gray[i - w - 1] - 2 * gray[i - w] - gray[i - w + 1] + gray[i + w - 1] + 2 * gray[i + w] + gray[i + w + 1];
        ink = Math.min(255, Math.hypot(gx, gy) * INK);
      }
      const v = Math.max(0, Math.min(255, PAPER - gray[i] * WASH - ink * 0.85));
      const o = i * 4;
      out.data[o] = v;
      out.data[o + 1] = v * 0.982;
      out.data[o + 2] = v * 0.938;
      out.data[o + 3] = 255;
    }
  }
  ctx.putImageData(out, 0, 0);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  return blob ? URL.createObjectURL(blob) : null;
}

/** Cached per image path. Resolves to null when the image can't be read. */
export function sketch(path: string | null | undefined): Promise<string | null> {
  if (!path) return Promise.resolve(null);
  let hit = cache.get(path);
  if (!hit) {
    hit = compute(path).catch(() => null);
    cache.set(path, hit);
  }
  return hit;
}
