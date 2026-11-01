import { useEffect, useRef, useState } from "react";
import "./guide-avatar.css";

// The supplied soft-noise sphere, driven by guide text states rather than microphone audio.
const vertexShader = `
uniform float u_time; uniform float u_audioIntensity; varying vec3 vNormal;
vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x,289.0);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
 const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
 vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
 vec3 g=step(x0.yzx,x0.xyz),l=1.0-g; vec3 i1=min(g.xyz,l.zxy),i2=max(g.xyz,l.zxy);
 vec3 x1=x0-i1+C.xxx,x2=x0-i2+C.yyy,x3=x0-D.yyy; i=mod(i,289.0);
 vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
 vec3 ns=(1.0/7.0)*D.wyz-D.xzx; vec4 j=p-49.0*floor(p*ns.z*ns.z);
 vec4 x_=floor(j*ns.z),y_=floor(j-7.0*x_); vec4 x=x_*ns.x+ns.yyyy,y=y_*ns.x+ns.yyyy,h=1.0-abs(x)-abs(y);
 vec4 b0=vec4(x.xy,y.xy),b1=vec4(x.zw,y.zw),s0=floor(b0)*2.0+1.0,s1=floor(b1)*2.0+1.0,sh=-step(h,vec4(0.0));
 vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy,a1=b1.xzyw+s1.xzyw*sh.zzww;
 vec3 p0=vec3(a0.xy,h.x),p1=vec3(a0.zw,h.y),p2=vec3(a1.xy,h.z),p3=vec3(a1.zw,h.w);
 vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3))); p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
 vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m*=m;
 return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
void main(){vNormal=normal;float noise=snoise(position*1.2+u_time*0.4)*0.18;vec3 p=position+normal*noise*(1.0+u_audioIntensity*4.5);gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);}`;
const fragmentShader = `
varying vec3 vNormal;
void main(){float glow=pow(1.0-dot(vNormal,vec3(0.0,0.0,1.0)),3.0);float shading=dot(vNormal,vec3(0.3,0.5,1.0))*0.5+0.5;vec3 color=mix(vec3(0.85),vec3(0.98,0.96,0.92),shading)+vec3(glow*0.25);gl_FragColor=vec4(color,0.45);}`;

type Props = { state?: "idle" | "thinking" | "speaking" | "nod"; excited?: boolean; large?: boolean };
export default function GuideAvatar({ state = "idle", excited = false, large = false }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const activity = useRef({ state, excited });
  activity.current = { state, excited };
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    let cancelled = false;
    let dispose = () => {};
    void import("three").then(THREE => {
      if (cancelled) return;
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(45, 1, .1, 100);
      camera.position.z = 6;
      const geometry = new THREE.SphereGeometry(1.4, 64, 64);
      const material = new THREE.ShaderMaterial({ vertexShader, fragmentShader, uniforms: { u_time: { value: 0 }, u_audioIntensity: { value: 0 } }, transparent: true, depthWrite: false });
      const mesh = new THREE.Mesh(geometry, material);
      scene.add(mesh);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      element.appendChild(renderer.domElement);
      const resize = () => { const w = element.clientWidth || 1, h = element.clientHeight || 1; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); };
      resize();
      const observer = new ResizeObserver(resize);
      observer.observe(element);
      const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
      let raf = 0;
      const render = (ms: number) => {
        const t = ms / 1000;
        const { state: current, excited: bright } = activity.current;
        const intensity = motion.matches ? 0 : current === "speaking" ? .12 + .12 * Math.abs(Math.sin(t * 7)) : current === "thinking" || current === "nod" || bright ? .12 : .04;
        material.uniforms.u_time.value = motion.matches ? 0 : t;
        material.uniforms.u_audioIntensity.value += (intensity - material.uniforms.u_audioIntensity.value) * .1;
        mesh.rotation.set(motion.matches ? 0 : t * .04, motion.matches ? 0 : t * .08, 0);
        renderer.render(scene, camera);
        raf = requestAnimationFrame(render);
      };
      const onLost = (event: Event) => { event.preventDefault(); cancelAnimationFrame(raf); setReady(false); };
      renderer.domElement.addEventListener("webglcontextlost", onLost);
      dispose = () => { cancelAnimationFrame(raf); observer.disconnect(); renderer.domElement.removeEventListener("webglcontextlost", onLost); geometry.dispose(); material.dispose(); renderer.dispose(); renderer.domElement.remove(); };
      raf = requestAnimationFrame(render);
      setReady(true);
    }).catch(() => { if (!cancelled) setReady(false); });
    return () => { cancelled = true; dispose(); };
  }, []);
  return (
    <div ref={container} role="img" aria-label="Cream cloud-like guide bubble" className={`guide-avatar${ready ? " guide-avatar--shader" : ""} guide-avatar--${state}${excited ? " guide-avatar--excited" : ""}${large ? " guide-avatar--large" : ""}`}>
      <span className="guide-avatar__cloud guide-avatar__cloud--one" />
      <span className="guide-avatar__cloud guide-avatar__cloud--two" />
      <span className="guide-avatar__cloud guide-avatar__cloud--three" />
    </div>
  );
}
