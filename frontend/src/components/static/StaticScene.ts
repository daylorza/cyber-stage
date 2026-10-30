import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import type { Calibration, Piece } from "../prototype/manifest";

/**
 * Static-image small clip: real 3D furniture over ONE static photo.
 *
 * The camera is the POC hero frame's calibrated camera (vanishing points,
 * same numbers the flat-card cascade uses). Pieces are real 3D models —
 * GLB sofa / chair, procedural stone table and woven rug — placed on the
 * floor plane where SAM 3.1 found the staged pieces, lit by one
 * shadow-casting key light, so shadows are rendered, never baked into a
 * texture. Pieces drop from the ceiling plane; the camera drifts slightly.
 * No video, no cut-out cards.
 */

export const STATIC_ASSETS = {
  photo: "/static-clip/hero.jpg",
  sofa: "/static-clip/sofa.glb",
  chair: "/static-clip/chair.glb",
};

type Item = {
  id: string;
  group: THREE.Group;
  start: number;
  dur: number;
  drop: number;
};

const TIMING = { rug: 0, firstPiece: 0.45, stagger: 0.55, drop: 0.8, hold: 0.9 };

export class StaticScene {
  readonly renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private baseQuat = new THREE.Quaternion();
  private floor = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private items: Item[] = [];
  private clock = 0;
  private playing = false;
  private frozen: number | null = null;
  private last = 0;
  private raf = 0;
  private dirty = true;
  /** Total clip length: last landing + hold. */
  readonly duration: number;

