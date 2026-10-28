import { media, type LiveRoom, type Piece } from "../../api";

/** Extra width and height beyond "cover", so there is a little room to pan. */
export const PAN_PAD = 1.08;
export const LOOK_DEGREES = 35;

export type Box = [number, number, number, number];
export type Size = { w: number; h: number };
/** `fit` = a tall room shown whole at viewport height, with a blurred backdrop behind it. */
export type Stage = Size & { fit: boolean };

export const roomAspect = (room: LiveRoom) => (room.size && room.size[0] > 0 && room.size[1] > 0 ? room.size[0] / room.size[1] : 16 / 9);

/** Rooms much narrower than the screen (vertical phone footage) are shown whole instead of cropped. */
export const isFit = (aspect: number, vw: number, vh: number) => aspect < (vw / vh) * 0.75;

/**
 * Cover mode: the box that covers the viewport at the room's aspect ratio, so normalized boxes map by
 * percentage. Fit mode: the whole room at viewport height, centred.
 */
export function stageSize(vw: number, vh: number, aspect: number): Stage {
  if (isFit(aspect, vw, vh)) return { w: vh * aspect, h: vh, fit: true };
  const w = Math.max(vw, vh * aspect);
  return { w: w * PAN_PAD, h: (w / aspect) * PAN_PAD, fit: false };
}

export const maxPanFor = (stage: Stage, vw: number) => (stage.fit ? 0 : Math.max(0, (stage.w - vw) / 2));

/** Vertical camera offset that frames the staged furniture when the stage is taller than the viewport. */
export function restOffset(pieces: Piece[], stage: Stage, vh: number): number {
  const my = Math.max(0, (stage.h - vh) / 2);
  if (stage.fit || my === 0) return 0;
  const items = planPieces(pieces);
  if (items.length === 0) return 0;
  const top = Math.min(...items.map((i) => i.y1));
  const bottom = Math.max(...items.map((i) => i.y2));
  const y = -((top + bottom) / 2 - 0.5) * stage.h;
  return Math.max(-my, Math.min(my, y));
}

const loaded = new Map<string, { img: HTMLImageElement; done: Promise<void> }>();

/** Fetch and decode an image ahead of time. Never rejects. */
export function preload(path: string | null | undefined): Promise<void> {
  if (!path) return Promise.resolve();
  const url = media(path);
  let hit = loaded.get(url);
  if (!hit) {
    const img = new Image();
    img.decoding = "async";
    img.src = url;
    hit = { img, done: img.decode().catch(() => undefined) };
    loaded.set(url, hit);
  }
  return hit.done;
}

export type StyleStatus = { ok: boolean; reason: string };

export function styleStatus(room: LiveRoom, id: string): StyleStatus {
  const s = room.styles[id];
  if (s && s.available && s.image) return { ok: true, reason: "" };
  const reason =
    (s?.geometry?.status === "fail" && s.geometry.reason) ||
    s?.error ||
    (s?.structure?.status === "fail" && s.structure.reason) ||
    "Not available for this room";
  return { ok: false, reason };
}

/** The buyer's chosen style, or the default when this room can't show it. */
export function resolveStyle(room: LiveRoom, chosen: string, fallback: string): { id: string | null; fellBack: boolean } {
  if (styleStatus(room, chosen).ok) return { id: chosen, fellBack: false };
  if (styleStatus(room, fallback).ok) return { id: fallback, fellBack: true };
  const other = Object.keys(room.styles).find((id) => styleStatus(room, id).ok);
  return { id: other ?? null, fellBack: true };
}

export type PieceItem = {
  key: string;
  concept: string;
  /** Padded clip box, normalized. */
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Feather widths inside the clip box, in percent of its own size. */
  fl: number;
  fr: number;
  ft: number;
  fb: number;
  /** Starting offset above the room, in percent of the piece's own height. */
  drop: number;
  flat: boolean;
};

const PAD = 0.028;
const RUG = /rug|carpet/i;
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

