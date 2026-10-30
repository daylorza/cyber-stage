import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { media, type LiveRoom } from "../../api";
import { cutout, maskMinusOvals, usable, type Cut } from "./cutout";
import { sketch } from "./sketch";
import { featherMask, IDENTITY, inFront, ovalOf, pieceMask, placed, planPieces, preload } from "./stage";

export type StagePhase = "empty" | "staged";
export type Overlay = { src: string | null; on: boolean };

type Props = {
  room: LiveRoom;
  /** The style to show. Changing it restyles the room in place. */
  styleId: string | null;
  /** Show the staged room straight away, with no cascade. */
  instant: boolean;
  reduced: boolean;
  /** Length of the empty-room beat before the first cascade (shorter when walking in from the video). */
  beat?: number;
  onReady: () => void;
  onPhase: (phase: StagePhase) => void;
  overlay: Overlay;
  children?: ReactNode;
};

const FIRST_HOLD = 2200;
const RESTYLE_HOLD = 220;
/** Sketch -> finished opening: the room sits as a pencil sketch, then fills stage by stage. */
const SKETCH_FADE = 600;
const SKETCH_HOLD = 1500;
const SKETCH_HOLD_MAIN = 2600;
/** Walls/wood fill (sketch lifts to the filmed room) and shelving/artwork fill. */
const SHELL_MS = 1150;
const DECOR_MS = 1050;
/** One fall, ceiling to floor, including the landing squash and settle. */
const FALL_MS = 1150;
/** Where in the fall the piece touches the floor. */
const CONTACT = 0.78;
const STAGGER = 320;
const RUG_MS = 950;
const SETTLE_MS = 750;
// Gravity: slow off the ceiling, fastest at the floor.
const GRAVITY = "cubic-bezier(0.55, 0, 0.9, 0.5)";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const frames = () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));

const maskStyle = (url: string | null): CSSProperties =>
  url
    ? {
        maskImage: `url(${url})`,
        WebkitMaskImage: `url(${url})`,
        maskSize: "100% 100%",
        WebkitMaskSize: "100% 100%",
        maskRepeat: "no-repeat",
        WebkitMaskRepeat: "no-repeat",
      }
    : {};

/** The furniture mask (or everything), minus the ovals of the pieces in front. */
const pieceInnerMask = (url: string | null, fronts: string[]): CSSProperties => {
  if (!fronts.length) return maskStyle(url);
  const layers = [url ? `url(${url})` : "linear-gradient(#000, #000)", ...fronts].join(", ");
  const rest = fronts.map(() => "add");
  return {
    maskImage: layers,
    WebkitMaskImage: layers,
    maskSize: "100% 100%",
    WebkitMaskSize: "100% 100%",
    maskRepeat: "no-repeat",
    WebkitMaskRepeat: "no-repeat",
    maskComposite: ["subtract", ...rest].join(", "),
    WebkitMaskComposite: ["source-out", ...rest.map(() => "source-over")].join(", "),
  };
};

/**
 * One room. Starts on the empty plate (the filmed frame), then each piece of the chosen style falls from
 * the ceiling and lands with weight: contact shadow growing under it as it nears the floor, a small squash on
 * impact, a settle. The rug unrolls. Only what the furniture mask covers ever appears, so walls, windows and
 * floor stay the filmed room; at the end the masked remainder (art, curtains, small decor) settles in.
 * Generated images are aligned to the filmed frame (style.align) and boxes are percentages of this element.
 */
