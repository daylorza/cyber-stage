import type { LiveRoom } from "../../api";

/** Image-space SAM detections rendered as a view diagram, not room coordinates. */
export default function RoomSchematic({ room, styleId }: { room?: LiveRoom; styleId: string | null }) {
  const detections = room?.sam_map?.detections ?? [];
  const pieces = styleId ? room?.styles[styleId]?.pieces ?? [] : [];
  return (
    <div className="min-w-0">
      <p className="eyebrow mb-2 text-ivory/80!">Floor plan</p>
      <svg viewBox="0 0 200 140" role="img" aria-label="Estimated room view; furniture positions approximate" className="block h-auto w-full max-w-44">
        <path d="M15 15 H185 V95 H15 Z" className="fill-ice/5 stroke-ivory/65" />
        <path d="M15 95 L0 130 H200 L185 95" className="fill-ice/[0.04] stroke-ivory/40" />
        {detections.map((d, i) => {
          const x = 15 + d.x_center * 170;
          const w = Math.max(5, Math.min(d.width * 170, 50));
          return <g key={`${d.concept}-${i}`}>
            <rect x={Math.max(15, Math.min(185 - w, x - w / 2))} y={d.concept === "door" ? 48 : 35} width={w} height={d.concept === "door" ? 47 : 25} className="fill-ice/20 stroke-ice" />
            <title>{`${d.concept} · ${d.wall} (estimated)`}</title>
          </g>;
        })}
        {pieces.map((piece, i) => {
          const [x1, , x2, y2] = piece.box;
          const align = room?.styles[styleId ?? ""]?.align;
          const x = Math.max(5, Math.min(195, ((x1 + x2) / 2 * (align?.sx ?? 1) + (align?.bx ?? 0)) * 200));
          const y = 98 + Math.max(0, Math.min(1, y2 * (align?.sy ?? 1) + (align?.by ?? 0))) * 26;
          return <circle key={`${piece.concept}-${i}`} cx={x} cy={y} r="2.5" className="fill-champagne-bright"><title>{`${piece.concept} · approximate`}</title></circle>;
        })}
        <path d="M100 130 L88 104 H112 Z" className="fill-ice/25" />
        <circle cx="100" cy="130" r="3" className="fill-ice" />
      </svg>
      <p className="mt-1.5 text-micro leading-snug text-ivory/65">Estimate · not to scale</p>
    </div>
  );
}
