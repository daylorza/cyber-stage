import type { Plan } from "../residences";

/** Floor plan with the viewer's position and view cone. */
export default function FloorPlan({ plan, heading, label }: { plan: Plan; heading: number; label: string }) {
  const [x, y] = plan.position;
  const labelled = plan.rooms.filter((r) => r.label);

  return (
    <div className="flex items-center gap-6">
      <svg viewBox="0 0 200 140" role="img" aria-label={`${label} floor plan.`} className="h-32 w-44 overflow-visible">
        <defs>
          <radialGradient id="plan-cone" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="scale(40)">
            <stop offset="0" style={{ stopColor: "var(--color-ice)" }} stopOpacity="0.45" />
            <stop offset="1" style={{ stopColor: "var(--color-ice)" }} stopOpacity="0" />
          </radialGradient>
        </defs>
        {plan.rooms.map((r) => (
          <path
            key={r.id}
            d={r.d}
            className={r.id === plan.current ? "fill-ice/10 stroke-ice/55" : "fill-none stroke-ivory/30"}
            strokeWidth={0.75}
          />
        ))}
        {plan.details?.map((d) => (
          <path key={d} d={d} className="fill-none stroke-ice/35" strokeWidth={0.75} />
        ))}
        <path d={plan.outline} className="fill-none stroke-ivory/70" strokeWidth={1.2} />
        <g transform={`translate(${x} ${y}) rotate(${heading})`}>
          <path d="M0 0 L-17 -36 A40 40 0 0 1 17 -36 Z" fill="url(#plan-cone)" />
        </g>
        <circle cx={x} cy={y} r={7} className="animate-pulse fill-ice/20" />
        <circle cx={x} cy={y} r={2.6} className="fill-ice" />
      </svg>
      <ul className="space-y-3">
        {labelled.map((r) => (
          <li
            key={r.id}
            className={`flex items-center gap-3 font-mono text-micro uppercase tracking-[0.2em] ${r.id === plan.current ? "text-ice" : "text-ivory/70"}`}
          >
            <span className={`h-px w-5 ${r.id === plan.current ? "bg-ice/70" : "bg-ivory/30"}`} />
            {r.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
