import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { clock, media, type LiveMoment, type LivePayload } from "../../api";
import { Wordmark } from "../Shell";
import Backdrop from "./Backdrop";
import { cutout } from "./cutout";
import { playCyberpunk } from "./cyberpunk";
import { useReducedMotion, useViewport } from "./hooks";
import LiveNav from "./LiveNav";
import GuidePanel from "./GuidePanel";
import GuideAvatar from "./GuideAvatar";
import MomentFx, { NO_FX, type Fx } from "./MomentFx";
import ReserveControl from "./ReserveControl";
import RoomStage, { type Overlay, type StagePhase } from "./RoomStage";
import {
  aim,
  IDENTITY,
  maxPanFor,
  preload,
  resolveStyle,
  restOffset,
  roomAspect,
  scaleFor,
  stageSize,
  styleStatus,
  type Cam,
  type Frame,
  type Pan,
} from "./stage";

const REST_EASE = "cubic-bezier(0.22, 0.7, 0.12, 1)";
const MOVE_EASE = "cubic-bezier(0.45, 0, 0.25, 1)";
/** Walking in from the video, the empty room has just been seen: a short beat, then the cascade.
    The main living space holds longest — the vibe is the point. */
const ARRIVAL_BEAT = 1400;
const MAIN_BEAT = 2400;
const WALK_RATE = 1;
const FIT_TILT = 5;

const CAPTION: Record<LiveMoment["id"], string> = { view: "Look out at the view", sit: "Sit down", coffee: "Make coffee" };

const clamp = (v: number, limit: number) => Math.max(-limit, Math.min(limit, v));

type Move = { cam: Cam | null; ms: number; ease: string };
type Token = { abort: boolean; wake: (() => void) | null };
type Mode = "walk" | "room";

const glassButton =
  "group pointer-events-auto flex items-center gap-4 rounded-full bg-ivory/[0.08] py-2 pl-2 pr-6 text-[15px] tracking-wide text-ivory ring-1 ring-ivory/25 backdrop-blur-xl transition hover:bg-ivory/[0.14] hover:ring-ivory/40";

/**
 * The residence in first person. With a walkthrough video, Live-In-It walks the filmed path in order: the
 * video plays, stops on each lived-in room exactly at its hero frame, and the furniture falls from the ceiling
 * over that frame; "Continue walking" picks the video up again. Bathrooms and utility rooms are walked past.
 * Without a video (older listings) it goes room by room.
 */
