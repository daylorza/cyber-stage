import * as THREE from "three";
import { ASSET_ROOT, type Calibration, type Piece, type Rect, type Style } from "./manifest";

/**
 * The Three.js layer over the paused hero frame. Three.js only renders: every pixel it draws
 * comes from the broker-approved Meta Image staging, cut along SAM 3.1 masks.
 *
 * The camera is the clip's camera (field of view, height and pitch from the hero frame's
 * vanishing points). Each piece is a 3D proxy at its real place in the room: the rug a sheet on
 * the floor plane, an upright piece a vertical card standing on its floor-contact line. Its
 * texture is PROJECTED from that camera at rest, so landed it is exactly the staged image, and
 * while it falls the texture rides the geometry in true perspective. Everything above the
 * ceiling plane is clipped, so pieces come down through the ceiling, never fade in.
 */

const VERT = /* glsl */ `
attribute vec3 restPosition;
uniform mat4 restViewProj;
varying vec4 vRest;
varying float vWorldY;
void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorldY = world.y;
  vRest = restViewProj * vec4(restPosition, 1.0);
  gl_Position = projectionMatrix * viewMatrix * world;
}`;

const FRAG = /* glsl */ `
uniform sampler2D map;
uniform vec4 rect;
uniform float ceiling;
uniform float feather;
uniform float opacity;
uniform vec3 gain;
uniform vec3 offset;
uniform float fix;
uniform vec4 foot[4];
uniform float reveal[4];
uniform vec3 plain;
varying vec4 vRest;
varying float vWorldY;
void main() {
  vec2 ndc = vRest.xy / vRest.w;
  vec2 img = vec2(ndc.x * 0.5 + 0.5, 0.5 - ndc.y * 0.5);
  vec2 uv = (img - rect.xy) / (rect.zw - rect.xy);
  if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) discard;
  vec4 c = texture2D(map, uv);
  // PT-01/03/04: where a piece will stand, the rug shows plain weave (its own
  // detail flattened to one tone) until that piece lands. No pre-baked shadow,
  // no filled patch, no base line can show through.
  for (int i = 0; i < 4; i++) {
    vec4 f = foot[i]; // (x, y) of the base line's left end, (z, w) of its right end
    if (f.z > f.x) {
      float t = clamp((img.x - f.x) / (f.z - f.x), 0.0, 1.0);
      float baseY = mix(f.y, f.w, t);
      float mx = smoothstep(f.x - 0.03, f.x - 0.005, img.x) * smoothstep(f.z + 0.03, f.z + 0.005, img.x);
      float mask = mx * smoothstep(0.055, 0.02, abs(img.y - baseY));
      // Plain weave: real rug weave sampled from the rug's clean front area
      // (toward the camera, where nothing stands), so the footprint shows
      // weave only — no shadow, no filled patch, no base line.
      vec3 src = texture2D(map, clamp(uv + vec2(0.0, 0.35), 0.0, 1.0)).rgb;
      c.rgb = mix(c.rgb, src, mask * (1.0 - reveal[i]));
    }
  }
  c.rgb = mix(c.rgb, clamp(c.rgb * gain + offset, 0.0, 1.0), fix);
  float a = c.a * opacity * (1.0 - smoothstep(ceiling - feather, ceiling, vWorldY));
  if (a < 0.002) discard;
  gl_FragColor = vec4(c.rgb * a, a);
}`;

/** CSS-style cubic-bezier easing. */
export function cubicBezier(x1: number, y1: number, x2: number, y2: number) {
  const at = (a: number, b: number, t: number) => 3 * a * t * (1 - t) ** 2 + 3 * b * t * t * (1 - t) + t ** 3;
  const slope = (a: number, b: number, t: number) => 3 * a * (1 - t) ** 2 + 6 * (b - a) * t * (1 - t) + 3 * (1 - b) * t * t;
  return (x: number) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 6; i++) {
      const d = slope(x1, x2, t);
      if (Math.abs(d) < 1e-6) break;
      t = Math.min(1, Math.max(0, t - (at(x1, x2, t) - x) / d));
    }
    return at(y1, y2, t);
  };
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const smooth = (a: number, b: number, v: number) => {
  const t = clamp01((v - a) / (b - a));
  return t * t * (3 - 2 * t);
};
/** Slow off the ceiling, accelerating, a short soft check before the floor: weight, not a bounce. */
const FALL = cubicBezier(0.5, 0, 0.72, 0.94);
/** Fabric: drag keeps the rug slower, and it settles rather than lands. */
const RUG_FALL = cubicBezier(0.42, 0, 0.62, 1);
const SETTLE = cubicBezier(0.2, 0.7, 0.3, 1);
const LIFT = cubicBezier(0.55, 0, 0.85, 0.4);