  constructor(canvas: HTMLCanvasElement, private cal: Calibration, aspect: number, private onDone?: () => void) {
    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, premultipliedAlpha: true, preserveDrawingBuffer: true });
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.camera = new THREE.PerspectiveCamera(cal.vfov_deg, aspect, 0.05, 200);
    this.camera.position.set(0, cal.height_m, 0);
    this.camera.rotation.set(-THREE.MathUtils.degToRad(cal.pitch_deg), 0, 0);
    this.camera.updateMatrixWorld();
    this.baseQuat.copy(this.camera.quaternion);

    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

    const hemi = new THREE.HemisphereLight(0xfff2e0, 0x8a7a66, 0.5);
    this.scene.add(hemi);
    // Key light from the filmed windows (back-left in the hero frame).
    const key = new THREE.DirectionalLight(0xffe8c8, 1.7);
    key.position.set(-5, 7, -3);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.left = -7;
    key.shadow.camera.right = 7;
    key.shadow.camera.top = 7;
    key.shadow.camera.bottom = -7;
    key.shadow.camera.near = 1;
    key.shadow.camera.far = 25;
    key.shadow.bias = -0.0004;
    this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xdfe8ff, 0.35);
    fill.position.set(5, 4, 5);
    this.scene.add(fill);

    // Shadow catcher: the photo's own floor, darkened only where a piece lands.
    const catcher = new THREE.Mesh(
      new THREE.PlaneGeometry(40, 40).rotateX(-Math.PI / 2),
      new THREE.ShadowMaterial({ opacity: 0.32 }),
    );
    catcher.position.y = 0.001;
    catcher.receiveShadow = true;
    this.scene.add(catcher);

    this.duration = TIMING.firstPiece + TIMING.stagger * 2 + TIMING.drop + TIMING.hold;
    this.raf = requestAnimationFrame(this.frame);
  }

  resize(width: number, height: number) {
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(width, height, false);
    this.dirty = true;
  }

  private ray(u: number, v: number) {
    const p = new THREE.Vector3(u * 2 - 1, 1 - v * 2, 0.5).unproject(this.camera);
    return new THREE.Ray(this.camera.position.clone(), p.sub(this.camera.position).normalize());
  }

  private onFloor(u: number, v: number) {
    return this.ray(u, v).intersectPlane(this.floor, new THREE.Vector3());
  }

  /** Floor placement from a piece's SAM box: its bottom edge on the floor
   *  gives the centre, the width axis and the width in metres directly. */
  private placement(piece: Piece) {
    const box = piece.box;
    const bl = this.onFloor(box[0], box[3]) ?? new THREE.Vector3();
    const br = this.onFloor(box[2], box[3]) ?? new THREE.Vector3();
    const centre = bl.clone().add(br).multiplyScalar(0.5);
    centre.y = 0;
    const axis = br.clone().sub(bl);
    const width = Math.max(axis.length(), 0.4);
    axis.normalize();
    return { centre, axis, width };
  }

  /** Yaw that puts a model's local +X along `axis` and its front (+Z) toward the camera. */
  private yawFor(axis: THREE.Vector3, centre: THREE.Vector3) {
    let yaw = Math.atan2(-axis.z, axis.x);
    const front = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
    const toCam = new THREE.Vector3(-centre.x, 0, -centre.z).normalize();
    if (front.dot(toCam) < 0) yaw += Math.PI;
    return yaw;
  }

  private finishModel(root: THREE.Object3D, targetWidth: number, tint?: string): THREE.Group {
    const group = new THREE.Group();
    // The model's long axis becomes local X, whatever axis it was authored on.
    const raw = new THREE.Box3().setFromObject(root).getSize(new THREE.Vector3());
    if (raw.z > raw.x) root.rotation.y = Math.PI / 2;
    const bbox = new THREE.Box3().setFromObject(root);
    const size = bbox.getSize(new THREE.Vector3());
    const scale = targetWidth / Math.max(size.x, 0.01);
    root.scale.setScalar(scale);
    const scaled = new THREE.Box3().setFromObject(root);
    const c = scaled.getCenter(new THREE.Vector3());
    // Group origin = the model's front-bottom centre, so the group can sit
    // exactly on the piece's SAM floor-contact line.
    root.position.set(-c.x, -scaled.min.y, -scaled.max.z);
    root.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        o.castShadow = true;
        o.receiveShadow = true;
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        for (const m of mats) {
          const mat = m as THREE.MeshStandardMaterial;
          if (!mat || !("envMapIntensity" in mat)) continue;
          mat.envMapIntensity = 0.55;
          // Recolour fabric to the staged palette (the chair's velvet even
          // declares metallicFactor 1, so judge by name / sheen, not metalness);
          // wood, metal and labels keep their authored finish.
          const fabric = /fabric|velvet/i.test(mat.name) || ((mat as THREE.MeshPhysicalMaterial).sheen ?? 0) > 0;
          if (tint && fabric) {
            mat.color.set(tint);
            // The velvet's sheen layer is tinted separately and would
            // otherwise keep the authored colour (orange on the chair).
            const phys = mat as THREE.MeshPhysicalMaterial;
            if (phys.sheenColor) phys.sheenColor.set(tint);
          }
        }
      }
    });
    group.add(root);
    return group;
  }

  /** Build all pieces for the staged style; nothing is shown until replay(). */
  async build(pieces: Piece[]) {
    const loader = new GLTFLoader();
    const [sofaGlb, chairGlb] = await Promise.all([
      loader.loadAsync(STATIC_ASSETS.sofa),
      loader.loadAsync(STATIC_ASSETS.chair),
    ]);
    let at = TIMING.firstPiece;
    for (const piece of pieces) {
      const { centre, axis, width } = this.placement(piece);
      let group: THREE.Group;
      let start = at;
      if (piece.kind === "rug") {
        group = this.buildRug(piece);
        start = TIMING.rug;
      } else if (piece.id === "sofa") {
        group = this.finishModel(sofaGlb.scene, width, piece.palette);
        at += TIMING.stagger;
      } else if (piece.id === "armchair") {
        group = this.finishModel(chairGlb.scene, Math.max(width, 0.8), piece.palette);
        at += TIMING.stagger;
      } else {
        group = this.buildTable(width);
        at += TIMING.stagger;
      }
      // The rug's geometry is already in floor coordinates; other pieces sit
      // with their front-bottom centre on the SAM contact line.
      if (piece.kind !== "rug") {
        group.position.copy(centre);
        group.rotation.y = this.yawFor(axis, centre);
      }
      group.visible = false;
      this.scene.add(group);
      this.items.push({ id: piece.id, group, start, dur: TIMING.drop, drop: this.cal.ceiling_m + 1.2 });
    }
    this.pose(0);
  }

  private buildRug(piece: Piece): THREE.Group {
    const [x1, y1, x2, y2] = piece.rect;
    // The rug's four corners on the floor plane: a flat quad in floor
    // coordinates, so it follows the photo's perspective exactly (a box
    // centred between the corners spills across the foreground).
    const corners = [
      this.onFloor(x1, y1), this.onFloor(x2, y1),
      this.onFloor(x1, Math.max(y2, 0.52)), this.onFloor(x2, Math.max(y2, 0.52)),
    ];
    const group = new THREE.Group();
    if (corners.some((p) => !p)) return group;
    const [a, b, c, d] = corners as THREE.Vector3[];
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
      a.x, 0.02, a.z, b.x, 0.02, b.z, c.x, 0.02, c.z,
      b.x, 0.02, b.z, d.x, 0.02, d.z, c.x, 0.02, c.z,
    ]), 3));
    geo.setAttribute("uv", new THREE.BufferAttribute(new Float32Array([0, 1, 1, 1, 0, 0, 1, 1, 1, 0, 0, 0]), 2));
    geo.computeVertexNormals();
    const rug = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      map: weaveTexture(piece.palette), roughness: 0.96, metalness: 0, side: THREE.DoubleSide, transparent: true,
    }));
    rug.receiveShadow = true;
    group.add(rug);
    return group;
  }

  private buildTable(width: number): THREE.Group {
    const stone = new THREE.MeshStandardMaterial({ map: stoneTexture(), color: 0xa89478, roughness: 0.42, metalness: 0.02 });
    const group = new THREE.Group();
    const top = new THREE.Mesh(new RoundedBoxGeometry(width, 0.07, width * 0.55, 3, 0.03), stone);
    top.position.y = 0.42;
    group.add(top);
    for (const side of [-1, 1]) {
      const base = new THREE.Mesh(new THREE.CylinderGeometry(width * 0.15, width * 0.17, 0.385, 24), stone);
      base.position.set(side * width * 0.24, 0.1925, 0);
      group.add(base);
    }
    group.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        o.castShadow = true;
        o.receiveShadow = true;
      }
    });
    return group;
  }

  replay() {
    this.clock = 0;
    this.frozen = null;
    this.playing = true;
  }

  freeze(t: number) {
    this.frozen = t;
    this.clock = t;
    this.playing = false;
    this.dirty = true;
  }

  showLanded() {
    this.frozen = this.duration;
    this.clock = this.duration;
    this.playing = false;
    this.dirty = true;
  }

  renderNow() {
    this.pose(this.clock);
    this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    this.renderer.dispose();
  }

  private frame = (now: number) => {
    this.raf = requestAnimationFrame(this.frame);
    const dt = this.last ? Math.min(0.05, (now - this.last) / 1000) : 0;
    this.last = now;
    if (this.playing) {
      this.clock += dt;
      if (this.clock >= this.duration) {
        this.clock = this.duration;
        this.playing = false;
        this.onDone?.();
      }
      this.dirty = true;
    }
    if (this.dirty) {
      this.pose(this.clock);
      this.renderer.render(this.scene, this.camera);
      this.dirty = this.playing;
    }
  };

  private pose(t: number) {
    // Slight camera drift through the clip; still when frozen for stills.
    const drift = this.frozen === null ? t : 0;
    this.camera.position.set(0.055 * Math.sin(drift * 0.55), this.cal.height_m + 0.02 * Math.sin(drift * 0.4), 0);
    this.camera.quaternion.copy(this.baseQuat);
    const sway = new THREE.Quaternion().setFromEuler(new THREE.Euler(0.0035 * Math.sin(drift * 0.5), 0.008 * Math.sin(drift * 0.45), 0));
    this.camera.quaternion.multiply(sway);
    this.camera.updateMatrixWorld();

    for (const it of this.items) {
      const p = (t - it.start) / it.dur;
      if (p <= 0) {
        it.group.visible = false;
        continue;
      }
      it.group.visible = true;
      const q = Math.min(1, p);
      // Accelerating fall, then a short settle: weight, not a bounce.
      const y = it.drop * (1 - q) ** 2.1;
      it.group.position.y = y;
      const settle = q > 0.82 ? Math.sin(((q - 0.82) / 0.18) * Math.PI) * (1 - q) : 0;
      it.group.scale.set(1 + 0.012 * settle, 1 - 0.03 * settle, 1 + 0.012 * settle);
    }
  }
}

