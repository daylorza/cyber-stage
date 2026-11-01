import { useEffect, useState } from "react";
import "./guide-avatar.css";

export default function GuideAvatar({ state = "idle", excited = false, large = false }: { state?: "idle" | "thinking" | "speaking" | "nod"; excited?: boolean; large?: boolean }) {
  const [blink, setBlink] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let timer = 0;
    const schedule = () => { timer = window.setTimeout(() => { setBlink(true); timer = window.setTimeout(() => { setBlink(false); schedule(); }, 120); }, 3000 + Math.random() * 2000); };
    schedule();
    return () => clearTimeout(timer);
  }, []);
  if (failed) return null;
  return <div aria-label="Blue holographic guide head" role="img" className={`guide-avatar guide-avatar--${state}${excited ? " guide-avatar--excited" : ""}${large ? " guide-avatar--large" : ""}`}><img src="/guide-portrait.png" alt="" draggable={false} onError={() => setFailed(true)} className={blink ? "guide-avatar__blink" : ""} /></div>;
}
