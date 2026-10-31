import { useEffect, useRef, useState } from "react";
import type { Plan } from "../residences";

const DEG_PER_MS = 0.06;

/** Floor plan with the viewer's position and view cone. Click and hold to rotate it. */
export default function FloorPlan({ plan, heading, label }: { plan: Plan; heading: number; label: string }) {
  const [rotation, setRotation] = useState(0);
  const frame = useRef(0);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  useEffect(() => setRotation(0), [plan]);

  function hold() {
    let last = performance.now();
    const tick = (now: number) => {
      setRotation((r) => (r + (now - last) * DEG_PER_MS) % 360);
      last = now;
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
  }

  const release = () => cancelAnimationFrame(frame.current);
  const [x, y] = plan.position;
  const labelled = plan.rooms.filter((r) => r.label);

  return (
    <div className="flex items-center gap-6">
      <svg
        viewBox="0 0 200 140"
        role="img"
        aria-label={`${label} floor plan. Click and hold to rotate.`}
        tabIndex={0}
        className="h-32 w-44 cursor-grab touch-none overflow-visible active:cursor-grabbing"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          hold();
        }}
        onPointerUp={release}
        onPointerCancel={release}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
            e.preventDefault();
            setRotation((r) => r + (e.key === "ArrowRight" ? 15 : -15));
          }
        }}
      >
        <defs>
          <radialGradient id="plan-cone" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="scale(40)">
            <stop offset="0" stopColor="#9be6ef" stopOpacity="0.45" />
            <stop offset="1" stopColor="#9be6ef" stopOpacity="0" />
          </radialGradient>
        </defs>
        <g transform={`rotate(${rotation} 100 70)`}>
          {plan.rooms.map((r) => (
            <path
              key={r.id}
              d={r.d}
              fill={r.id === plan.current ? "rgb(155 230 239 / 0.1)" : "none"}
              stroke={r.id === plan.current ? "rgb(155 230 239 / 0.55)" : "rgb(236 229 216 / 0.28)"}
              strokeWidth={0.75}
            />
          ))}
          {plan.details?.map((d) => (
            <path key={d} d={d} fill="none" stroke="rgb(155 230 239 / 0.35)" strokeWidth={0.75} />
          ))}
          <path d={plan.outline} fill="none" stroke="rgb(236 229 216 / 0.7)" strokeWidth={1.2} />
          <g transform={`translate(${x} ${y}) rotate(${heading})`}>
            <path d="M0 0 L-17 -36 A40 40 0 0 1 17 -36 Z" fill="url(#plan-cone)" />
          </g>
          <circle cx={x} cy={y} r={7} fill="rgb(155 230 239 / 0.18)" className="animate-pulse" />
          <circle cx={x} cy={y} r={2.6} fill="#9be6ef" />
        </g>
      </svg>
      <ul className="space-y-3">
        {labelled.map((r) => (
          <li
            key={r.id}
            className={`flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] ${r.id === plan.current ? "text-ice" : "text-ivory/60"}`}
          >
            <span className={`h-px w-5 ${r.id === plan.current ? "bg-ice/70" : "bg-ivory/30"}`} />
            {r.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
