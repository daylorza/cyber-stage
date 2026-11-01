import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, type Reservation } from "../../api";
import { playDing, primeAudio } from "./ding";

/** Simulated hold. The broker confirms the showing; no payment is taken or requested. */
export default function ReserveControl({ listingId }: { listingId: string }) {
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState("");
  const [reservation, setReservation] = useState<Reservation | null>(null);
  const [width, setWidth] = useState<number | null>(null);
  const [faded, setFaded] = useState(false);
  const [hover, setHover] = useState(false);
  const pill = useRef<HTMLButtonElement>(null);

  useLayoutEffect(() => {
    if (pill.current && width == null && pill.current.offsetWidth) setWidth(pill.current.offsetWidth);
  }, [width]);

  useEffect(() => {
    if (state !== "done") return;
    setFaded(false);
    const timer = window.setTimeout(() => setFaded(true), 5000);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function reserve() {
    if (state !== "idle") return;
    primeAudio();
    setState("busy");
    setError("");
    try {
      const result = await api.reserve(listingId);
      setReservation(result);
      setState("done");
      playDing();
    } catch (e) {
      setError((e as Error).message);
      setState("idle");
    }
  }

  const done = state === "done";

  const showCard = done && reservation && (!faded || hover);

  return (
    <div
      className="relative flex flex-col items-end gap-3"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {showCard && (
        <div role="status" className="glass animate-fade-in absolute bottom-full left-0 mb-3 w-72 max-w-[calc(100vw-2rem)] p-5 sm:hidden" style={{ animationDelay: "1000ms" }}>
          <p className="font-serif text-lg text-ivory">Hold requested</p>
          <p className="mt-2 text-sm leading-relaxed text-ivory/75">
            Simulated deposit — no payment taken. The broker confirms your private showing.
          </p>
          <p className="eyebrow mt-3">Ref {reservation.id.slice(-8)}</p>
        </div>
      )}
      <button type="button" disabled={state !== "idle"} onClick={reserve} aria-label={done ? "Hold requested" : "Reserve"} className="btn-glass pointer-events-auto disabled:cursor-default sm:hidden">
        {done ? "Hold requested" : state === "busy" ? "Requesting" : "Reserve"}
        <span aria-hidden className={`h-3 w-3 rounded-full border border-ivory/70 ${done ? "bg-ice/70" : ""}`} />
      </button>
      <button
        ref={pill}
        type="button"
        disabled={state !== "idle"}
        onClick={reserve}
        aria-label={done ? "Hold requested" : "Reserve this showing"}
        className="pointer-events-auto relative hidden h-14 items-center overflow-hidden whitespace-nowrap rounded-full bg-ivory/[0.07] pl-2 pr-6 text-left text-ivory ring-1 ring-ivory/30 backdrop-blur-xl transition duration-300 hover:bg-ivory/[0.12] hover:ring-ivory/60 disabled:cursor-default disabled:hover:bg-ivory/[0.07] disabled:hover:ring-ivory/30 sm:flex [@media(hover:hover)]:enabled:hover:shadow-[0_0_28px_-6px_rgb(155_230_239/0.4)]"
        style={{ width: width ?? undefined }}
      >
        {done && reservation && (
          <span role="status" className="reserve-reveal absolute inset-y-0 left-6 right-16 flex min-w-0 flex-col justify-center gap-0.5">
            <span className="text-ui tracking-wide">Hold requested</span>
            <span className="truncate font-mono text-micro tracking-wide text-ivory/70">No payment taken · Ref {reservation.id.slice(-6)}</span>
          </span>
        )}
        <span
          className={`relative z-10 grid h-10 w-10 shrink-0 place-items-center rounded-full transition-transform duration-700 ease-[cubic-bezier(0.6,0,0.2,1)] ${done ? "" : "ring-1 ring-ivory/30"}`}
          style={{ transform: done && width ? `translateX(${width - 56}px)` : "none" }}
        >
          {done ? (
            <svg viewBox="0 0 40 40" className="h-10 w-10 stroke-ivory" fill="none" strokeWidth={1.5} aria-hidden>
              <circle cx={20} cy={20} r={19} pathLength={1} transform="rotate(-90 20 20)" className="live-draw" />
              <path
                d="M12.5 20.5 L18 26 L28 14.5"
                pathLength={1}
                className="live-draw"
                style={{ animationDelay: "0.75s", animationDuration: "0.5s" }}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-ivory/70 shadow-[0_0_10px_rgb(236_229_216/0.5)]" />
          )}
        </span>
        <span className="ml-4 flex flex-col gap-0.5 transition-opacity duration-200" style={{ opacity: done ? 0 : 1 }}>
          <span className="text-ui tracking-wide">{state === "busy" ? "Requesting" : "Reserve this showing"}</span>
          <span className="font-mono text-micro tracking-wide text-ivory/70">Refundable hold · broker confirms</span>
        </span>
      </button>
      {error && (
        <p role="alert" className="max-w-xs text-right text-xs text-rose">
          {error}
        </p>
      )}
    </div>
  );
}
