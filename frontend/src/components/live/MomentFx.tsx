import type { Box } from "./stage";

export type Fx = { bloom: boolean; steam: boolean };
export const NO_FX: Fx = { bloom: false, steam: false };

/** Light and steam laid over the stage, positioned in the stage's own percentages. */
export default function MomentFx({ fx, focus }: { fx: Fx; focus: Box | null }) {
  if (!focus) return null;
  const [x1, y1, x2, y2] = focus;
  const cx = ((x1 + x2) / 2) * 100;
  return (
    <>
      <div
        aria-hidden
        className="pointer-events-none absolute"
        style={{
          left: `${x1 * 100 - 6}%`,
          top: `${y1 * 100 - 8}%`,
          width: `${(x2 - x1) * 100 + 12}%`,
          height: `${(y2 - y1) * 100 + 16}%`,
          background: "radial-gradient(ellipse at 50% 45%, rgb(236 229 216 / 0.5), rgb(155 230 239 / 0.14) 48%, transparent 72%)",
          mixBlendMode: "screen",
          opacity: fx.bloom ? 1 : 0,
          transform: fx.bloom ? "scale(1.05)" : "scale(0.94)",
          transition: "opacity 1400ms ease-in-out, transform 3600ms ease-out",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute"
        style={{ left: `${cx}%`, top: `${y1 * 100 + (y2 - y1) * 22}%`, opacity: fx.steam ? 1 : 0, transition: "opacity 900ms ease-out" }}
      >
        {[
          { dx: "-0.8vmin", delay: "0s", left: "-1.2vmin" },
          { dx: "0.9vmin", delay: "1.1s", left: "0vmin" },
          { dx: "-0.4vmin", delay: "2.1s", left: "1.1vmin" },
        ].map((w) => (
          <span
            key={w.delay}
            className="live-steam absolute rounded-full"
            style={
              {
                left: w.left,
                top: 0,
                width: "1.4vmin",
                height: "7vmin",
                animationDelay: w.delay,
                filter: "blur(0.9vmin)",
                background: "linear-gradient(to top, rgb(236 229 216 / 0.7), rgb(236 229 216 / 0))",
                "--steam-drift": w.dx,
              } as React.CSSProperties
            }
          />
        ))}
      </div>
    </>
  );
}