/** Rug first, then large to small. Boxes that cover most of the room are left to the full image. */
export function planPieces(pieces: Piece[]): PieceItem[] {
  return pieces
    .map((p, i) => {
      const [a, b, c, d] = p.box;
      const x1 = clamp01(Math.min(a, c));
      const x2 = clamp01(Math.max(a, c));
      const y1 = clamp01(Math.min(b, d));
      const y2 = clamp01(Math.max(b, d));
      return { p, i, x1, y1, x2, y2, area: (x2 - x1) * (y2 - y1) };
    })
    .filter((b) => b.x2 - b.x1 > 0.02 && b.y2 - b.y1 > 0.02 && b.area >= 0.0015 && b.area <= 0.55)
    .sort((a, b) => Number(RUG.test(b.p.concept)) - Number(RUG.test(a.p.concept)) || b.area - a.area)
    .slice(0, 8)
    .map(({ p, i, x1, y1, x2, y2 }) => {
      const X1 = clamp01(x1 - PAD);
      const Y1 = clamp01(y1 - PAD);
      const X2 = clamp01(x2 + PAD);
      const Y2 = clamp01(y2 + PAD);
      const w = X2 - X1;
      const h = Y2 - Y1;
      return {
        key: `${i}-${p.concept}`,
        concept: p.concept,
        x1: X1,
        y1: Y1,
        x2: X2,
        y2: Y2,
        fl: ((x1 - X1) / w) * 100,
        fr: ((X2 - x2) / w) * 100,
        ft: ((y1 - Y1) / h) * 100,
        fb: ((Y2 - y2) / h) * 100,
        drop: (Y2 / h) * 100 + 10,
        flat: RUG.test(p.concept),
      };
    });
}

/** `soft` swaps the thin pad-ring feather for a wide one, so a whole-box patch reads as a fade-in. */
export const featherMask = (i: PieceItem, soft = false) => {
  const gradient = (dir: string, a: number, b: number) =>
    `linear-gradient(${dir}, transparent 0%, #000 ${a}%, #000 ${100 - b}%, transparent 100%)`;
  return soft
    ? `${gradient("to right", 26, 26)}, ${gradient("to bottom", 30, 30)}`
    : `${gradient("to right", i.fl, i.fr)}, ${gradient("to bottom", i.ft, i.fb)}`;
};

// ── camera for the live-in moments ──

export type Cam = { x: number; y: number; s: number };
export type Frame = { stage: Stage; vw: number; vh: number };

const clampTo = (v: number, limit: number) => Math.max(-limit, Math.min(limit, v));

/** Zoom that makes the focus box fill `fill` of the viewport, bounded. */
export function scaleFor(focus: Box, f: Frame, fill: number, min: number, max: number): number {
  const bw = Math.max(0.02, focus[2] - focus[0]) * f.stage.w;
  const bh = Math.max(0.02, focus[3] - focus[1]) * f.stage.h;
  // Fit-mode rooms come from ~1000px-wide phone frames, so keep the zoom where they stay sharp.
  const cap = f.stage.fit ? Math.min(max, 2.2) : max;
  return Math.max(Math.min(min, cap), Math.min(cap, Math.min((fill * f.vw) / bw, (fill * f.vh) / bh)));
}

/** Camera that centres the focus box at zoom `s`, never showing beyond the room's edge. */
export function aim(focus: Box, s: number, f: Frame, lift = 0): Cam {
  const cx = (focus[0] + focus[2]) / 2 - 0.5;
  const cy = (focus[1] + focus[3]) / 2 - 0.5;
  // Fit mode: the backdrop covers the sides. A zoomed stage narrower than the screen may slide until its edge meets
  // the screen edge (centring a far-off focus would leave a dead strip), and one wider than the screen stays covering.
  const mx = f.stage.fit ? Math.abs(s * f.stage.w - f.vw) / 2 : Math.max(0, (s * f.stage.w - f.vw) / 2);
  const my = Math.max(0, (s * f.stage.h - f.vh) / 2);
  return { x: clampTo(-s * cx * f.stage.w, mx), y: clampTo(-s * cy * f.stage.h - lift * f.vh, my), s };
}
