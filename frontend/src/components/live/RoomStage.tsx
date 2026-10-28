import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { media, type LiveRoom } from "../../api";
import { cutout, usable, type Cut } from "./cutout";
import { featherMask, planPieces, preload } from "./stage";

export type StagePhase = "empty" | "staged";
export type Overlay = { src: string | null; on: boolean };

type Props = {
  room: LiveRoom;
  /** The style to show. Changing it restyles the room in place. */
  styleId: string | null;
  /** Show the staged room straight away, with no cascade. */
  instant: boolean;
  reduced: boolean;
  onReady: () => void;
  onPhase: (phase: StagePhase) => void;
  overlay: Overlay;
  children?: ReactNode;
};

const FIRST_HOLD = 2200;
const RESTYLE_HOLD = 160;
const FALL_MS = 900;
const FADE_MS = 700;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const frames = () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));

/** Fade an element to full opacity and keep it there. */
function reveal(el: Element | null | undefined, ms: number) {
  el?.animate([{ opacity: 1 }], { duration: ms, easing: "cubic-bezier(0.4, 0, 0.2, 1)", fill: "forwards" });
}

/**
 * One room. Starts on the empty plate, then drops each piece of the chosen style into place and
 * fades the full staged image over the top. Boxes are percentages of this element, which the
 * parent sizes to the room's aspect ratio.
 */
