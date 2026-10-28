import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { media, type LiveMoment, type LivePayload } from "../../api";
import { RESIDENCES } from "../../residences";
import Backdrop from "./Backdrop";
import { cutout } from "./cutout";
import { useReducedMotion, useViewport } from "./hooks";
import LiveNav from "./LiveNav";
import MomentFx, { NO_FX, type Fx } from "./MomentFx";
import ReserveControl from "./ReserveControl";
import RoomStage, { type Overlay, type StagePhase } from "./RoomStage";
import {
  aim,
  LOOK_DEGREES,
  maxPanFor,
  preload,
  resolveStyle,
  restOffset,
  roomAspect,
  scaleFor,
  stageSize,
  type Cam,
  type Frame,
} from "./stage";

const REST_EASE = "cubic-bezier(0.22, 0.7, 0.12, 1)";
const MOVE_EASE = "cubic-bezier(0.45, 0, 0.25, 1)";

/** Which plan room lights up for each room type. */
const PLAN_ROOM: Record<string, string> = { living: "living", kitchen: "kitchen", dining: "dining", bedroom: "primary", terrace: "terrace" };

const CAPTION: Record<LiveMoment["id"], string> = { view: "Look out at the view", sit: "Sit down", coffee: "Make coffee" };

const clamp = (v: number, limit: number) => Math.max(-limit, Math.min(limit, v));

type Move = { cam: Cam | null; ms: number; ease: string };
type Token = { abort: boolean; wake: (() => void) | null };

const glassButton =
  "group pointer-events-auto flex items-center gap-4 rounded-full bg-ivory/[0.08] py-2 pl-2 pr-6 text-[15px] tracking-wide text-ivory ring-1 ring-ivory/25 backdrop-blur-xl transition hover:bg-ivory/[0.14] hover:ring-ivory/40";

