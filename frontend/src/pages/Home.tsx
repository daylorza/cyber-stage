import { useEffect, useRef, useState, type PointerEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type ListingSummary } from "../api";
import { BRAND } from "../brand";
import FloorPlan from "../components/FloorPlan";
import { RESIDENCES } from "../residences";

const REST_SCALE = 1.14;
const INSIDE_SCALE = 1.26;
const LOOK_DEGREES = 35;
const maxPan = (scale: number) => ((scale - 1) / 2) * 100 - 0.5;
const clamp = (v: number, limit: number) => Math.max(-limit, Math.min(limit, v));

function BellIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.2} aria-hidden>
      <path d="M6 16.5h12l-1.4-2.1V10a4.6 4.6 0 0 0-9.2 0v4.4L6 16.5Z" strokeLinejoin="round" />
      <path d="M10.2 18.6a1.9 1.9 0 0 0 3.6 0" strokeLinecap="round" />
    </svg>
  );
}

function factLine(summary: ListingSummary | undefined): string {
  if (!summary) return "";
  const { beds, sqft } = summary.facts;
  return [beds != null && `${beds} beds`, sqft != null && `${sqft.toLocaleString("en-US")} sq ft`, summary.price_display]
    .filter(Boolean)
    .join("  /  ");
}

export default function Home() {
  const [index, setIndex] = useState(0);
  const [listings, setListings] = useState<Record<string, ListingSummary>>({});
  const [pan, setPan] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [inside, setInside] = useState(false);
  const [concierge, setConcierge] = useState(false);
  const drag = useRef({ x: 0, pan: 0 });
  const closeTimer = useRef(0);
  const enterTimer = useRef(0);
  const navigate = useNavigate();

  const residence = RESIDENCES[index];
  const summary = listings[residence.id];
  const name = summary?.title || residence.city;
  const scale = inside ? INSIDE_SCALE : REST_SCALE;
  const heading = residence.plan.facing + (pan / maxPan(scale)) * LOOK_DEGREES;

  useEffect(() => {
    document.title = BRAND;
    api
      .listings()
      .then((items) => setListings(Object.fromEntries(items.map((i) => [i.id, i]))))
      .catch(() => setListings({}));
    return () => {
      clearTimeout(closeTimer.current);
      clearTimeout(enterTimer.current);
    };
  }, []);

  useEffect(() => setPan((p) => clamp(p, maxPan(scale))), [scale]);

  const go = (next: number) => {
    clearTimeout(enterTimer.current);
    setIndex((next + RESIDENCES.length) % RESIDENCES.length);
    setPan(0);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof SVGElement) return;
      if (e.key === "ArrowRight") go(index + 1);
      if (e.key === "ArrowLeft") go(index - 1);
      if (e.key === "Escape") {
        clearTimeout(enterTimer.current);
        setInside(false);
        setConcierge(false);
        setRevealed(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const show = () => {
    clearTimeout(closeTimer.current);
    setRevealed(true);
  };
  const hide = () => {
    closeTimer.current = window.setTimeout(() => setRevealed(false), 380);
  };

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, pan };
    setDragging(true);
    setConcierge(false);
  }
  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    const dx = ((e.clientX - drag.current.x) / window.innerWidth) * 100 * 0.6;
    setPan(clamp(drag.current.pan + dx, maxPan(scale)));
  }
  const endDrag = () => setDragging(false);

  const hud = `transition duration-700 ${inside ? "invisible opacity-0" : "visible opacity-100"}`;
  const reveal = revealed ? "visible translate-y-0 opacity-100" : "invisible -translate-y-1 opacity-0";

  return (
    <div className="fixed inset-0 overflow-hidden bg-night select-none">
      <div
        aria-hidden
        className="absolute inset-0 will-change-transform"
        style={{
          transform: `translate3d(${pan}%, 0, 0) scale(${scale})`,
          transition: dragging ? "none" : "transform 1.8s cubic-bezier(0.22, 0.7, 0.12, 1)",
        }}
      >
        {RESIDENCES.map((r, i) => (
          <img
            key={r.id}
            src={r.hero}
            alt=""
            draggable={false}
            className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-[1400ms] ease-out ${i === index ? "opacity-100" : "opacity-0"}`}
          />
        ))}
      </div>

      <div className={`pointer-events-none absolute inset-0 transition-opacity duration-1000 ${inside ? "opacity-25" : "opacity-100"}`}>
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgb(13_14_16/0.7)_0%,rgb(13_14_16/0.28)_40%,transparent_62%)]" />
        <div className="absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-night/55 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 h-[45%] bg-gradient-to-t from-night/80 via-night/30 to-transparent" />
        <div
          className={`absolute inset-0 transition-opacity duration-500 ${revealed && !inside ? "opacity-100" : "opacity-0"}`}
          style={{
            background:
              "radial-gradient(26rem 26rem at 100% 0%, rgb(13 14 16 / 0.78), rgb(13 14 16 / 0.35) 45%, transparent 75%), radial-gradient(38rem 28rem at 100% 100%, rgb(13 14 16 / 0.6), transparent 72%)",
          }}
        />
      </div>

      <div
        role="img"
        aria-label={`${name}, ${residence.city}. Drag to look around.`}
        className="absolute inset-0 cursor-grab touch-none active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      />

      <div className="legible pointer-events-none absolute inset-0">
        <div className={`absolute left-6 top-6 sm:left-10 sm:top-9 ${hud}`}>
          <Link
            to="/"
            className="pointer-events-auto text-[11px] font-medium uppercase tracking-[0.3em] text-ivory/90 transition hover:text-ivory sm:text-[13px] sm:tracking-[0.42em]"
          >
            {BRAND}
          </Link>
          <p key={residence.id} className="eyebrow mt-3 flex animate-fade-in items-center gap-2.5 text-ivory/80!">
            <span className="ice-dot" />
            {residence.city}
          </p>
        </div>

        <nav
          aria-label="Main"
          onMouseEnter={show}
          onMouseLeave={hide}
          className={`pointer-events-auto absolute right-6 top-6 flex flex-col items-end sm:right-10 sm:top-9 ${hud}`}
        >
          <button
            type="button"
            aria-label="Menu"
            aria-expanded={revealed}
            aria-controls="home-menu"
            onClick={() => (revealed ? setRevealed(false) : show())}
            className="grid h-11 w-11 place-items-center rounded-full bg-night/20 ring-1 ring-ivory/25 backdrop-blur-md transition hover:ring-ice/60"
          >
            <span className="ice-dot" />
          </button>
          <div className={`flex flex-col items-end transition duration-500 ${reveal}`}>
            <span aria-hidden className="mr-[21.5px] h-8 w-px bg-gradient-to-b from-ivory/45 to-transparent" />
            <ul id="home-menu" className="mt-1 flex flex-col items-end gap-2 rounded-2xl bg-night/30 py-2 pl-3 pr-2 backdrop-blur-md">
              {RESIDENCES.map((r, i) => (
                <li key={r.id}>
                  <button
                    type="button"
                    aria-current={i === index ? "true" : undefined}
                    onClick={() => go(i)}
                    className={`flex items-center gap-2 font-serif text-xs transition hover:text-ivory ${i === index ? "text-ivory" : "text-ivory/75"}`}
                  >
                    {i === index && <span className="ice-dot" />}
                    {r.city}
                  </button>
                </li>
              ))}
              <li className="pt-3">
                <Link to="/inventory" className="eyebrow text-ivory/70! transition hover:text-ivory!">
                  Broker console
                </Link>
              </li>
              <li>
                <Link to="/prototype-testing" className="eyebrow text-ivory/70! transition hover:text-ivory!">
                  Prototype Testing
                </Link>
              </li>
            </ul>
          </div>
        </nav>

        <div className={`absolute left-6 top-[31%] max-w-xl sm:left-10 ${hud}`}>
          <h1 className="text-[clamp(3.75rem,8.5vw,7rem)] leading-[0.92] font-[250] tracking-[-0.025em] text-ivory">Presence.</h1>
          <p className="mt-6 text-lg font-light text-ivory sm:text-xl">A different way to come home.</p>
        </div>

        <div className={`absolute inset-x-0 bottom-24 flex flex-col items-center gap-3.5 sm:bottom-9 ${hud}`}>
          <button
            type="button"
            onClick={() => {
              setInside(true);
              setRevealed(false);
              setConcierge(false);
              if (residence.id === "seed_miami" || residence.id === "seed_los_angeles") {
                clearTimeout(enterTimer.current);
                const path = residence.id === "seed_miami" ? "/p/lst_190d1a7673a8/live" : "/p/lst_190d1a7673a8/live?room=room_2";
                enterTimer.current = window.setTimeout(() => navigate(path), 900);
              }
            }}
            className="group pointer-events-auto flex items-center gap-4 rounded-full bg-ivory/[0.08] py-2 pl-2 pr-6 text-[15px] tracking-wide text-ivory ring-1 ring-ivory/25 backdrop-blur-xl transition hover:bg-ivory/[0.14] hover:ring-ivory/40"
          >
            <span className="grid h-9 w-9 place-items-center rounded-full ring-1 ring-ivory/30">
              <span className="ice-dot" />
            </span>
            Enter residence
            <span aria-hidden className="transition group-hover:translate-x-1">→</span>
          </button>
          <p className="eyebrow text-ivory/55!">Drag to look around</p>
        </div>

        <div className={`absolute bottom-10 left-6 sm:left-10 ${hud}`}>
          {concierge && (
            <div role="dialog" aria-label="Concierge" className="glass pointer-events-auto absolute bottom-14 left-0 w-72 p-5">
              <p className="eyebrow">Concierge</p>
              <p className="mt-3 font-serif text-lg">{name}</p>
              <p className="mt-2 text-sm leading-relaxed text-ivory/75">
                Private viewings are by appointment, arranged by the listing broker.
              </p>
            </div>
          )}
          <button
            type="button"
            aria-expanded={concierge}
            onClick={() => setConcierge((c) => !c)}
            className="pointer-events-auto flex items-center gap-3 text-sm tracking-wide text-ivory/85 transition hover:text-ivory"
          >
            <span className="grid h-9 w-9 place-items-center rounded-full bg-night/20 ring-1 ring-ivory/25 backdrop-blur-md">
              <BellIcon />
            </span>
            Concierge
          </button>
        </div>

        <div
          onMouseEnter={show}
          onMouseLeave={hide}
          className={`pointer-events-auto absolute bottom-10 right-10 hidden transition duration-500 md:block ${reveal} ${inside ? "invisible! opacity-0!" : ""}`}
        >
          <FloorPlan plan={residence.plan} heading={heading} label={name} />
          <div className="mt-5">
            <p className="font-serif text-xl tracking-wide text-ivory">{name}</p>
            <p className="eyebrow mt-1.5">
              {residence.city} / {residence.collection}
            </p>
            {factLine(summary) && <p className="mt-2.5 font-mono text-[11px] text-ivory/70">{factLine(summary)}</p>}
          </div>
        </div>

        <div className={`transition duration-700 ${inside ? "visible opacity-100" : "invisible opacity-0"}`}>
          <div className="absolute left-6 top-6 sm:left-10 sm:top-9">
            <p className="font-serif text-xl text-ivory/90">{name}</p>
            <p className="eyebrow mt-1.5">{residence.city}</p>
          </div>
          <button
            type="button"
            onClick={() => {
              clearTimeout(enterTimer.current);
              setInside(false);
            }}
            className="btn-glass pointer-events-auto absolute right-6 top-6 sm:right-10 sm:top-9"
          >
            Leave
          </button>
          <p className="eyebrow absolute inset-x-0 bottom-10 text-center text-ivory/60!">Drag to look around · Esc to leave</p>
        </div>
      </div>
    </div>
  );
}
