import { useEffect, useRef } from "react";
import * as THREE from "three";
import "./guide-avatar.css";

type Props = { state?: "idle" | "thinking" | "speaking" | "nod"; excited?: boolean; large?: boolean };
export default function GuideAvatar({ state = "idle", excited = false, large = false }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const animation = useRef({ state, excited });
  animation.current = { state, excited };
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" }); }
    catch { return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setClearColor(0x000000, 0);
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, .1, 20);
    camera.position.set(0, 0, 7);
    const figure = new THREE.Group();
    scene.add(figure);
    const solid = new THREE.MeshBasicMaterial({ color: 0x20a9ca, transparent: true, opacity: .18, depthWrite: false });
    const wire = new THREE.MeshBasicMaterial({ color: 0x8beeff, transparent: true, opacity: .18, wireframe: true, depthWrite: false });
    const shapes: THREE.BufferGeometry[] = [];
    function form(geometry: THREE.BufferGeometry, x: number, y: number, z: number, sx: number, sy: number, sz: number) {
      shapes.push(geometry);
      for (const material of [solid, wire]) {
        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(x, y, z); mesh.scale.set(sx, sy, sz); figure.add(mesh);
      }
    }
    form(new THREE.SphereGeometry(1, 16, 12), 0, .58, 0, .65, .86, .52); // smooth, featureless head
    form(new THREE.SphereGeometry(1, 16, 12), 0, .67, -.22, .76, .94, .46); // hair silhouette
    form(new THREE.CylinderGeometry(.20, .28, .65, 12, 2), 0, -.38, 0, 1, 1, 1);
    form(new THREE.SphereGeometry(1, 16, 10), 0, -1.06, 0, 1.22, .48, .42);
    const resize = () => { const width = element.clientWidth || 1, height = element.clientHeight || 1; renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix(); };
    resize();
    const observer = new ResizeObserver(resize); observer.observe(element);
    let raf = 0;
    const render = (ms: number) => {
      const t = ms / 1000, current = animation.current;
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const pulse = current.state === 'speaking' ? Math.sin(t * 13) * .025 : Math.sin(t * 2) * .012;
      figure.position.y = reduced ? 0 : Math.sin(t * 1.2) * .035;
      figure.rotation.z = reduced ? 0 : current.state === 'thinking' ? -.12 : Math.sin(t) * .025;
      figure.rotation.x = reduced ? 0 : current.state === 'nod' ? Math.sin(t * 9) * .1 : 0;
      figure.scale.setScalar(reduced ? 1 : 1 + pulse);
      wire.opacity = current.excited || current.state === 'thinking' ? .34 : .18;
      renderer.render(scene, camera); raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);
    return () => { cancelAnimationFrame(raf); observer.disconnect(); shapes.forEach(g => g.dispose()); solid.dispose(); wire.dispose(); renderer.dispose(); renderer.domElement.remove(); };
  }, []);
  return <div ref={container} role="img" aria-label="Faceless blue holographic guide" className={`guide-avatar${large ? ' guide-avatar--large' : ''}`} />;
}