/** The residence in first person: one room at a time, empty to lived-in, with live-in moments. */
export default function LiveTour({ payload }: { payload: LivePayload }) {
  const navigate = useNavigate();
  const { rooms, moments, styles } = payload;
  const viewport = useViewport();
  const reduced = useReducedMotion();

  const [roomIndex, setRoomIndex] = useState(0);
  const [instant, setInstant] = useState(false);
  const [chosen, setChosen] = useState(payload.default_style);
  const [phase, setPhase] = useState<StagePhase>("empty");
  const [entered, setEntered] = useState(false);
  const [dark, setDark] = useState(true);
  const [pan, setPan] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [visited, setVisited] = useState<Set<string>>(() => new Set([rooms[0]?.id]));
  const [finishPressed, setFinishPressed] = useState(false);
  const [moment, setMoment] = useState<LiveMoment | null>(null);
  const [move, setMove] = useState<Move>({ cam: null, ms: 1800, ease: REST_EASE });
  const [fx, setFx] = useState<Fx>(NO_FX);
  const [vignette, setVignette] = useState(false);
  const [overlay, setOverlay] = useState<Overlay>({ src: null, on: false });
  const [pending, setPending] = useState<LiveMoment | null>(null);

  const drag = useRef({ x: 0, pan: 0 });
  const closeTimer = useRef(0);
  const switching = useRef(false);
  const token = useRef<Token | null>(null);
  const timers = useRef<number[]>([]);

  const room = rooms[roomIndex];
  const { id: styleId, fellBack } = useMemo(() => resolveStyle(room, chosen, payload.default_style), [room, chosen, payload.default_style]);
  const styleLabel = styles.find((s) => s.id === styleId)?.label ?? room.styles[styleId ?? ""]?.label ?? "";
  const chosenLabel = styles.find((s) => s.id === chosen)?.label ?? chosen;

  const stage = useMemo(() => stageSize(viewport.w, viewport.h, roomAspect(room)), [viewport.w, viewport.h, room]);
  const fit = stage.fit;
  const maxPan = maxPanFor(stage, viewport.w);
  const restY = useMemo(
    () => restOffset(styleId ? (room.styles[styleId]?.pieces ?? []) : [], stage, viewport.h),
    [room, styleId, stage, viewport.h],
  );
  const backdropPath = phase === "staged" && styleId ? (room.styles[styleId]?.image ?? null) : (room.plate ?? room.before);
  const finished = finishPressed || visited.size >= rooms.length;
  const last = roomIndex === rooms.length - 1;

  // Latest values for the async moment runner.
  const latest = useRef({ stage, viewport, styleId });
  latest.current = { stage, viewport, styleId };

  const basePlan = RESIDENCES.find((r) => r.id === payload.residence)?.plan ?? null;
  const planRoom = PLAN_ROOM[room.type] ?? basePlan?.current;
  // FloorPlan resets its rotation when this object changes, so only rebuild it when the lit room changes.
  const plan = useMemo(() => (basePlan && planRoom ? { ...basePlan, current: planRoom } : basePlan), [basePlan, planRoom]);
  const heading = (plan?.facing ?? 0) + (maxPan > 0 ? (pan / maxPan) * LOOK_DEGREES : 0);

  const later = (fn: () => void, ms: number) => {
    timers.current.push(window.setTimeout(fn, ms));
  };

  useEffect(() => {
    document.title = payload.title;
    return () => {
      if (token.current) {
        token.current.abort = true;
        token.current.wake?.();
      }
      timers.current.forEach(clearTimeout);
      clearTimeout(closeTimer.current);
    };
  }, [payload.title]);

  useEffect(() => setPan((p) => clamp(p, maxPan)), [maxPan]);
  useEffect(() => setVisited((v) => (v.has(room.id) ? v : new Set(v).add(room.id))), [room.id]);

  // Warm the next room and this room's other styles while the buyer looks around.
  useEffect(() => {
    if (phase !== "staged") return;
    const next = rooms[roomIndex + 1];
    if (next) {
      const s = resolveStyle(next, chosen, payload.default_style).id;
      void preload(next.plate ?? next.before);
      if (s) void preload(next.styles[s]?.image);
      if (s) void cutout(next.plate ?? next.before, next.styles[s]?.image);
    }
    Object.values(room.styles).forEach((s) => {
      if (!s.available) return;
      void preload(s.image);
      void cutout(room.plate ?? room.before, s.image);
    });
    moments.filter((m) => m.room_id === room.id).forEach((m) => Object.values(m.images).forEach((p) => void preload(p)));
  }, [phase, room, roomIndex, rooms, chosen, payload.default_style, moments]);

  const onReady = useCallback(() => {
    setEntered(true);
    setDark(false);
    switching.current = false;
  }, []);

  const goTo = useCallback(
    (i: number, asStaged = false) => {
      if (i < 0 || i >= rooms.length || i === roomIndex || switching.current || token.current) return;
      switching.current = true;
      setDark(true);
      setNavOpen(false);
      if (!asStaged) setPending(null);
      later(() => {
        setRoomIndex(i);
        setInstant(asStaged);
        setPhase("empty");
        setPan(0);
      }, 380);
      later(() => (switching.current = false), 7000);
    },
    [rooms.length, roomIndex],
  );

  // ── live-in moments ──

  const abortMoment = useCallback(() => {
    const t = token.current;
    if (!t) return;
    t.abort = true;
    t.wake?.();
  }, []);

  const playMoment = useCallback(async (m: LiveMoment) => {
    if (token.current) return;
    const tok: Token = { abort: false, wake: null };
    token.current = tok;
    setMoment(m);
    setNavOpen(false);

    const sleep = (ms: number, interruptible = true) =>
      new Promise<void>((resolve) => {
        if (interruptible && tok.abort) return resolve();
        const t = window.setTimeout(() => {
          tok.wake = null;
          resolve();
        }, ms);
        if (interruptible)
          tok.wake = () => {
            clearTimeout(t);
            tok.wake = null;
            resolve();
          };
      });
    const frame = (): Frame => ({ stage: latest.current.stage, vw: latest.current.viewport.w, vh: latest.current.viewport.h });
    const go = (cam: Cam | null, ms: number) => setMove({ cam, ms, ease: MOVE_EASE });
    /** Hold with a faint drift, so the picture is never perfectly still. */
    const hold = async (ms: number, cam: Cam, dx: number, dy: number, ds: number) => {
      const end = Date.now() + ms;
      let k = 0;
      while (!tok.abort && Date.now() < end) {
        const sign = k++ % 2 === 0 ? 1 : -1;
        const step = Math.min(1700, end - Date.now());
        go({ x: cam.x + sign * dx, y: cam.y + sign * dy, s: cam.s + (sign > 0 ? ds : 0) }, 1700);
        await sleep(step);
      }
    };

    try {
      const f = frame();
      if (m.id === "view") {
        const s = scaleFor(m.focus, f, 0.82, 1.15, 2.6);
        const cam = aim(m.focus, s, f);
        go(cam, 2600);
        await sleep(2600);
        if (!tok.abort) {
          setFx({ bloom: true, steam: false });
          await hold(3000, cam, 6, 3, 0.008);
        }
      } else if (m.id === "sit") {
        const s = scaleFor(m.focus, f, 0.5, 1.3, 1.9);
        const approach = aim(m.focus, s, f);
        go(approach, 2400);
        await sleep(2400);
        if (!tok.abort) {
          const eye = aim(m.focus, s + 0.07, f, 0.045);
          setVignette(true);
          go(eye, 1500);
          await sleep(1500);
          if (!tok.abort) await hold(3200, eye, 0, 4, 0.006);
        }
      } else {
        const image = m.images[latest.current.styleId ?? ""];
        const warm = preload(image);
        const s = scaleFor(m.focus, f, 0.45, 1.5, 2.3);
        const cam = aim(m.focus, s, f);
        go(cam, 2400);
        await sleep(2400);
        if (!tok.abort) {
          setFx({ bloom: false, steam: true });
          if (image) {
            await warm;
            setOverlay({ src: media(image), on: false });
            await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
            setOverlay({ src: media(image), on: true });
          }
          await hold(3600, cam, 4, 2, 0.006);
        }
      }
    } finally {
      const back = tok.abort ? 1100 : 1800;
      setFx(NO_FX);
      setVignette(false);
      setOverlay((o) => ({ ...o, on: false }));
      go(null, back);
      await sleep(back, false);
      setOverlay({ src: null, on: false });
      setMove({ cam: null, ms: 1800, ease: REST_EASE });
      setMoment(null);
      token.current = null;
    }
  }, []);

  const requestMoment = useCallback(
    (m: LiveMoment) => {
      if (token.current) return;
      const index = rooms.findIndex((r) => r.id === m.room_id);
      if (index < 0) return;
      setNavOpen(false);
      setPending(m);
      if (index !== roomIndex) goTo(index, true);
    },
    [rooms, roomIndex, goTo],
  );

  useEffect(() => {
    if (!pending || phase !== "staged" || pending.room_id !== room.id || dark) return;
    setPending(null);
    void playMoment(pending);
  }, [pending, phase, room.id, dark, playMoment]);

  // ── keys ──

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof SVGElement) return;
      if (e.key === "Escape") {
        if (token.current) abortMoment();
        else if (navOpen) setNavOpen(false);
        else navigate(`/p/${payload.listing_id}`);
      }
      if (token.current) return;
      if (e.key === "ArrowRight") goTo(roomIndex + 1);
      if (e.key === "ArrowLeft") goTo(roomIndex - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // ── drag to look around ──

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    if (token.current) return abortMoment();
    if (fit) return setNavOpen(false);
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, pan };
    setDragging(true);
    setNavOpen(false);
  }
  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    setPan(clamp(drag.current.pan + (e.clientX - drag.current.x) * 0.8, maxPan));
  }
  const endDrag = () => setDragging(false);

  const caption =
    phase === "staged" && styleId
      ? `AI-staged · ${styleLabel}`
      : room.plate_source === "generated"
        ? "Empty room · AI-modified"
        : room.plate_furnished
          ? "As filmed"
          : "Empty room · as filmed";

  const cam = moment ? move.cam : null;
  const x = cam ? cam.x : pan;
  const roomMoments = moments.filter((m) => m.room_id === room.id);
  const chrome = `transition-opacity duration-700 ${moment || !entered ? "opacity-0" : "opacity-100"}`;

  return (
    <div className="fixed inset-0 overflow-hidden bg-night select-none">
      {fit && <Backdrop path={backdropPath} />}
      <div
        className="absolute"
        style={{
          width: stage.w,
          height: stage.h,
          left: "50%",
          top: "50%",
          marginLeft: -stage.w / 2,
          marginTop: -stage.h / 2,
          transform: `translate3d(${x}px, ${cam ? cam.y : restY}px, 0) scale(${cam ? cam.s : 1})`,
          transition: dragging ? "none" : `transform ${move.ms}ms ${move.ease}`,
        }}
      >
        <div
          className="h-full w-full"
          style={
            fit
              ? {
                  maskImage: "linear-gradient(to right, transparent 0%, #000 6.5%, #000 93.5%, transparent 100%)",
                  WebkitMaskImage: "linear-gradient(to right, transparent 0%, #000 6.5%, #000 93.5%, transparent 100%)",
                }
              : undefined
          }
        >
          <RoomStage
            key={room.id}
            room={room}
            styleId={styleId}
            instant={instant}
            reduced={reduced}
            onReady={onReady}
            onPhase={setPhase}
            overlay={overlay}
          >
            <MomentFx fx={fx} focus={moment?.focus ?? null} />
          </RoomStage>
        </div>
      </div>

      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-night/55 to-transparent" />
        <div className="absolute inset-0 bg-[radial-gradient(34rem_20rem_at_0%_0%,rgb(13_14_16/0.55),transparent_70%)]" />
        <div className="absolute inset-x-0 bottom-0 h-[38%] bg-gradient-to-t from-night/75 via-night/25 to-transparent" />
        <div
          className="absolute inset-0 transition-opacity duration-[1200ms]"
          style={{
            opacity: vignette ? 1 : 0,
            background: "radial-gradient(ellipse at 50% 50%, transparent 42%, rgb(13 14 16 / 0.62) 100%)",
          }}
        />
      </div>

      <div
        role="img"
        aria-label={fit ? `${payload.title}, ${room.name}.` : `${payload.title}, ${room.name}. Drag to look around.`}
        className={`absolute inset-0 touch-none ${moment ? "cursor-pointer" : fit ? "" : "cursor-grab active:cursor-grabbing"}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      />

      <div
        className="pointer-events-none absolute inset-0 bg-night"
        style={{ opacity: dark ? 1 : 0, transition: `opacity ${dark ? 380 : entered ? 800 : 1600}ms ease-in-out` }}
      />

      <div className="legible pointer-events-none absolute inset-0">
        <div inert={!!moment} className={chrome}>
          <div className="absolute left-6 top-6 max-w-[min(26rem,60vw)] sm:left-10 sm:top-9">
            <p className="font-serif text-xl text-ivory/90">{payload.title}</p>
            <p key={room.id} className="eyebrow mt-1.5 flex animate-fade-in items-center gap-2.5 text-ivory/80!">
              <span className="ice-dot" />
              {room.name}
            </p>
            <p className="eyebrow mt-1.5 text-ivory/55!" aria-live="polite">
              {caption}
            </p>
            {fellBack && styleId && (
              <p className="eyebrow mt-1.5 text-ivory/45!">
                {chosenLabel} isn't available in this room · showing {styleLabel}
              </p>
            )}
            {!styleId && <p className="eyebrow mt-1.5 text-ivory/45!">Staging isn't available for this room</p>}
            {payload.note && <p className="eyebrow mt-3 max-w-xs text-[0.58rem]! leading-relaxed normal-case tracking-wide text-ivory/60!">{payload.note}</p>}
          </div>

          <div className="absolute right-6 top-6 sm:right-10 sm:top-9">
            <LiveNav
              listingId={payload.listing_id}
              title={payload.title}
              rooms={rooms}
              roomIndex={roomIndex}
              onRoom={goTo}
              styles={styles}
              styleId={styleId}
              onStyle={setChosen}
              moments={moments}
              onMoment={requestMoment}
              plan={plan}
              heading={heading}
              open={navOpen}
              setOpen={setNavOpen}
              closeTimer={closeTimer}
            />
          </div>

          <div className="absolute inset-x-0 bottom-24 flex flex-col items-center gap-3.5 sm:bottom-9">
            <div
              className={`flex flex-wrap items-center justify-center gap-x-7 gap-y-2 transition-opacity duration-700 ${phase === "staged" && !dark ? "opacity-100" : "opacity-0"}`}
            >
              {roomMoments.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  disabled={phase !== "staged"}
                  onClick={() => requestMoment(m)}
                  className="eyebrow pointer-events-auto text-ivory/70! transition hover:text-ice!"
                >
                  {m.label}
                </button>
              ))}
            </div>
            {finishPressed ? (
              <Link to={`/p/${payload.listing_id}`} className={glassButton}>
                <span className="grid h-9 w-9 place-items-center rounded-full ring-1 ring-ivory/30">
                  <span className="ice-dot" />
                </span>
                View listing
                <span aria-hidden className="transition group-hover:translate-x-1">→</span>
              </Link>
            ) : (
              <button type="button" onClick={() => (last ? setFinishPressed(true) : goTo(roomIndex + 1))} className={glassButton}>
                <span className="grid h-9 w-9 place-items-center rounded-full ring-1 ring-ivory/30">
                  <span className="ice-dot" />
                </span>
                {last ? "Finish" : "Next room"}
                {!last && <span aria-hidden className="transition group-hover:translate-x-1">→</span>}
                <span className="font-mono text-[11px] tracking-widest text-ivory/55">
                  {roomIndex + 1} / {rooms.length}
                </span>
              </button>
            )}
            {!fit && <p className="eyebrow text-ivory/55!">Drag to look around</p>}
          </div>

          <div
            className={`absolute bottom-10 right-6 transition-opacity duration-1000 sm:right-10 ${finished ? "opacity-100" : "pointer-events-none opacity-0"}`}
            inert={!finished}
          >
            {finished && <ReserveControl listingId={payload.listing_id} />}
          </div>
        </div>

        <div
          aria-live="polite"
          className={`absolute inset-x-0 bottom-12 flex flex-col items-center gap-1.5 transition-opacity duration-700 ${moment ? "opacity-100" : "opacity-0"}`}
        >
          <p className="eyebrow text-ivory/85!">{moment ? CAPTION[moment.id] : ""}</p>
          <p className="eyebrow text-ivory/45!">{styleId ? `AI-staged · ${styleLabel}` : ""}</p>
          <p className="eyebrow text-ivory/35!">Esc or click to return</p>
        </div>
      </div>
    </div>
  );
}
