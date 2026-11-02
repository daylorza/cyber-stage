import { useLayoutEffect, useRef, useState } from "react";
import type { LiveRoom } from "../../api";
import { styleStatus } from "./stage";

type Props = {
  styles: { id: string; label: string }[];
  room: LiveRoom;
  pressed: string | null;
  onChoose: (id: string) => void;
  /** "bar": the desktop pill, sized like the Finish control. "sheet": the phone row of pills. */
  variant: "bar" | "sheet";
  className?: string;
};

const HOVER_GLOW = "[@media(hover:hover)]:hover:[text-shadow:0_0_12px_rgb(155_230_239/0.55)]";

/** Staging styles with a highlight that slides to the selected one. */
export default function StylePicker({ styles, room, pressed, onChoose, variant, className = "" }: Props) {
  const group = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

  useLayoutEffect(() => {
    const el = pressed ? group.current?.querySelector<HTMLElement>(`[data-style="${pressed}"]`) : null;
    if (!el) return setBox(null);
    const update = () => setBox({ left: el.offsetLeft, top: el.offsetTop, width: el.offsetWidth, height: el.offsetHeight });
    update();
    if (variant === "sheet") el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [pressed, variant]);

  const bar = variant === "bar";
  return (
    <div
      ref={group}
      role="group"
      aria-label="Style"
      className={
        bar
          ? `relative flex items-center gap-1 rounded-full bg-ivory/[0.08] p-1.5 ring-1 ring-ivory/25 backdrop-blur-xl transition duration-300 hover:ring-ivory/40 [@media(hover:hover)]:hover:shadow-[0_0_28px_-6px_rgb(155_230_239/0.4)] ${className}`
          : `relative flex gap-2 overflow-x-auto px-4 py-2 [mask-image:linear-gradient(to_right,#000_82%,transparent)] [scrollbar-width:none] ${className}`
      }
    >
      {box && (
        <span
          aria-hidden
          className="pointer-events-none absolute rounded-full bg-ivory/90 shadow-[0_0_18px_rgb(236_229_216/0.25)] transition-[left,width,top,height] duration-500 ease-[cubic-bezier(0.22,0.7,0.12,1)]"
          style={box}
        />
      )}
      {styles.map((s) => {
        const status = s.id === "original" ? { ok: !!room.before, reason: "Original unavailable" } : styleStatus(room, s.id);
        const active = s.id === pressed;
        const tone = active ? "text-night" : status.ok ? `text-ivory/80 hover:text-ivory ${HOVER_GLOW}` : bar ? "text-ivory/30 line-through decoration-ivory/30" : "text-ivory/85";
        return (
          <button
            key={s.id}
            data-style={s.id}
            type="button"
            disabled={!status.ok}
            title={status.ok ? (bar ? `Restyle as ${s.label}` : undefined) : status.reason}
            aria-pressed={active}
            onClick={() => onChoose(s.id)}
            className={`relative shrink-0 rounded-full tracking-wide transition-colors duration-300 disabled:cursor-not-allowed ${
              bar ? "h-10 px-5 text-ui" : `min-h-11 px-4 text-sm ring-1 disabled:opacity-35 ${active ? "ring-transparent" : "ring-ivory/15"}`
            } ${tone}`}
          >
            {s.label}
          </button>
        );
      })}
    </div>
  );
}