export default function LiveTour({ payload }: { payload: LivePayload }) {
  const navigate = useNavigate();
  const styles = [{ id: "original", label: "Original" }, ...[["modern-luxury", "Modern luxury"], ["coastal", "Coastal"], ["minimal", "Minimal"], ["2142", "Cyberpunk"]].map(([id, label]) => ({ id, label }))];
  const listingPath = `/p/${payload.listing_id}`;
  const video = payload.video;
  const viewport = useViewport();
  const reduced = useReducedMotion();

  // On the video walk, stop only where furniture can fall: rooms with at least one usable style.
  const rooms = useMemo(() => {
    const timed = !!video && payload.rooms.some((r) => r.t != null);
    const usable = payload.rooms.filter((r) => Object.values(r.styles).some((s) => s.available && s.image));
    return timed && usable.length ? usable : payload.rooms;
  }, [payload.rooms, video]);
  const walking = !!video && rooms.some((r) => r.t != null);
  // TODO: Restore sit and coffee when they do more than zoom.
  const moments = useMemo(() => payload.moments.filter((m) => !["sit", "coffee", "view"].includes(m.id) && rooms.some((r) => r.id === m.room_id)), [payload.moments, rooms]);
  // TODO: Restore drag-to-look when it behaves like a real look-around.
  const dragToLookEnabled = false;

  const [mode, setMode] = useState<Mode>(walking ? "walk" : "room");
  const [arrived, setArrived] = useState(!walking);
  const [playing, setPlaying] = useState(false);
  const [now, setNow] = useState(0);
  const [ended, setEnded] = useState(false);
  const [roomIndex, setRoomIndex] = useState(0);
  const [instant, setInstant] = useState(false);
  const [chosen, setChosen] = useState("modern-luxury");
  const [intro, setIntro] = useState(true);
  const [introVisible, setIntroVisible] = useState(true);
  const [titleOpen, setTitleOpen] = useState(true);
  const [titlePos, setTitlePos] = useState({ x: 24, y: 80 });
  const titleDrag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const [avatarOn, setAvatarOn] = useState(true);
  const [styleChange, setStyleChange] = useState(0);
  const choose = (id: string) => {
    if (id === "2142") playCyberpunk();
    setChosen(id);
    setStyleChange(n => n + 1);
    setIntro(false);
  };
  const [phase, setPhase] = useState<StagePhase>("empty");
  const [entered, setEntered] = useState(false);
  const [dark, setDark] = useState(false);
  const [pan, setPan] = useState<Pan>({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [finishPressed, setFinishPressed] = useState(false);
  const [moment, setMoment] = useState<LiveMoment | null>(null);
  const [move, setMove] = useState<Move>({ cam: null, ms: 1800, ease: REST_EASE });
  const [fx, setFx] = useState<Fx>(NO_FX);
  const [vignette, setVignette] = useState(false);
  const [overlay, setOverlay] = useState<Overlay>({ src: null, on: false });
  const [pending, setPending] = useState<LiveMoment | null>(null);

  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const drag = useRef({ x: 0, y: 0, pan: { x: 0, y: 0 } });
  const closeTimer = useRef(0);
  const switching = useRef(false);
  const token = useRef<Token | null>(null);
  const timers = useRef<number[]>([]);
  const videoRef = useRef<HTMLVideoElement>(null);
  const autoplayTimer = useRef(0);
  const nextStop = useRef(0);

  const room = rooms[roomIndex];
  const { id: styleId, fellBack } = useMemo(() => chosen === "original" ? { id: null, fellBack: false } : resolveStyle(room, chosen, "modern-luxury"), [room, chosen]);
  const styleLabel = styles.find((s) => s.id === styleId)?.label ?? room.styles[styleId ?? ""]?.label ?? "";
  const chosenLabel = styles.find((s) => s.id === chosen)?.label ?? chosen;
  const inRoom = mode === "room";

  const phone = viewport.w < 640;
  const aspect = inRoom ? roomAspect(room) : walking && video ? video.width / video.height : roomAspect(room);
  const stage = useMemo(() => {
    if (phone && inRoom) { const height = Math.max(100, viewport.h - 460); const width = Math.min(viewport.w, height * aspect); return { w: width, h: width / aspect, fit: false }; }
    const size = stageSize(viewport.w, viewport.h, aspect);
    return walking && !inRoom && size.fit ? { ...size, w: viewport.h * 0.84 * aspect, h: viewport.h * 0.84 } : size;
  }, [viewport.w, viewport.h, aspect, walking, inRoom, phone]);
  const fit = stage.fit;
  const maxPan = maxPanFor(stage, viewport.w, viewport.h);
  // Keep framing anchored to the room, independent of the selected furniture style.
  const framingStyle = resolveStyle(room, payload.default_style, payload.default_style).id;
  const stagedStyle = framingStyle ? room.styles[framingStyle] : undefined;
  const restY = useMemo(
    () => (inRoom && stagedStyle ? restOffset(stagedStyle.pieces ?? [], stage, viewport.h, stagedStyle.align ?? IDENTITY) : 0),
    [inRoom, stagedStyle, stage, viewport.h],
  );

  // Where the walk is: the room on the video timeline at this moment (prepared or walked past).
  const pathStop = useMemo(() => {
    const stops = payload.path ?? [];
    return [...stops].reverse().find((s) => (s.span?.[0] ?? s.t) <= now + 0.2) ?? null;
  }, [payload.path, now]);
  const nearestRoom = useMemo(() => {
    if (!walking) return room;
    const ahead = rooms.find((r) => (r.t ?? 0) >= now);
    return ahead ?? rooms[rooms.length - 1];
  }, [walking, rooms, room, now]);

  const backdropPath = inRoom
    ? chosen === "original" ? room.before : phase === "staged" && styleId
      ? (room.styles[styleId]?.image ?? null)
      : (room.plate ?? room.before)
    : (nearestRoom?.before ?? null);
  const last = roomIndex === rooms.length - 1;

  // Latest values for the async moment runner.
  const latest = useRef({ stage, viewport, styleId });
  latest.current = { stage, viewport, styleId };

  const later = (fn: () => void, ms: number) => {
    timers.current.push(window.setTimeout(fn, ms));
  };

  useEffect(() => {
    if (!entered || !inRoom || !intro) return;
    const timer = window.setTimeout(() => setIntro(false), 5000);
    return () => clearTimeout(timer);
  }, [entered, inRoom, intro]);

  useEffect(() => {
    if (intro) return;
    const timer = window.setTimeout(() => setIntroVisible(false), 650);
    return () => clearTimeout(timer);
  }, [intro]);

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

  useEffect(() => setPan((p) => ({ x: clamp(p.x, maxPan.x), y: clamp(p.y, maxPan.y) })), [maxPan.x, maxPan.y]);

  // Warm what comes next: while walking, the next room; in a room, its other styles and the next room.
  useEffect(() => {
    const warm = (r: (typeof rooms)[number] | undefined) => {
      if (!r) return;
      const s = resolveStyle(r, chosen, payload.default_style).id;
      void preload(r.plate ?? r.before);
      if (!s) return;
      void preload(r.styles[s]?.image);
      void preload(r.styles[s]?.mask);
      if (!r.styles[s]?.mask) void cutout(r.plate ?? r.before, r.styles[s]?.image);
    };
    if (!inRoom) return warm(rooms[nextStop.current]);
    if (phase !== "staged") return;
    warm(rooms[roomIndex + 1]);
    Object.values(room.styles).forEach((s) => {
      if (!s.available) return;
      void preload(s.image);
      void preload(s.mask);
    });
    moments.filter((m) => m.room_id === room.id).forEach((m) => Object.values(m.images).forEach((p) => void preload(p)));
  }, [inRoom, phase, room, roomIndex, rooms, chosen, payload.default_style, moments]);

  const onReady = useCallback(() => {
    setEntered(true);
    setDark(false);
    switching.current = false;
  }, []);

  // ── the walk: the video plays and stops at each prepared room's hero frame ──

  const arrive = useCallback(
    (i: number) => {
      const el = videoRef.current;
      const t = rooms[i]?.t;
      if (!el || t == null) return;
      el.pause();
      nextStop.current = i + 1;
      const show = () => {
        setRoomIndex(i);
        setInstant(false);
        setPhase("empty");
        setPan({ x: 0, y: 0 });
        setArrived(true);
        setMode("room");
      };
      if (Math.abs(el.currentTime - t) > 0.02) {
        el.addEventListener("seeked", show, { once: true });
        el.currentTime = t;
      } else show();
    },
    [rooms],
  );

  useEffect(() => {
    if (!walking || !playing) return;
    let raf = 0;
    let shown = -1;
    const tick = () => {
      const el = videoRef.current;
      if (!el) return;
      const t = el.currentTime;
      if (Math.abs(t - shown) > 0.15) {
        shown = t;
        setNow(t);
      }
      const stop = rooms[nextStop.current];
      if (stop?.t != null && t >= stop.t - 0.03) return arrive(nextStop.current);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [walking, playing, rooms, arrive]);

  const play = useCallback(() => {
    const el = videoRef.current;
    if (!el) return;
    el.playbackRate = WALK_RATE;
    setEnded(false);
    void el.play().catch(() => undefined);
  }, []);

  const continueWalk = useCallback(() => {
    if (token.current) return;
    setNavOpen(false);
    setPending(null);
    setMode("walk");
    later(play, 480);
  }, [play]);

  /** Jump the walk to a time: the next stop is the first room after it. */
  const seekWalk = useCallback(
    (t: number) => {
      const el = videoRef.current;
      if (!el || token.current) return;
      nextStop.current = rooms.findIndex((r) => (r.t ?? 0) > t + 0.05);
      if (nextStop.current < 0) nextStop.current = rooms.length;
      el.currentTime = t;
      setNow(t);
      setMode("walk");
      later(play, 300);
    },
    [rooms, play],
  );

  const goTo = useCallback(
    (i: number, asStaged = false) => {
      if (i < 0 || i >= rooms.length || switching.current || token.current) return;
      if (i === roomIndex && inRoom) return;
      switching.current = true;
      clearTimeout(autoplayTimer.current);
      setNavOpen(false);
      if (!asStaged) setPending(null);
      const fromRoom = inRoom && arrived;
      if (fromRoom) setDark(true);
      later(
        () => {
          if (walking) {
            const el = videoRef.current;
            el?.pause();
            if (el && rooms[i].t != null) el.currentTime = rooms[i].t!;
            nextStop.current = i + 1;
            setNow(rooms[i].t ?? 0);
            setArrived(true);
            setMode("room");
          }
          setRoomIndex(i);
          setInstant(asStaged);
          setPhase("empty");
          setPan({ x: 0, y: 0 });
          if (!fromRoom) switching.current = false;
        },
        fromRoom ? 380 : 0,
      );
      later(() => (switching.current = false), 7000);
    },
    [rooms, roomIndex, inRoom, arrived, walking],
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
      if (index !== roomIndex || !inRoom) goTo(index, true);
    },
    [rooms, roomIndex, inRoom, goTo],
  );

  useEffect(() => {
    if (!pending || !inRoom || phase !== "staged" || pending.room_id !== room.id || dark) return;
    setPending(null);
    void playMoment(pending);
  }, [pending, inRoom, phase, room.id, dark, playMoment]);

  // ── keys ──

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof SVGElement) return;
      if (e.key === "Escape") {
        if (token.current) abortMoment();
        else if (navOpen) setNavOpen(false);
        else navigate(listingPath);
      }
      if (token.current) return;
      if (e.key === "ArrowRight") {
        if (walking && inRoom) continueWalk();
        else if (!walking) goTo(roomIndex + 1);
      }
      if (e.key === "ArrowLeft") goTo(roomIndex - 1);
      if (e.key === " " && walking && !inRoom) {
        e.preventDefault();
        if (playing) videoRef.current?.pause();
        else play();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // ── drag to look around ──

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    if (token.current) return abortMoment();
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, pan };
    setDragging(true);
    setNavOpen(false);
  }
  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    setPan({
      x: clamp(drag.current.pan.x + (e.clientX - drag.current.x) * 0.8, maxPan.x),
      y: clamp(drag.current.pan.y + (e.clientY - drag.current.y) * 0.8, maxPan.y),
    });
  }
  const endDrag = () => setDragging(false);

  const caption = !inRoom
    ? ended
      ? "End of the walkthrough"
      : "Walking the residence · as filmed"
    : chosen === "original" ? "Original / Unstaged"
    : phase === "staged" && styleId
      ? `AI-staged · ${styleLabel}`
      : room.plate_source === "generated"
        ? "Empty room · AI-modified"
        : room.plate_furnished
          ? "As filmed"
          : "Empty room · as filmed";

  const cam = moment ? move.cam : null;
  const x = phone && inRoom ? 0 : cam ? cam.x : pan.x;
  const y = phone && inRoom ? 0 : cam ? cam.y : clamp(restY + pan.y, maxPan.y);
  const tilt = fit && !cam && maxPan.x > 0 ? (-pan.x / maxPan.x) * FIT_TILT : 0;
  const roomMoments = inRoom ? moments.filter((m) => m.room_id === room.id) : [];
  const chrome = `transition-opacity duration-700 ${moment || !entered ? "opacity-0" : "opacity-100"}`;
  const roomName = inRoom ? room.name : (pathStop?.name ?? "");
  const nextRoom = rooms[nextStop.current];

  return (
    <div className="fixed inset-0 overflow-hidden bg-night select-none">
      {(fit || (phone && inRoom)) && <Backdrop path={backdropPath} />}
      <div
        className="absolute"
        style={{
          width: stage.w,
          height: stage.h,
          left: "50%",
          top: "50%",
          marginLeft: -stage.w / 2,
          marginTop: -stage.h / 2,
          transform: `perspective(1600px) translate3d(${x}px, ${y}px, 0) rotateY(${tilt}deg) scale(${cam ? cam.s : 1})`,
          transition: dragging ? "none" : `transform ${move.ms}ms ${move.ease}`,
        }}
      >
        <div
          className="relative h-full w-full overflow-hidden"
          style={
            fit
              ? {
                  maskImage: "linear-gradient(to right, transparent 0%, #000 6.5%, #000 93.5%, transparent 100%)",
                  WebkitMaskImage: "linear-gradient(to right, transparent 0%, #000 6.5%, #000 93.5%, transparent 100%)",
                }
              : undefined
          }
        >
          {walking && video && (
            <video
              ref={videoRef}
              src={media(video.path)}
              poster={rooms[0]?.before ? media(rooms[0].before) : undefined}
              muted
              playsInline
              preload="auto"
              className="absolute inset-0 h-full w-full object-fill"
              onLoadedData={(e) => {
                e.currentTarget.defaultPlaybackRate = WALK_RATE;
                e.currentTarget.playbackRate = WALK_RATE;
                setEntered(true);
                setDark(false);
                autoplayTimer.current = window.setTimeout(play, 1400);
              }}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onEnded={() => {
                setPlaying(false);
                setEnded(true);
                nextStop.current = rooms.length;
              }}
            />
          )}
          {arrived && (
            <div
              className="absolute inset-0"
              style={{ opacity: inRoom ? 1 : 0, transition: `opacity ${inRoom ? 420 : 480}ms ease-in-out`, pointerEvents: "none" }}
            >
              <RoomStage
                key={room.id}
                room={room}
                original={chosen === "original"}
                styleId={styleId}
                instant={instant}
                reduced={reduced}
                beat={walking ? (room.main ? MAIN_BEAT : ARRIVAL_BEAT) : undefined}
                onReady={onReady}
                onPhase={setPhase}
                overlay={overlay}
              >
                <MomentFx fx={fx} focus={moment?.focus ?? null} />
              </RoomStage>
            </div>
          )}
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
        aria-label={`${payload.title}, ${roomName}.`}
        className={`absolute inset-0 touch-none ${moment ? "cursor-pointer" : dragToLookEnabled ? "cursor-grab active:cursor-grabbing" : "cursor-default"}`}
        onTouchStart={(e) => { const t = e.touches[0]; touchStart.current = { x: t.clientX, y: t.clientY }; }}
        onTouchEnd={(e) => { const start = touchStart.current; const end = e.changedTouches[0]; touchStart.current = null; if (!start || Math.abs(end.clientX - start.x) < 60 || Math.abs(end.clientX - start.x) < Math.abs(end.clientY - start.y)) return; if (end.clientX < start.x) { if (walking && inRoom) continueWalk(); else if (!walking) goTo(roomIndex + 1); } else goTo(roomIndex - 1); }}
        onPointerDown={dragToLookEnabled ? onPointerDown : undefined}
        onPointerMove={dragToLookEnabled ? onPointerMove : undefined}
        onPointerUp={dragToLookEnabled ? endDrag : undefined}
        onPointerCancel={dragToLookEnabled ? endDrag : undefined}
      />

      <div
        className="pointer-events-none absolute inset-0 bg-night"
        style={{ opacity: dark ? 1 : 0, transition: `opacity ${dark ? 380 : entered ? 800 : 1600}ms ease-in-out` }}
      />

      {entered && inRoom && !moment && <GuidePanel listingId={payload.listing_id} room={room} rooms={rooms} styleId={chosen} onStyle={choose} onRoom={(i) => goTo(i, true)} avatarOn={avatarOn} setAvatarOn={setAvatarOn} intro={introVisible} styleChange={styleChange} />}
      {entered && inRoom && introVisible && <div className={`guide-intro pointer-events-none absolute z-10 flex flex-col items-center gap-3 rounded-3xl bg-night/55 px-5 py-4 text-center text-ivory shadow-xl ring-1 ring-ivory/15 backdrop-blur-md ${intro ? "" : "guide-intro--leaving"}`}>{avatarOn && <GuideAvatar large />}<span className="text-base leading-relaxed">Please choose your staging type below.</span></div>}
      <div className="legible pointer-events-none absolute inset-0">
        <div className="absolute left-6 top-6 sm:left-10 sm:top-9"><Wordmark /></div>
        <div inert={!!moment} className={chrome}>
          <div className="pointer-events-auto absolute bottom-28 left-10 z-20 hidden sm:block">
            <ReserveControl listingId={payload.listing_id} />
          </div>
          <div className="pointer-events-auto absolute left-6 top-16 z-20 sm:hidden"><ReserveControl listingId={payload.listing_id} /></div>
          <div className="pointer-events-auto absolute max-w-[min(26rem,75vw)] touch-none" style={{ left: Math.min(titlePos.x, Math.max(0, viewport.w - 48)), top: Math.min(titlePos.y + (phone ? 50 : 0), Math.max(0, viewport.h - 48)) }} onPointerDown={e => { if ((e.target as HTMLElement).closest("button")) return; const rect = e.currentTarget.getBoundingClientRect(); titleDrag.current = { x: e.clientX, y: e.clientY, left: rect.left, top: rect.top - (phone ? 50 : 0) }; e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { const start = titleDrag.current; if (!start) return; const rect = e.currentTarget.getBoundingClientRect(); setTitlePos({ x: Math.max(0, Math.min(viewport.w - rect.width, start.left + e.clientX - start.x)), y: Math.max(0, Math.min(viewport.h - rect.height - (phone ? 50 : 0), start.top + e.clientY - start.y)) }); }} onPointerUp={() => { titleDrag.current = null; }} onPointerCancel={() => { titleDrag.current = null; }}>
            <button type="button" aria-label={titleOpen ? "Collapse title" : "Expand title"} onClick={() => setTitleOpen(!titleOpen)} className="absolute right-0 top-0 z-10 grid h-11 w-11 place-items-center"><span className="grid h-8 w-8 place-items-center rounded-full bg-ivory/10 text-ivory ring-1 ring-ivory/30">{titleOpen ? "−" : "+"}</span></button>
            {titleOpen && <div className="rounded-2xl bg-night/45 p-4 pr-12 shadow-lg backdrop-blur-md sm:p-5 sm:pr-12">
            <p className="font-serif text-xl text-ivory/90">{payload.title}</p>
            <p key={roomName} className="eyebrow mt-1.5 flex animate-fade-in items-center gap-2.5 text-ivory/80!">
              <span className="ice-dot" />
              {roomName}
            </p>
            <p className="eyebrow mt-1.5 text-ivory/55!" aria-live="polite">
              {caption}
            </p>
            {inRoom && styleId === "2142" && <p className="eyebrow mt-1.5 max-w-xs normal-case tracking-wide text-ivory/70!">Cyberpunk concept · AI-imagined, not a verified depiction of the property</p>}
            {inRoom && fellBack && styleId && (
              <p className="eyebrow mt-1.5 text-ivory/45!">
                {chosenLabel} isn't available in this room · showing {styleLabel}
              </p>
            )}
            {inRoom && !styleId && chosen !== "original" && <p className="eyebrow mt-1.5 text-ivory/45!">Staging isn't available for this room</p>}
            {payload.note && !/test upload/i.test(payload.note) && <p className="eyebrow mt-3 max-w-xs text-[0.58rem]! leading-relaxed normal-case tracking-wide text-rose/80!">{payload.note}</p>}
            </div>}
          </div>

          <div className="absolute right-6 top-6 sm:right-10 sm:top-9">
            <LiveNav
              listingPath={listingPath}
              rooms={rooms}
              roomIndex={inRoom ? roomIndex : -1}
              onRoom={goTo}
              styles={styles}
              styleId={chosen === "original" ? "original" : styleId}
              onStyle={choose}
              moments={moments}
              onMoment={requestMoment}
              mapRoom={room}
              open={navOpen}
              setOpen={setNavOpen}
              closeTimer={closeTimer}
            />
          </div>

          <div className="absolute inset-x-0 bottom-24 flex flex-col items-center gap-3.5 sm:bottom-9">
            {roomMoments.length > 0 && (
              <div className={`flex flex-wrap items-center justify-center gap-x-7 gap-y-2 transition-opacity duration-700 ${phase === "staged" && !dark ? "opacity-100" : "opacity-0"}`}>
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
            )}

            {walking && !inRoom && (
              <button type="button" onClick={() => goTo(Math.max(0, rooms.findIndex((r) => r.main)), true)} className="btn-glass pointer-events-auto">
                Choose furniture
              </button>
            )}

            {walking && video && (
              <div className="pointer-events-auto relative h-5 w-[min(34rem,80vw)]" aria-label="The walkthrough">
                <div className="absolute inset-x-0 top-1/2 h-px bg-ivory/15" />
                <div className="absolute left-0 top-1/2 h-px bg-ice/60" style={{ width: `${Math.min(100, (now / video.duration) * 100)}%` }} />
                {(payload.path ?? []).map((s) => {
                  const index = rooms.findIndex((r) => r.id === s.id);
                  return (
                    <button
                      key={s.id}
                      type="button"
                      title={`${s.name} · ${clock(s.t)}${s.prepared ? "" : " · walked past"}`}
                      aria-label={`${s.name}, ${clock(s.t)}`}
                      onClick={() => (index >= 0 ? goTo(index) : seekWalk(s.span?.[0] ?? s.t))}
                      className="absolute top-1/2 grid h-5 w-5 -translate-x-1/2 -translate-y-1/2 place-items-center"
                      style={{ left: `${((index >= 0 ? s.t : (s.span?.[0] ?? s.t)) / video.duration) * 100}%` }}
                    >
                      <span
                        className={`block rounded-full ${s.prepared ? "h-2 w-2 bg-ice shadow-[0_0_10px_rgb(155_230_239/0.7)]" : "h-1 w-1 bg-ivory/45"}`}
                      />
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {!inRoom && walking && <button type="button" onClick={() => goTo(Math.max(0, rooms.findIndex(r => r.main)), true)} className="pointer-events-auto absolute bottom-4 left-3 z-10 min-h-11 rounded-full bg-night/90 px-5 text-sm text-ivory sm:hidden">Choose furniture</button>}
          {inRoom && <div className="pointer-events-auto absolute inset-x-0 z-10 rounded-xl bg-night/35 px-2 ring-1 ring-ivory/15 backdrop-blur-xl sm:hidden" style={{ bottom: "calc(6rem + env(safe-area-inset-bottom))" }}>
            <div role="group" aria-label="Style" className="flex justify-between gap-0.5">{styles.map(s => { const status = s.id === "original" ? { ok: !!room.before, reason: "Original unavailable" } : styleStatus(room, s.id); return <button key={s.id} type="button" disabled={!status.ok} title={status.reason} aria-pressed={s.id === (chosen === "original" ? "original" : styleId)} onClick={() => choose(s.id)} className={`min-h-11 min-w-0 border-b px-1 text-[11px] tracking-wide text-ivory disabled:opacity-35 ${s.id === (chosen === "original" ? "original" : styleId) ? "border-ice" : "border-transparent"}`}>{s.label}</button>; })}</div>
            <div className="flex items-center justify-end gap-2"><button type="button" className="flex min-h-11 w-28 items-center text-xs text-ivory/85" onClick={() => walking ? continueWalk() : last ? setFinishPressed(true) : goTo(roomIndex + 1)}><span className="flex h-[34px] w-full items-center justify-center rounded-full bg-ivory/[0.07] px-2 ring-1 ring-ivory/25">{walking ? "Continue walking" : last ? "Finish" : "Next room"}</span></button></div>
          </div>}
          <div className="absolute inset-x-0 bottom-10 hidden items-center px-6 sm:flex sm:px-10">
            <div className="pointer-events-auto">
              {walking ? (
                inRoom ? (
                  <button type="button" onClick={continueWalk} className={glassButton}>
                    <span className="grid h-9 w-9 place-items-center rounded-full ring-1 ring-ivory/30">
                      <span className="ice-dot" />
                    </span>
                    Continue walking
                    <span aria-hidden className="transition group-hover:translate-x-1">→</span>
                    <span className="font-mono text-[11px] tracking-widest text-ivory/55">
                      {roomIndex + 1} / {rooms.length}
                    </span>
                  </button>
                ) : ended ? (
                  <div className="flex items-center gap-3">
                    <button type="button" onClick={() => seekWalk(0)} className={glassButton}>
                      <span className="grid h-9 w-9 place-items-center rounded-full ring-1 ring-ivory/30">
                        <span className="ice-dot" />
                      </span>
                      Walk again
                    </button>
                    <Link to={listingPath} className="btn-glass pointer-events-auto">
                      View listing
                    </Link>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => (playing ? videoRef.current?.pause() : play())}
                    className={glassButton}
                    aria-label={playing ? "Pause the walk" : "Resume the walk"}
                  >
                    <span className="grid h-9 w-9 place-items-center rounded-full ring-1 ring-ivory/30">
                      <span className={playing ? "ice-dot animate-pulse" : "ice-dot"} />
                    </span>
                    {playing ? (nextRoom ? `Walking to the ${nextRoom.name.toLowerCase()}` : "Walking") : "Resume walking"}
                  </button>
                )
              ) : finishPressed ? (
                <Link to={listingPath} className={glassButton}>
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
            </div>
            {inRoom && (
              <div
                role="group"
                aria-label="Style"
                className={`pointer-events-auto absolute left-1/2 flex -translate-x-1/2 flex-col items-center gap-1.5 transition-opacity duration-700 ${!dark ? "opacity-100" : "opacity-0"}`}
              >
                <div className="flex items-center gap-1 rounded-full bg-night/35 p-1 ring-1 ring-ivory/15 backdrop-blur-xl">
                  {styles.map((s) => {
                    const status = s.id === "original" ? { ok: !!room.before, reason: "Original unavailable" } : styleStatus(room, s.id);
                    return (
                      <button
                        key={s.id}
                        type="button"
                        disabled={!status.ok}
                        title={status.ok ? `Restyle as ${s.label}` : status.reason}
                        aria-pressed={s.id === (chosen === "original" ? "original" : styleId)}
                        onClick={() => choose(s.id)}
                        className={`rounded-full px-3.5 py-1.5 text-[12px] tracking-wide transition disabled:cursor-not-allowed ${s.id === (chosen === "original" ? "original" : styleId) ? "bg-ivory/90 text-night" : status.ok ? "text-ivory/80 hover:text-ivory" : "text-ivory/30 line-through decoration-ivory/30"}`}
                      >
                        {s.label}
                      </button>
                    );
                  })}
                </div>
                {styles
                  .filter((s) => s.id !== "original" && !styleStatus(room, s.id).ok)
                  .map((s) => (
                    <p key={s.id} className="max-w-md text-center text-[11px] leading-snug text-ivory/45">
                      {s.label} unavailable here · {styleStatus(room, s.id).reason.split(" Not compared")[0].split(" Framing")[0]}
                    </p>
                  ))}
              </div>
            )}
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