export default function RoomStage({ room, styleId, instant, reduced, beat = FIRST_HOLD, onReady, onPhase, overlay, children }: Props) {
  const [shown, setShown] = useState<string | null>(null);
  const [cut, setCut] = useState<Cut | null>(null);
  const [sketchUrl, setSketchUrl] = useState<string | null>(null);
  const [decorMask, setDecorMask] = useState<string | null>(null);
  const shownRef = useRef<string | null>(null);
  const started = useRef(false);
  const layer = useRef<HTMLDivElement>(null);
  const callbacks = useRef({ onReady, onPhase });
  callbacks.current = { onReady, onPhase };

  const base = room.plate ?? room.before;
  const style = shown ? room.styles[shown] : undefined;
  const align = style?.align ?? IDENTITY;
  const items = useMemo(() => planPieces(style?.pieces ?? [], style?.align ?? IDENTITY), [style]);
  // Server mask: aligned and cleaned. Without one (older preparations), the in-browser difference cut.
  const maskUrl = style?.mask ? media(style.mask) : cut ? cut.url : null;

  useEffect(() => {
    let cancelled = false;
    const target = styleId ? room.styles[styleId] : undefined;
    const stagedPath = target && target.available ? target.image : null;
    const setShownStyle = (id: string | null) => {
      shownRef.current = id;
      setShown(id);
    };

    (async () => {
      const ready = Promise.all([preload(base), preload(stagedPath), preload(target?.mask)]);
      const cutting = target?.mask ? Promise.resolve(null) : cutout(base, stagedPath);
      const drawing = sketch(stagedPath);
      const first = !started.current;

      if (first) {
        await Promise.race([ready, sleep(6000)]);
        if (cancelled) return;
        started.current = true;
        callbacks.current.onReady();
      } else if (shownRef.current) {
        callbacks.current.onPhase("empty");
        await lift();
        if (cancelled) return;
        await ready;
        if (cancelled) return;
        setShownStyle(null);
        await frames();
      } else {
        await ready;
      }
      if (cancelled) return;

      if (!stagedPath || !styleId) {
        setShownStyle(null);
        callbacks.current.onPhase("empty");
        return;
      }

      if (reduced || (first && instant) || !base) {
        setCut(null);
        setShownStyle(styleId);
        await frames();
        if (cancelled) return;
        settleNow();
        callbacks.current.onPhase("staged");
        return;
      }

      // The empty-room beat. A missing server mask is cut in the browser meanwhile; go without it if slow.
      await sleep(first ? beat : RESTYLE_HOLD);
      if (cancelled) return;
      const mask = await Promise.race([cutting, sleep(300).then(() => null)]);
      if (cancelled) return;

      const hasMask = !!target?.mask || !!mask;
      setCut(mask);
      setShownStyle(styleId);
      await frames();
      if (cancelled) return;

      const root = layer.current;
      const rest = root?.querySelector<HTMLElement>("[data-rest]");
      const pieces = root ? Array.from(root.querySelectorAll<HTMLElement>("[data-piece]")) : [];

      // Sketch -> finished opening (first arrival only, while a furniture mask exists):
      // the room sits as a pencil sketch, the walls/wood fill with colour, shelving and
      // artwork fill in (the staged image where the mask has no furniture piece), THEN the
      // cascade drops the pieces. The sketch is the opening; the drop is still the main act.
      if (first && hasMask && pieces.length > 0) {
        const drawn = await Promise.race([drawing, sleep(1400).then(() => null)]);
        if (cancelled) return;
        if (drawn) {
          setDecorMask(
            await maskMinusOvals(
              maskUrl,
              items.map((i) => [i.x1, i.y1, i.x2, i.y2]),
            ),
          );
          setSketchUrl(drawn);
          await frames();
          if (cancelled) return;
          const paper = root?.querySelector<HTMLElement>("[data-sketch]");
          const decor = root?.querySelector<HTMLElement>("[data-decor]");
          paper?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: SKETCH_FADE, fill: "forwards" });
          await sleep(SKETCH_FADE + (room.main ? SKETCH_HOLD_MAIN : SKETCH_HOLD));
          if (cancelled) return;
          paper?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: SHELL_MS, easing: "ease-in-out", fill: "forwards" });
          await sleep(SHELL_MS);
          if (cancelled) return;
          decor?.animate(
            [
              { clipPath: "inset(0 0 100% 0)", opacity: 0.4 },
              { clipPath: "inset(0 0 0% 0)", opacity: 1 },
            ],
            { duration: DECOR_MS, easing: "cubic-bezier(0.5, 0, 0.2, 1)", fill: "forwards" },
          );
          await sleep(DECOR_MS + 120);
          if (cancelled) return;
        }
      }

      if (pieces.length === 0) {
        callbacks.current.onPhase("staged");
        rest?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 1600, easing: "ease-in-out", fill: "forwards" });
        return;
      }

      let at = 0;
      let landed = 0;
      pieces.forEach((el) => {
        const shadow = root?.querySelector<HTMLElement>(`[data-shadow="${el.dataset.key}"]`);
        if (el.dataset.flat === "1") {
          // A rug unrolls across the floor instead of dropping like a slab.
          el.animate(
            [
              { clipPath: "inset(0 100% 0 0)", opacity: 0, transform: "translate3d(0, -1.5%, 0)" },
              { opacity: 1, offset: 0.12 },
              { clipPath: "inset(0 0% 0 0)", opacity: 1, transform: "translate3d(0, 0, 0)" },
            ],
            { duration: RUG_MS, delay: at, easing: "cubic-bezier(0.45, 0, 0.2, 1)", fill: "both" },
          );
          landed = Math.max(landed, at + RUG_MS);
          at += STAGGER;
          return;
        }
        const drop = Number(el.dataset.drop ?? 120);
        el.animate(
          [
            { transform: `translate3d(0, -${drop}%, 0) scale(0.99, 1.025)`, opacity: 1, offset: 0, easing: GRAVITY },
            { transform: "translate3d(0, 0, 0) scale(1.014, 0.972)", offset: CONTACT, easing: "cubic-bezier(0.2, 0.6, 0.35, 1)" },
            { transform: "translate3d(0, -0.8%, 0) scale(0.996, 1.006)", offset: 0.9, easing: "cubic-bezier(0.4, 0, 0.6, 1)" },
            { transform: "translate3d(0, 0, 0) scale(1, 1)", opacity: 1, offset: 1 },
          ],
          { duration: FALL_MS, delay: at, fill: "both" },
        );
        // The floor shadow is there before the piece is: faint and wide-spread high up, dark and tight at contact.
        shadow?.animate(
          [
            { opacity: 0, transform: "scale(0.45, 0.6)", offset: 0 },
            { opacity: 0.25, transform: "scale(0.7, 0.75)", offset: CONTACT * 0.6, easing: GRAVITY },
            { opacity: 1, transform: "scale(1.04, 1)", offset: CONTACT },
            { opacity: 0.92, transform: "scale(1, 1)", offset: 1 },
          ],
          { duration: FALL_MS, delay: at, easing: "linear", fill: "both" },
        );
        landed = Math.max(landed, at + FALL_MS);
        at += STAGGER;
      });
      await sleep(landed + 80);
      if (cancelled) return;
      // What the boxes missed (art, curtains, small decor) settles in, masked: the room itself never changes.
      rest?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: SETTLE_MS, easing: "cubic-bezier(0.4, 0, 0.2, 1)", fill: "forwards" });
      await sleep(SETTLE_MS * 0.6);
      if (cancelled) return;
      callbacks.current.onPhase("staged");
    })();

    function settleNow() {
      const root = layer.current;
      root?.querySelector("[data-decor]")?.animate([{ opacity: 1 }], { duration: 1, fill: "forwards" });
      root?.querySelector("[data-rest]")?.animate([{ opacity: 1 }], { duration: 1, fill: "forwards" });
      root?.querySelectorAll("[data-piece],[data-shadow]").forEach((el) => el.animate([{ opacity: 1 }], { duration: 1, fill: "forwards" }));
    }

    /** Lift the current pieces back up to the ceiling and clear to the plate. */
    async function lift() {
      const root = layer.current;
      if (!root) return;
      const pieces = Array.from(root.querySelectorAll<HTMLElement>("[data-piece]"));
      const shadows = Array.from(root.querySelectorAll<HTMLElement>("[data-shadow]"));
      const rest = root.querySelector("[data-rest]");
      if (reduced) return;
      rest?.animate([{ opacity: 0 }], { duration: 280, easing: "ease-out", fill: "forwards" });
      await sleep(160);
      pieces.reverse().forEach((el, i) => {
        const drop = Number(el.dataset.drop ?? 120);
        el.animate([{ transform: `translate3d(0, -${drop}%, 0) scale(0.99, 1.03)` }], {
          duration: 520,
          delay: i * 45,
          easing: "cubic-bezier(0.5, 0, 0.75, 0.2)",
          fill: "forwards",
        });
      });
      shadows.forEach((el) => el.animate([{ opacity: 0, transform: "scale(0.5, 0.6)" }], { duration: 380, fill: "forwards" }));
      await sleep(520 + pieces.length * 45 + 60);
    }

    return () => {
      cancelled = true;
    };
    // The room never changes for a mounted stage; only the style does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleId, room.id]);

  return (
    <div role="img" aria-label={room.name} className="relative h-full w-full overflow-hidden bg-smoke">
      {base && (
        <img
          src={media(base)}
          alt=""
          draggable={false}
          className="absolute max-w-none select-none"
          style={placed(room.plate_source === "generated" ? room.plate_align : IDENTITY)}
        />
      )}

      {shown && style?.image && (
        <div key={shown} ref={layer} className="absolute inset-0">
          {/* Shelving, artwork and decor: the staged image where the mask has no furniture piece.
              Filled during the sketch opening, before the pieces drop. */}
          <div
            data-decor
            className="absolute inset-0"
            style={{ opacity: 0, ...maskStyle(decorMask) }}
          >
            <img src={media(style.image)} alt="" draggable={false} className="absolute max-w-none select-none" style={placed(align)} />
          </div>

          {/* The masked remainder: only where the furniture mask says the staged room differs. */}
          <div data-rest className="absolute inset-0" style={{ opacity: 0, ...maskStyle(maskUrl) }}>
            <img src={media(style.image)} alt="" draggable={false} className="absolute max-w-none select-none" style={placed(align)} />
          </div>

          {items.map((p) =>
            p.flat ? null : (
              <div
                key={`s-${p.key}`}
                data-shadow={p.key}
                className="absolute"
                style={{
                  left: `${p.x1 * 100 + (p.x2 - p.x1) * 6}%`,
                  width: `${(p.x2 - p.x1) * 88}%`,
                  top: `${(p.y2 - 0.04) * 100}%`,
                  height: "5%",
                  opacity: 0,
                  transformOrigin: "50% 60%",
                  background: "radial-gradient(ellipse at 50% 55%, rgb(8 8 10 / 0.55), rgb(8 8 10 / 0.22) 50%, transparent 72%)",
                  filter: "blur(2px)",
                }}
              />
            ),
          )}

          {items.map((p) => {
            const w = p.x2 - p.x1;
            const h = p.y2 - p.y1;
            const masked = !!style.mask || usable(cut, [p.x1, p.y1, p.x2, p.y2]);
            const feather = p.flat ? featherMask(p, !masked) : pieceMask(p);
            return (
              <div
                key={p.key}
                data-piece
                data-key={p.key}
                data-drop={p.drop}
                data-flat={p.flat ? "1" : "0"}
                className="absolute will-change-transform"
                style={{
                  left: `${p.x1 * 100}%`,
                  top: `${p.y1 * 100}%`,
                  width: `${w * 100}%`,
                  height: `${h * 100}%`,
                  opacity: 0,
                  transformOrigin: "50% 100%",
                  maskImage: feather,
                  WebkitMaskImage: feather,
                  ...(p.flat ? { maskComposite: "intersect", WebkitMaskComposite: "source-in" } : {}),
                }}
              >
                {/* A frame-sized window onto the aligned staged image, cut to the furniture mask. */}
                <div
                  className="absolute"
                  style={{
                    width: `${100 / w}%`,
                    height: `${100 / h}%`,
                    left: `${(-p.x1 / w) * 100}%`,
                    top: `${(-p.y1 / h) * 100}%`,
                    ...pieceInnerMask(masked ? maskUrl : null, inFront(p, items).map(ovalOf)),
                  }}
                >
                  <img src={media(style.image!)} alt="" draggable={false} className="absolute max-w-none select-none" style={placed(align)} />
                </div>
              </div>
            );
          })}

          {sketchUrl && (
            <img
              data-sketch
              src={sketchUrl}
              alt=""
              draggable={false}
              className="absolute max-w-none select-none"
              style={{ ...placed(align), opacity: 0 }}
            />
          )}
        </div>
      )}

      {overlay.src && (
        <img
          src={overlay.src}
          alt=""
          draggable={false}
          className="absolute max-w-none select-none"
          style={{ ...placed(align), opacity: overlay.on ? 1 : 0, transition: "opacity 1400ms ease-in-out" }}
        />
      )}

      {children}
    </div>
  );
}
