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
        <div role="status" className="glass animate-fade-in absolute bottom-full right-0 mb-3 w-72 p-5" style={{ animationDelay: "1000ms" }}>
          <p className="font-serif text-lg text-ivory">Hold requested</p>
          <p className="mt-2 text-sm leading-relaxed text-ivory/75">
            Simulated deposit — no payment taken. The broker confirms your private showing.
          </p>
          <p className="eyebrow mt-3">Ref {reservation.id.slice(-8)}</p>
        </div>
      )}
      <button type="button" disabled={state !== "idle"} onClick={reserve} aria-label={done ? "Hold requested" : "Reserve"} className="pointer-events-auto flex min-h-11 items-center text-ivory disabled:cursor-default sm:hidden">
        <span className="flex h-[34px] items-center gap-2 rounded-full bg-ivory/[0.07] px-3 text-xs tracking-wide ring-1 ring-ivory/25 backdrop-blur-xl">Reserve<span aria-hidden className="h-3 w-3 rounded-full border border-ivory/70" /></span>
      </button>
      <button
        ref={pill}
        type="button"
        disabled={state !== "idle"}
        onClick={reserve}
        aria-label={done ? "Hold requested" : "Reserve this showing"}
        className="pointer-events-auto hidden h-14 items-center sm:flex gap-4 overflow-hidden whitespace-nowrap rounded-full bg-ivory/[0.07] pl-2 pr-6 text-left text-ivory ring-1 ring-ivory/30 backdrop-blur-xl transition-colors hover:bg-ivory/[0.12] hover:ring-ivory/60 disabled:cursor-default"
        style={{
          width: done ? 56 : (width ?? undefined),
          paddingRight: done ? 0 : undefined,
          transition: "width 700ms cubic-bezier(0.6, 0, 0.2, 1), padding 700ms, background-color 300ms, box-shadow 300ms",
        }}
      >
        <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${done ? "" : "ring-1 ring-ivory/30"}`}>
          {done ? (
            <svg viewBox="0 0 40 40" className="h-10 w-10" fill="none" stroke="#f4f1e8" strokeWidth={1.5} aria-hidden>
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
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-ivory/70" style={{ boxShadow: "0 0 10px rgb(244 241 232 / 0.5)" }} />
          )}
        </span>
        <span className="flex flex-col gap-0.5 transition-opacity duration-300" style={{ opacity: done ? 0 : 1 }}>
          <span className="text-[15px] tracking-wide">{state === "busy" ? "Requesting" : "Reserve this showing"}</span>
          <span className="font-mono text-[10px] tracking-wide text-ivory/65">Refundable hold · broker confirms</span>
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