/** 0 = card along the piece's floor-contact line, 1 = card square to the camera. */
const CARD_FACING = 0.6;

export const TIMING = {
  rug: 2.4,
  firstUpright: 1.55,
  stagger: 0.8,
  upright: 1.45,
  contact: 0.8,
  rugTouch: 0.6,
  lift: 0.75,
  liftStagger: 0.07,
};

type Item = {
  piece: Piece;
  mesh: THREE.Mesh;
  pivot: THREE.Vector3;
  top: number;
  start: number;
  dur: number;
  sign: number;
  axis: THREE.Vector3;
  shadow?: THREE.Mesh;
  blob: THREE.Mesh;
  blobSize: [number, number];
  rug?: { rest: Float32Array; half: [number, number] };
};

type Mode = "empty" | "cascade" | "landed" | "lift";

export class CascadeScene {
  readonly renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private restViewProj = new THREE.Matrix4();
  private floor = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private items: Item[] = [];
  private textures: THREE.Texture[] = [];
  private blobTex: THREE.Texture;
  private mode: Mode = "empty";
  private clock = 0;
  private frozen: number | null = null;
  private total = 0;
  private last = 0;
  private raf = 0;
  private dirty = true;
  private liftFrom: number[] = [];
  private settle: ((done: boolean) => void) | null = null;
  /** Piece id -> rug footprint slot it reveals on landing. */
  private footSlot = new Map<string, number>();
  /** Per-channel map from the extracted hero frame's colours to how this browser shows the clip. */
  private gain = new THREE.Vector3(1, 1, 1);
  private offset = new THREE.Vector3(0, 0, 0);
  colourFit: { gain: number[]; offset: number[]; pixels: number } | null = null;