function weaveTexture(palette: string): THREE.Texture {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = palette;
  ctx.fillRect(0, 0, 256, 256);
  for (let y = 0; y < 256; y += 2) {
    for (let x = 0; x < 256; x += 4) {
      const v = Math.sin(x * 1.7 + y * 0.6) + Math.sin(y * 2.3) + Math.sin((x + y) * 0.35);
      ctx.fillStyle = v > 0 ? "rgba(70,52,30,0.09)" : "rgba(255,250,235,0.08)";
      ctx.fillRect(x, y, 3, 1.6);
    }
  }
  // Feather the quad's edges in texture space so the rug melts into the
  // filmed floor instead of ending on a hard rectangle edge.
  const fade = ctx.createLinearGradient(0, 0, 0, 256);
  fade.addColorStop(0, "rgba(0,0,0,1)");
  fade.addColorStop(0.05, "rgba(0,0,0,0)");
  fade.addColorStop(0.95, "rgba(0,0,0,0)");
  fade.addColorStop(1, "rgba(0,0,0,1)");
  ctx.globalCompositeOperation = "destination-out";
  ctx.fillStyle = fade;
  ctx.fillRect(0, 0, 256, 256);
  const side = ctx.createLinearGradient(0, 0, 256, 0);
  side.addColorStop(0, "rgba(0,0,0,1)");
  side.addColorStop(0.05, "rgba(0,0,0,0)");
  side.addColorStop(0.95, "rgba(0,0,0,0)");
  side.addColorStop(1, "rgba(0,0,0,1)");
  ctx.fillStyle = side;
  ctx.fillRect(0, 0, 256, 256);
  ctx.globalCompositeOperation = "source-over";
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function stoneTexture(): THREE.Texture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 128;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "#b3a189";
  ctx.fillRect(0, 0, 256, 128);
  for (let i = 0; i < 46; i++) {
    ctx.strokeStyle = `rgba(90,72,50,${0.05 + Math.random() * 0.1})`;
    ctx.lineWidth = 0.6 + Math.random() * 1.6;
    ctx.beginPath();
    const y = Math.random() * 128;
    ctx.moveTo(0, y);
    ctx.bezierCurveTo(80, y + 9 - Math.random() * 18, 170, y + 9 - Math.random() * 18, 256, y);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
