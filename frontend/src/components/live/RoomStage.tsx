import { useEffect, useRef, useState, type ReactNode } from "react";
import { media, type LiveRoom } from "../../api";
import { IDENTITY, placed, preload } from "./stage";

export type StagePhase = "empty" | "staged";
export type Overlay = { src: string | null; on: boolean };
type Props = {
  room: LiveRoom;
  original?: boolean;
  styleId: string | null;
  instant: boolean;
  reduced: boolean;
  beat?: number;
  onReady: () => void;
  onPhase: (phase: StagePhase) => void;
  overlay: Overlay;
  children?: ReactNode;
};

export default function RoomStage({ room, original, styleId, reduced, onReady, onPhase, overlay, children }: Props) {
  const [shown, setShown] = useState<string | null>(null);
  const [incoming, setIncoming] = useState<string | null>(null);
  const shownRef = useRef<string | null>(null);
  const callbacks = useRef({ onReady, onPhase });
  callbacks.current = { onReady, onPhase };
  const base = original ? room.before : (room.plate ?? room.before);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    const next = styleId ? room.styles[styleId] : undefined;
    const target = next?.available && next.image ? styleId : null;
    const finish = () => {
      shownRef.current = target;
      setShown(target);
      setIncoming(null);
      callbacks.current.onReady();
      callbacks.current.onPhase(target ? "staged" : "empty");
    };
    Promise.all([preload(base), preload(next?.image)]).then(() => {
      if (cancelled) return;
      if (!reduced && shownRef.current && target && shownRef.current !== target) {
        setIncoming(target);
        timer = window.setTimeout(finish, 400);
      } else finish();
    });
    return () => { cancelled = true; clearTimeout(timer); };
  }, [styleId, room.id, reduced, base]);

  const style = shown ? room.styles[shown] : undefined;
  const next = incoming ? room.styles[incoming] : undefined;
  const baseAlign = !original && room.plate_source === "generated" ? room.plate_align : IDENTITY;
  return (
    <div role="img" aria-label={room.name} className="relative h-full w-full overflow-hidden bg-smoke">
      <style>{`@keyframes room-style-fade { from { opacity: 0 } to { opacity: 1 } }`}</style>
      {(style?.image || base) && <img src={media(style?.image || base!)} alt="" draggable={false} className="absolute max-w-none select-none" style={placed(style?.image ? (style.align ?? IDENTITY) : baseAlign)} />}
      {next?.image && <img key={incoming} src={media(next.image)} alt="" draggable={false} className="absolute max-w-none select-none" style={{ ...placed(next.align ?? IDENTITY), animation: "room-style-fade 400ms cubic-bezier(0.22, 1, 0.36, 1) both" }} />}
      {overlay.src && <img src={overlay.src} alt="" draggable={false} className="absolute max-w-none select-none" style={{ ...placed(style?.align ?? IDENTITY), opacity: overlay.on ? 1 : 0, transition: "opacity 1400ms ease-in-out" }} />}
      {children}
    </div>
  );
}