  constructor(canvas: HTMLCanvasElement, private cal: Calibration, aspect: number, private assetRoot: string = ASSET_ROOT) {
    // preserveDrawingBuffer: the landed room is drawn once and must stay on screen as drawn.
    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, premultipliedAlpha: true, preserveDrawingBuffer: true });
    this.renderer.setClearColor(0x000000, 0);
    // Textures carry the staged image's own sRGB values; draw them as they are.
    this.renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    this.camera = new THREE.PerspectiveCamera(cal.vfov_deg, aspect, 0.05, 200);
    this.camera.position.set(0, cal.height_m, 0);
    this.camera.rotation.set(-THREE.MathUtils.degToRad(cal.pitch_deg), 0, 0);
    this.camera.updateMatrixWorld();
    this.camera.updateProjectionMatrix();
    this.restViewProj.multiplyMatrices(this.camera.projectionMatrix, this.camera.matrixWorldInverse);
    this.blobTex = blobTexture();
    this.raf = requestAnimationFrame(this.frame);
  }

  resize(width: number, height: number) {
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(width, height, false);
    this.dirty = true;
  }

  get pieces() {
    return this.items.map((i) => i.piece);
  }

  /** Build the pieces for a style (textures loaded); nothing is shown until cascade(). */
  async setStyle(style: Style) {
    const pieces = (style.pieces ?? []).filter((piece) => piece.kind !== "rug");
    const loader = new THREE.TextureLoader();
    const load = async (name: string) => {
      const tex = await loader.loadAsync(this.assetRoot + name);
      tex.flipY = false;
      tex.colorSpace = THREE.NoColorSpace;
      tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
      tex.needsUpdate = true;
      return tex;
    };
    const loaded = await Promise.all(
      pieces.map(async (p) => [await load(p.texture), p.shadow ? await load(p.shadow.texture) : null] as const),
    );
    this.clearItems();
    const order = style.draw_order ?? pieces.map((p) => p.id);
    // Each upright's footprint on the rug: its floor-contact (base) line, end to
    // end, where its shadow, patch and base line all sit, in hero-frame
    // coordinates, plus the slot each item reveals when it lands.
    const footprints = pieces
      .filter((p) => p.kind !== "rug")
      .slice(0, 4)
      .map((p) => {
        const base = p.base?.length ? p.base : [[p.box[0], p.box[3]], [p.box[2], p.box[3]]] as [number, number][];
        const left = base.reduce((a, b) => (b[0] < a[0] ? b : a));
        const right = base.reduce((a, b) => (b[0] > a[0] ? b : a));
        return new THREE.Vector4(left[0], left[1], right[0], right[1]);
      });
    this.footSlot.clear();
    let slot = 0;
    pieces.forEach((p) => {
      if (p.kind !== "rug" && slot < 4) this.footSlot.set(p.id, slot++);
    });
    const rugPalette = pieces.find((p) => p.kind === "rug")?.palette ?? "#c8af86";
    let at = TIMING.firstUpright;
    pieces.forEach((piece, n) => {
      const [tex, shadowTex] = loaded[n];
      this.textures.push(tex, ...(shadowTex ? [shadowTex] : []));
      const rug = piece.kind === "rug";
      const start = rug ? 0 : at;
      if (!rug) at += TIMING.stagger;
      this.items.push(rug ? this.buildRug(piece, tex, footprints, rugPalette) : this.buildUpright(piece, tex, shadowTex, n, start, order));
    });
    this.total = Math.max(0, ...this.items.map((i) => i.start + i.dur));
    this.mode = "empty";
    this.pose();
  }

  /** Drop every piece from the ceiling, in order. Resolves true when all have landed. */
  cascade(): Promise<boolean> {
    this.finish(false);
    this.mode = "cascade";
    this.clock = 0;
    this.frozen = null;
    return new Promise((resolve) => (this.settle = resolve));
  }

  /** Everything up through the ceiling again, last piece first. */
  lift(): Promise<boolean> {
    if (this.mode === "empty") return Promise.resolve(true);
    this.finish(false);
    // Each piece leaves from where it is now; one still above the ceiling stays there.
    this.liftFrom = this.items.map((it, k) => Math.min(this.progress(it, k), it.rug ? TIMING.rugTouch : TIMING.contact));
    this.mode = "lift";
    this.clock = 0;
    this.frozen = null;
    return new Promise((resolve) => (this.settle = resolve));
  }

  showLanded() {
    this.finish(false);
    this.mode = "landed";
    this.dirty = true;
  }

  clear() {
    this.finish(false);
    this.mode = "empty";
    this.dirty = true;
  }

  /** QA only: hold the cascade at `t` seconds. */
  freeze(t: number) {
    this.finish(false);
    this.mode = "cascade";
    this.frozen = t;
    this.clock = t;
    this.dirty = true;
  }

  get duration() {
    return this.total;
  }

  /**
   * The clip is HDR (BT.2020, HLG): every browser and display tone-maps it its own way, while the
   * pieces were colour-matched to the frame as extracted. Compare the paused hero frame as THIS
   * browser draws it with that extracted frame, fit a per-channel gain + offset, and apply it to
   * the pieces, so they sit in the light that is actually on screen.
   */
  matchVideo(video: HTMLVideoElement, plate: HTMLImageElement) {
    const w = 160;
    const h = 90;
    const read = (src: CanvasImageSource) => {
      const c = document.createElement("canvas");
      c.width = w;
      c.height = h;
      const ctx = c.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(src, 0, 0, w, h);
      return ctx.getImageData(0, 0, w, h).data;
    };
    let a: Uint8ClampedArray;
    let b: Uint8ClampedArray;
    try {
      a = read(plate);
      b = read(video);
    } catch {
      return;
    }
    const gain: number[] = [];
    const offset: number[] = [];
    for (let ch = 0; ch < 3; ch++) {
      let keep = Array.from({ length: w * h }, (_, i) => i);
      let g = 1;
      let o = 0;
      for (let pass = 0; pass < 3; pass++) {
        let sx = 0, sy = 0, sxx = 0, sxy = 0;
        for (const i of keep) {
          const x = a[i * 4 + ch] / 255;
          const y = b[i * 4 + ch] / 255;
          sx += x; sy += y; sxx += x * x; sxy += x * y;
        }
        const n = keep.length;
        const den = n * sxx - sx * sx;
        if (n < 50 || Math.abs(den) < 1e-9) break;
        g = (n * sxy - sx * sy) / den;
        o = (sy - g * sx) / n;
        const res = keep.map((i) => Math.abs(g * (a[i * 4 + ch] / 255) + o - b[i * 4 + ch] / 255));
        const cut = [...res].sort((p, q) => p - q)[Math.floor(res.length * 0.75)];
        keep = keep.filter((_, k) => res[k] <= cut);
      }
      gain.push(Math.min(1.5, Math.max(0.6, g)));
      offset.push(Math.min(0.15, Math.max(-0.15, o)));
    }
    this.gain.set(gain[0], gain[1], gain[2]);
    this.offset.set(offset[0], offset[1], offset[2]);
    this.colourFit = { gain: gain.map((v) => +v.toFixed(3)), offset: offset.map((v) => +v.toFixed(3)), pixels: w * h };
    this.dirty = true;
  }

  /** Pose and draw now (QA snapshots read the canvas in the same task). */
  renderNow() {
    this.pose();
    this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    this.finish(false);
    this.clearItems();
    this.blobTex.dispose();
    this.renderer.dispose();
  }

  // --- geometry -------------------------------------------------------------------------

  private ray(u: number, v: number) {
    const p = new THREE.Vector3(u * 2 - 1, 1 - v * 2, 0.5).unproject(this.camera);
    return new THREE.Ray(this.camera.position.clone(), p.sub(this.camera.position).normalize());
  }

  private onFloor(u: number, v: number) {
    return this.ray(u, v).intersectPlane(this.floor, new THREE.Vector3());
  }

  /** A (cols+1) x (rows+1) grid over an image rect; `place` puts each vertex in the room. */
  private grid(rect: Rect, cols: number, rows: number, place: (u: number, v: number) => THREE.Vector3, pivot: THREE.Vector3) {
    const [x1, y1, x2, y2] = rect;
    const rest = new Float32Array((cols + 1) * (rows + 1) * 3);
    const pos = new Float32Array(rest.length);
    let k = 0;
    for (let j = 0; j <= rows; j++)
      for (let i = 0; i <= cols; i++) {
        const p = place(x1 + ((x2 - x1) * i) / cols, y1 + ((y2 - y1) * j) / rows);
        rest.set([p.x, p.y, p.z], k);
        pos.set([p.x - pivot.x, p.y - pivot.y, p.z - pivot.z], k);
        k += 3;
      }
    const index: number[] = [];
    for (let j = 0; j < rows; j++)
      for (let i = 0; i < cols; i++) {
        const a = j * (cols + 1) + i;
        index.push(a, a + cols + 1, a + 1, a + 1, a + cols + 1, a + cols + 2);
      }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("restPosition", new THREE.BufferAttribute(rest, 3));
    g.setIndex(index);
    return { geometry: g, rest };
  }

  private floorGrid(rect: Rect, cols: number, rows: number, pivot: THREE.Vector3) {
    const fallback = new THREE.Vector3();
    return this.grid(rect, cols, rows, (u, v) => this.onFloor(u, Math.max(v, 0.52)) ?? fallback, pivot);
  }

  private material(tex: THREE.Texture, rect: Rect, colour = true) {
    return new THREE.ShaderMaterial({
      uniforms: {
        map: { value: tex },
        rect: { value: new THREE.Vector4(...rect) },
        restViewProj: { value: this.restViewProj },
        ceiling: { value: this.cal.ceiling_m },
        feather: { value: 0.06 },
        opacity: { value: 1 },
        gain: { value: this.gain },
        offset: { value: this.offset },
        fix: { value: colour ? 1 : 0 },
        foot: { value: [new THREE.Vector4(), new THREE.Vector4(), new THREE.Vector4(), new THREE.Vector4()] },
        reveal: { value: [1, 1, 1, 1] },
        plain: { value: new THREE.Vector3(1, 1, 1) },
      },
      vertexShader: VERT,
      fragmentShader: FRAG,
      transparent: true,
      premultipliedAlpha: true,
      depthTest: false,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
  }

  private blob(order: number) {
    const mat = new THREE.MeshBasicMaterial({
      map: this.blobTex,
      color: 0x000000,
      transparent: true,
      premultipliedAlpha: true,
      depthTest: false,
      depthWrite: false,
      opacity: 0,
    });
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), mat);
    mesh.renderOrder = order;
    mesh.visible = false;
    this.scene.add(mesh);
    return mesh;
  }

  private buildRug(piece: Piece, tex: THREE.Texture, footprints: THREE.Vector4[], palette: string): Item {
    const [x1, , x2, y2] = piece.rect;
    const center = this.onFloor((x1 + x2) / 2, Math.max(0.52, (piece.rect[1] + y2) / 2)) ?? new THREE.Vector3();
    center.y = 0;
    const { geometry, rest } = this.floorGrid(piece.rect, 64, 40, center);
    const mat = this.material(tex, piece.rect);
    footprints.forEach((f, i) => ((mat.uniforms.foot.value as THREE.Vector4[])[i].copy(f)));
    mat.uniforms.reveal.value = footprints.map(() => 0).concat([1, 1, 1, 1]).slice(0, 4);
    // Raw staged sRGB values, like the textures: no colour-space conversion,
    // so the plain weave sits at the rug's own tone before the colour fit.
    const hex = parseInt(palette.slice(1), 16);
    mat.uniforms.plain.value = new THREE.Vector3(((hex >> 16) & 255) / 255, ((hex >> 8) & 255) / 255, (hex & 255) / 255);
    const mesh = new THREE.Mesh(geometry, mat);
    mesh.renderOrder = 0;
    mesh.position.copy(center);
    mesh.visible = false;
    this.scene.add(mesh);
    let hx = 0;
    let hz = 0;
    for (let k = 0; k < rest.length; k += 3) {
      hx = Math.max(hx, Math.abs(rest[k] - center.x));
      hz = Math.max(hz, Math.abs(rest[k + 2] - center.z));
    }
    return {
      piece, mesh, pivot: center, top: 0, start: 0, dur: TIMING.rug, sign: 1,
      axis: new THREE.Vector3(1, 0, 0), blob: this.blob(-1), blobSize: [hx * 1.6, hz * 1.6],
      rug: { rest, half: [hx, hz] },
    };
  }

  private buildUpright(piece: Piece, tex: THREE.Texture, shadowTex: THREE.Texture | null, n: number, start: number, order: string[]): Item {
    const box = piece.box;
    const contacts = (piece.base?.length ? piece.base : [[box[0], box[3]], [box[2], box[3]]])
      .map(([u, v]) => this.onFloor(u, v))
      .filter((p): p is THREE.Vector3 => !!p);
    // The floor-contact line, by PCA: the card stands on it.
    const mx = contacts.reduce((s, p) => s + p.x, 0) / contacts.length;
    const mz = contacts.reduce((s, p) => s + p.z, 0) / contacts.length;
    let sxx = 0, sxz = 0, szz = 0;
    for (const p of contacts) {
      sxx += (p.x - mx) ** 2;
      sxz += (p.x - mx) * (p.z - mz);
      szz += (p.z - mz) ** 2;
    }
    const angle = 0.5 * Math.atan2(2 * sxz, sxx - szz);
    const axis = new THREE.Vector3(Math.cos(angle), 0, Math.sin(angle));
    const pivot = new THREE.Vector3(mx, 0, mz);
    const toCam = new THREE.Vector3(this.camera.position.x - mx, 0, this.camera.position.z - mz).normalize();
    const facing = new THREE.Plane().setFromNormalAndCoplanarPoint(toCam, pivot);
    // The card turns along its floor-contact line, but only part way: a fully oblique card
    // seen from below, high in its fall, reads as a thin slab rather than the piece.
    const side = new THREE.Vector3(-axis.z, 0, axis.x);
    if (side.dot(toCam) < 0) side.negate();
    const normal = side.lerp(toCam, CARD_FACING).normalize();
    axis.set(normal.z, 0, -normal.x);
    const card = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, pivot);
    const cam = this.camera.position;
    const { geometry, rest } = this.grid(piece.rect, 40, 28, (u, v) => {
      const r = this.ray(u, v);
      const p = r.intersectPlane(card, new THREE.Vector3());
      return p && p.distanceTo(cam) < 40 ? p : (r.intersectPlane(facing, new THREE.Vector3()) ?? pivot.clone());
    }, pivot);
    let top = 0;
    let along = 0;
    for (let k = 0; k < rest.length; k += 3) {
      top = Math.max(top, rest[k + 1]);
      along = Math.max(along, Math.abs((rest[k] - mx) * axis.x + (rest[k + 2] - mz) * axis.z));
    }
    const mesh = new THREE.Mesh(geometry, this.material(tex, piece.rect));
    mesh.renderOrder = 10 + Math.max(0, order.indexOf(piece.id));
    mesh.position.copy(pivot);
    mesh.visible = false;
    this.scene.add(mesh);
    let shadow: THREE.Mesh | undefined;
    if (piece.shadow && shadowTex) {
      const { geometry: sg } = this.floorGrid(piece.shadow.rect, 40, 20, new THREE.Vector3());
      shadow = new THREE.Mesh(sg, this.material(shadowTex, piece.shadow.rect, false));
      shadow.renderOrder = 5;
      shadow.visible = false;
      this.scene.add(shadow);
    }
    const width = Math.max(0.4, along * 2);
    return {
      piece, mesh, pivot, top, start, dur: TIMING.upright, sign: n % 2 ? -1 : 1, axis, shadow,
      blob: this.blob(4), blobSize: [width * 1.05, Math.min(1.1, Math.max(0.45, width * 0.45))],
    };
  }

  private clearItems() {
    for (const it of this.items) {
      for (const m of [it.mesh, it.shadow, it.blob]) {
        if (!m) continue;
        this.scene.remove(m);
        m.geometry.dispose();
        (m.material as THREE.Material).dispose();
      }
    }
    this.textures.forEach((t) => t.dispose());
    this.textures = [];
    this.items = [];
  }

  // --- motion ---------------------------------------------------------------------------

  private finish(done: boolean) {
    const settle = this.settle;
    this.settle = null;
    settle?.(done);
  }

  private frame = (now: number) => {
    this.raf = requestAnimationFrame(this.frame);
    const dt = this.last ? Math.min(0.05, (now - this.last) / 1000) : 0;
    this.last = now;
    const moving = (this.mode === "cascade" && this.frozen === null) || this.mode === "lift";
    if (moving) {
      this.clock += dt;
      if (this.mode === "cascade" && this.clock >= this.total) {
        this.mode = "landed";
        this.finish(true);
      } else if (this.mode === "lift" && this.clock >= this.liftTotal()) {
        this.mode = "empty";
        this.finish(true);
      }
    }
    if (moving || this.dirty) {
      this.pose();
      this.renderer.render(this.scene, this.camera);
      this.dirty = false;
    }
  };

  private liftTotal() {
    return TIMING.lift + TIMING.liftStagger * Math.max(0, this.items.length - 1);
  }

  /** Progress p of one piece: <= 0 above the ceiling (hidden), 1 = landed and settled. */
  private progress(it: Item, k: number) {
    if (this.mode === "empty") return -1;
    if (this.mode === "cascade") return (this.clock - it.start) / it.dur;
    if (this.mode === "lift") {
      // Reverse, last in first out: the fall run backwards from where the piece was.
      const from = this.liftFrom[k] ?? -1;
      const local = clamp01((this.clock - (this.items.length - 1 - k) * TIMING.liftStagger) / TIMING.lift);
      return from <= 0 || local >= 1 ? -1 : from * (1 - LIFT(local));
    }
    return 1;
  }

  private pose() {
    // A footprint stays plain weave until its piece settles, then the staged
    // rug under it is revealed beneath the piece and its own shadow.
    for (const it of this.items) {
      if (!it.rug) continue;
      const reveal = (it.mesh.material as THREE.ShaderMaterial).uniforms.reveal.value as number[];
      this.items.forEach((other, k) => {
        const s = this.footSlot.get(other.piece.id);
        if (s === undefined) return;
        const p = clamp01(this.progress(other, k));
        reveal[s] = clamp01((p - TIMING.contact) / (1 - TIMING.contact));
      });
    }
    this.items.forEach((it, k) => {
      const p = this.progress(it, k);
      const visible = p > 0;
      it.mesh.visible = visible;
      if (it.shadow) it.shadow.visible = visible;
      it.blob.visible = visible;
      if (!visible) return;
      if (it.rug) this.poseRug(it, clamp01(p));
      else this.poseUpright(it, clamp01(p));
    });
  }

  private poseUpright(it: Item, p: number) {
    const contact = TIMING.contact;
    const y0 = this.cal.ceiling_m + it.top + 0.12;
    let y = 0;
    let sy = 1;
    let sxz = 1;
    let swing = 0;
    if (p < contact) {
      const q = p / contact;
      y = y0 * (1 - FALL(q));
      swing = 1 - SETTLE(q);
    } else {
      const q = (p - contact) / (1 - contact);
      const s = Math.sin(Math.PI * q) * (1 - q);
      sy = 1 - 0.022 * s;
      sxz = 1 + 0.011 * s;
    }
    const yaw = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), it.sign * 0.06 * swing);
    const tilt = new THREE.Quaternion().setFromAxisAngle(it.axis, -it.sign * 0.025 * swing);
    it.mesh.position.set(it.pivot.x, y, it.pivot.z);
    it.mesh.quaternion.copy(yaw).multiply(tilt);
    it.mesh.scale.set(sxz, sy, sxz);

    // The floor knows before the piece arrives: a wide faint shadow high up, tight and dark at
    // contact, then the staged contact shadow takes over and the approach shadow leaves.
    const near = 1 - clamp01(y / y0);
    const after = p < contact ? 0 : (p - contact) / (1 - contact);
    if (it.shadow) (it.shadow.material as THREE.ShaderMaterial).uniforms.opacity.value = 0.2 * (1 - clamp01(y / 1.1)) ** 2;
    this.placeBlob(it, near ** 2 * 0.1 * (1 - after), 1 + 1.6 * (1 - near), Math.atan2(-it.axis.z, it.axis.x));
  }

  private poseRug(it: Item, p: number) {
    const rug = it.rug!;
    const touch = TIMING.rugTouch;
    const t = this.clock;
    const [hx, hz] = rug.half;
    let edge = 0;
    let billow = 0;
    let flutter = 0;
    let domeZ = 0;
    let yaw = 0;
    if (p < touch) {
      const q = p / touch;
      edge = (this.cal.ceiling_m + 0.4) * (1 - RUG_FALL(q));
      billow = 0.34 * smooth(0, 0.45, q);
      flutter = 1;
      yaw = 0.06 * (1 - SETTLE(q));
    } else {
      // Edges down first; the trapped air rolls out toward the far edge and the weave lies flat.
      const s = (p - touch) / (1 - touch);
      const decay = (1 - s) ** 2;
      billow = 0.34 * decay;
      flutter = decay;
      domeZ = -0.6 * SETTLE(s);
    }
    const spread = 1 - 0.055 * (billow / 0.34);
    const cos = Math.cos(yaw);
    const sin = Math.sin(yaw);
    const pos = it.mesh.geometry.getAttribute("position") as THREE.BufferAttribute;
    const arr = pos.array as Float32Array;
    const { x: cx, z: cz } = it.pivot;
    for (let k = 0; k < arr.length; k += 3) {
      const rx = rug.rest[k] - cx;
      const rz = rug.rest[k + 2] - cz;
      const nx = rx / hx;
      const nz = rz / hz;
      const d = Math.max(0, 1 - 0.85 * nx * nx - 0.85 * (nz - domeZ) ** 2);
      const dome = d * d * (3 - 2 * d);
      const wave = flutter * (0.045 * Math.sin(nx * 5 + t * 7) + 0.03 * Math.sin(nz * 4.2 - t * 5.5));
      const x = rx * spread;
      const z = rz * spread;
      arr[k] = x * cos - z * sin;
      arr[k + 1] = Math.max(0, edge + billow * dome + wave * (1 - 0.4 * dome));
      arr[k + 2] = x * sin + z * cos;
    }
    pos.needsUpdate = true;
    it.mesh.position.set(cx, 0, cz);
    const height = edge + billow * 0.5;
    this.placeBlob(it, 0.12 * (1 - clamp01(height / 1.6)) ** 2 * (p < touch ? 1 : 1 - (p - touch) / (1 - touch)), 1, 0);
  }

  private placeBlob(it: Item, opacity: number, scale: number, yaw: number) {
    const b = it.blob;
    (b.material as THREE.MeshBasicMaterial).opacity = opacity;
    b.visible = opacity > 0.002;
    b.position.set(it.pivot.x, 0.002, it.pivot.z);
    b.rotation.set(0, yaw, 0);
    b.scale.set(it.blobSize[0] * scale, 1, it.blobSize[1] * scale);
  }
}

function blobTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, "rgba(0,0,0,0.7)");
  g.addColorStop(0.45, "rgba(0,0,0,0.3)");
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}