export default function RoomStage({ room, styleId, instant, reduced, onReady, onPhase, overlay, children }: Props) {
  const [shown, setShown] = useState<string | null>(null);
  const [cut, setCut] = useState<Cut | null>(null);
  const shownRef = useRef<string | null>(null);
  const started = useRef(false);
  const layer = useRef<HTMLDivElement>(null);
  const callbacks = useRef({ onReady, onPhase });
  callbacks.current = { onReady, onPhase };

  const base = room.plate ?? room.before;
  const style = shown ? room.styles[shown] : undefined;
  const items = useMemo(() => planPieces(style?.pieces ?? []), [style]);

  useEffect(() => {
    let cancelled = false;
    const target = styleId ? room.styles[styleId] : undefined;
    const stagedPath = target && target.available ? target.image : null;
    const setShownStyle = (id: string | null) => {
      shownRef.current = id;
      setShown(id);
    };

    (async () => {
      const ready = Promise.all([preload(base), preload(stagedPath)]);
      // Where the staged image differs from the plate: that is the furniture. Computed alongside the preload.
      const cutting = cutout(base, stagedPath);
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
        reveal(layer.current?.querySelector("[data-full]"), 1);
        callbacks.current.onPhase("staged");
        return;
      }

      // The empty-room beat. The cutout is usually ready by the end of it; wait a little longer, then go without.
      await sleep(first ? FIRST_HOLD : RESTYLE_HOLD);
      if (cancelled) return;
      const mask = await Promise.race([cutting, sleep(300).then(() => null)]);
      if (cancelled) return;

      setCut(mask);
      setShownStyle(styleId);
      await frames();
      if (cancelled) return;

      const root = layer.current;
      const full = root?.querySelector("[data-full]");
      const pieces = root ? Array.from(root.querySelectorAll<HTMLElement>("[data-piece]")) : [];
      const shadows = root ? Array.from(root.querySelectorAll<HTMLElement>("[data-shadow]")) : [];

      if (pieces.length === 0) {
        callbacks.current.onPhase("staged");
        reveal(full, 1800);
        return;
      }

      const stagger = 210;
      pieces.forEach((el, i) => {
        const drop = Number(el.dataset.drop ?? 120);
        el.animate(
          [
            { transform: `translate3d(0, -${drop}%, 0)`, opacity: 0, offset: 0, easing: "cubic-bezier(0.5, 0.05, 0.78, 0.6)" },
            { opacity: 1, offset: 0.14 },
            { transform: "translate3d(0, 1.6%, 0)", opacity: 1, offset: 0.72, easing: "cubic-bezier(0.2, 0.6, 0.3, 1)" },
            { transform: "translate3d(0, 0, 0)", opacity: 1, offset: 1 },
          ],
          { duration: FALL_MS, delay: i * stagger, fill: "both" },
        );
        shadows[i]?.animate([{ opacity: 0 }, { opacity: 1 }], {
          duration: 420,
          delay: i * stagger + FALL_MS * 0.6,
          easing: "ease-out",
          fill: "both",
        });
      });
      await sleep((pieces.length - 1) * stagger + FALL_MS + 120);
      if (cancelled) return;
      callbacks.current.onPhase("staged");
      reveal(full, FADE_MS);
    })();

    /** Lift the current pieces back up and clear to the plate. */
    async function lift() {
      const root = layer.current;
      if (!root) return;
      const pieces = Array.from(root.querySelectorAll<HTMLElement>("[data-piece]"));
      const shadows = Array.from(root.querySelectorAll<HTMLElement>("[data-shadow]"));
      const full = root.querySelector("[data-full]");
      if (reduced) return;
      full?.animate([{ opacity: 0 }], { duration: 260, easing: "ease-out", fill: "forwards" });
      await sleep(140);
      pieces.forEach((el, i) =>
        el.animate([{ transform: "translate3d(0, -16%, 0)", opacity: 0 }], {
          duration: 400,
          delay: i * 28,
          easing: "cubic-bezier(0.45, 0, 0.9, 0.55)",
          fill: "forwards",
        }),
      );
      shadows.forEach((el) => el.animate([{ opacity: 0 }], { duration: 220, fill: "forwards" }));
      await sleep(400 + pieces.length * 28 + 60);
    }

    return () => {
      cancelled = true;
    };
    // The room never changes for a mounted stage; only the style does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleId, room.id]);

  return (
    <div role="img" aria-label={room.name} className="relative h-full w-full overflow-hidden bg-smoke">
      {base && <img src={media(base)} alt="" draggable={false} className="absolute inset-0 h-full w-full select-none" />}

      {shown && style?.image && (
        <div key={shown} ref={layer} className="absolute inset-0">
          {items.map((p) =>
            p.flat ? null : (
              <div
                key={`s-${p.key}`}
                data-shadow
                className="absolute"
                style={{
                  left: `${p.x1 * 100 + (p.x2 - p.x1) * 8}%`,
                  width: `${(p.x2 - p.x1) * 84}%`,
                  top: `${(p.y2 - 0.034) * 100}%`,
                  height: "4.2%",
                  opacity: 0,
                  background: "radial-gradient(ellipse at 50% 50%, rgb(0 0 0 / 0.5), rgb(0 0 0 / 0.18) 55%, transparent 72%)",
                }}
              />
            ),
          )}
          {items.map((p) => {
            const w = p.x2 - p.x1;
            const h = p.y2 - p.y1;
            const cutOut = usable(cut, [p.x1, p.y1, p.x2, p.y2]);
            const mask = featherMask(p, p.flat && !cutOut);
            return (
              <div
                key={p.key}
                data-piece
                data-drop={p.drop}
                className="absolute will-change-transform"
                style={{
                  left: `${p.x1 * 100}%`,
                  top: `${p.y1 * 100}%`,
                  width: `${w * 100}%`,
                  height: `${h * 100}%`,
                  opacity: 0,
                  maskImage: mask,
                  WebkitMaskImage: mask,
                  maskComposite: "intersect",
                  WebkitMaskComposite: "source-in",
                }}
              >
                <img
                  src={media(style.image!)}
                  alt=""
                  draggable={false}
                  className="absolute max-w-none select-none"
                  style={{
                    width: `${100 / w}%`,
                    height: `${100 / h}%`,
                    left: `${(-p.x1 / w) * 100}%`,
                    top: `${(-p.y1 / h) * 100}%`,
                    ...(cutOut && cut
                      ? {
                          maskImage: `url(${cut.url})`,
                          WebkitMaskImage: `url(${cut.url})`,
                          maskSize: "100% 100%",
                          WebkitMaskSize: "100% 100%",
                          maskRepeat: "no-repeat",
                          WebkitMaskRepeat: "no-repeat",
                        }
                      : null),
                  }}
                />
              </div>
            );
          })}
          <img
            data-full
            src={media(style.image)}
            alt=""
            draggable={false}
            className="absolute inset-0 h-full w-full select-none"
            style={{ opacity: 0 }}
          />
        </div>
      )}

      {overlay.src && (
        <img
          src={overlay.src}
          alt=""
          draggable={false}
          className="absolute inset-0 h-full w-full select-none"
          style={{ opacity: overlay.on ? 1 : 0, transition: "opacity 1400ms ease-in-out" }}
        />
      )}

      {children}
    </div>
  );
}
