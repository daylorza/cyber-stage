/** The Prototype Testing assets, built locally by `make prototype` into public/prototype/ (git-ignored). */

export type Rect = [number, number, number, number];

export type Piece = {
  id: string;
  name: string;
  concept: string;
  kind: "rug" | "upright";
  /** SAM 3.1 box, normalized hero-frame coordinates. */
  box: Rect;
  texture: string;
  /** Where the texture sits in the hero frame (normalized x1, y1, x2, y2). */
  rect: Rect;
  /** Floor contact points (normalized image x, y) for upright pieces. */
  base?: [number, number][];
  shadow?: { texture: string; rect: Rect; max_darkening: number } | null;
  palette: string;
  palette_staged: string;
};

export type Style = {
  id: string;
  label: string;
  available: boolean;
  reason?: string;
  reason_short?: string;
  source: string;
  pieces?: Piece[];
  draw_order?: string[];
};

export type Calibration = {
  vfov_deg: number;
  pitch_deg: number;
  roll_deg: number;
  height_m: number;
  ceiling_m: number;
};

export type Manifest = {
  label: string;
  video: { src: string; width: number; height: number; fps: number; duration: number };
  hero: { pts: number; seek: number; plate: string };
  camera: Calibration;
  styles: Style[];
};

export const ASSET_ROOT = "/prototype/";

/** Asset root for a generalised listing's cascade (Work 3), built by
 *  `python -m prototype.general`; the POC root stays the default. */
export const generalRoot = (listingId: string) => `/prototype-general/${listingId}/`;

export async function loadManifest(root: string = ASSET_ROOT): Promise<Manifest> {
  const res = await fetch(`${root}manifest.json`, { cache: "no-store" });
  const type = res.headers.get("content-type") ?? "";
  if (!res.ok || !type.includes("json")) throw new Error("missing");
  return res.json();
}
