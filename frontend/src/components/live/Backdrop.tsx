import { useEffect, useRef, useState } from "react";
import { media } from "../../api";
import { preload } from "./stage";

type Layer = { id: number; src: string; on: boolean };

/** What fills the screen around a room that is shown whole: the same picture, blurred and dimmed. */
export default function Backdrop({ path }: { path: string | null }) {
  const [layers, setLayers] = useState<Layer[]>([]);
  const last = useRef<string | null>(null);
  const counter = useRef(0);

  useEffect(() => {
    if (!path || path === last.current) return;
    const first = last.current === null;
    last.current = path;
    const id = ++counter.current;
    void preload(path).then(() => {
      setLayers((l) => [...l, { id, src: media(path), on: first }]);
      if (!first)
        requestAnimationFrame(() =>
          requestAnimationFrame(() => setLayers((l) => l.map((x) => (x.id === id ? { ...x, on: true } : x)))),
        );
      setTimeout(() => setLayers((l) => l.filter((x) => x.id >= id)), 1800);
    });
  }, [path]);

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden bg-night">
      <div className="absolute inset-0" style={{ filter: "blur(48px) brightness(0.4)", transform: "scale(1.15)" }}>
        {layers.map((l) => (
          <img
            key={l.id}
            src={l.src}
            alt=""
            draggable={false}
            className="absolute inset-0 h-full w-full object-cover"
            style={{ opacity: l.on ? 1 : 0, transition: "opacity 1200ms ease-in-out" }}
          />
        ))}
      </div>
    </div>
  );
}
