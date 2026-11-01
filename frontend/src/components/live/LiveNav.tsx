import { Link } from "react-router-dom";
import type { LiveMoment, LiveRoom } from "../../api";
import RoomSchematic from "./RoomSchematic";
import { styleStatus } from "./stage";

type Props = {
  listingPath: string;
  rooms: LiveRoom[];
  roomIndex: number;
  onRoom: (i: number) => void;
  styles: { id: string; label: string }[];
  styleId: string | null;
  onStyle: (id: string) => void;
  moments: LiveMoment[];
  onMoment: (m: LiveMoment) => void;
  mapRoom: LiveRoom;
  open: boolean;
  setOpen: (open: boolean) => void;
  closeTimer: { current: number };
};

const item = "flex min-h-11 max-w-full min-w-0 items-center gap-2 break-words text-left [overflow-wrap:anywhere] font-serif text-sm transition hover:text-ivory disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:text-ivory/75 sm:min-h-0 sm:gap-2.5 sm:text-[15px]";

/** Hover menu, upper right. The floor plan lives here and nowhere else. */
export default function LiveNav(p: Props) {
  const show = () => {
    clearTimeout(p.closeTimer.current);
    p.setOpen(true);
  };
  const hide = () => {
    p.closeTimer.current = window.setTimeout(() => p.setOpen(false), 380);
  };
  const room = p.rooms[p.roomIndex];
  const reveal = p.open ? "visible translate-y-0 opacity-100" : "invisible -translate-y-1 opacity-0";

  return (
    <nav aria-label="Residence" onMouseEnter={show} onMouseLeave={hide} className="pointer-events-auto flex flex-col items-end">
      <button
        type="button"
        aria-label="Menu"
        aria-expanded={p.open}
        aria-controls="live-menu"
        onClick={() => (p.open ? p.setOpen(false) : show())}
        className="grid h-11 w-11 place-items-center rounded-full bg-night/20 ring-1 ring-ivory/25 backdrop-blur-md transition hover:ring-ice/60"
      >
        <span className="ice-dot" />
      </button>
      <div className={`flex flex-col items-end transition duration-500 ${reveal}`}>
        <span aria-hidden className="mr-[21.5px] h-2 w-px bg-gradient-to-b from-ivory/45 to-transparent sm:h-8" />
        <div
          id="live-menu"
          className="mt-1 max-h-[65dvh] w-[210px] max-w-[calc(100vw-3rem)] space-y-3 overflow-x-hidden overflow-y-auto rounded-xl bg-night/70 p-3 backdrop-blur-xl ring-1 ring-ivory/10 sm:max-h-[78dvh] sm:w-[250px] sm:space-y-6 sm:rounded-2xl sm:bg-night/45 sm:p-5"
        >
          <section aria-label="Rooms" className="space-y-2 sm:space-y-4">
            <p className="eyebrow">Rooms</p>
            {p.mapRoom && (
              <div className="min-w-0">
                <RoomSchematic room={p.mapRoom} styleId={p.styleId} />
                <p className="mt-2 text-[11px] leading-snug text-ivory/70">*Floor plan estimation — derived from SAM detections for this room, not a measured floor plan, not to scale.</p>
                {!p.mapRoom.sam_map && <p className="mt-2 text-[11px] leading-snug text-ivory/70">Map approximate — room geometry not detected</p>}
              </div>
            )}
            <ul className="space-y-0 sm:space-y-2.5">
              {p.rooms.map((r, i) => (
                <li key={r.id}>
                  <button
                    type="button"
                    aria-current={i === p.roomIndex ? "true" : undefined}
                    onClick={() => p.onRoom(i)}
                    className={`${item} ${i === p.roomIndex ? "text-ivory" : "text-ivory/75"}`}
                  >
                    {i === p.roomIndex && <span className="ice-dot" />}
                    {r.name}
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section aria-label="Style" className="space-y-1 sm:space-y-3">
            <p className="eyebrow">Style</p>
            <ul className="space-y-0 sm:space-y-2.5">
              {p.styles.map((s) => {
                const status = room ? (s.id === "original" ? { ok: !!room.before, reason: "Original unavailable" } : styleStatus(room, s.id)) : { ok: false, reason: "" };
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      disabled={!status.ok}
                      title={status.ok ? undefined : status.reason}
                      aria-current={s.id === p.styleId ? "true" : undefined}
                      onClick={() => p.onStyle(s.id)}
                      className={`${item} ${s.id === p.styleId ? "text-ivory" : "text-ivory/75"}`}
                    >
                      {s.id === p.styleId && <span className="ice-dot" />}
                      {s.label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          {p.moments.length > 0 && (
            <section aria-label="Moments" className="space-y-3">
              <p className="eyebrow">Moments</p>
              <ul className="space-y-2.5">
                {p.moments.map((m) => (
                  <li key={`${m.room_id}-${m.id}`}>
                    <button type="button" onClick={() => p.onMoment(m)} className={`${item} text-ivory/75`}>
                      {m.label}
                      <span className="eyebrow">{p.rooms.find((r) => r.id === m.room_id)?.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="flex justify-end pt-1">
            <Link to={p.listingPath} className="eyebrow text-ivory/70! transition hover:text-ivory!">
              Leave
            </Link>
          </div>
        </div>
      </div>
    </nav>
  );
}
