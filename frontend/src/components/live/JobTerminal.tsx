import { useEffect, useRef } from "react";
import type { Job, JobLogEntry } from "../../api";
import { modelName } from "../trust";

/** A line the console adds itself, between Meta calls: job started, stage changed, done. */
export type JobEvent = { at: string; text: string; tone?: "info" | "ok" | "fail" };

const PURPOSE: Record<string, string> = {
  "image.stage": "Stage the room",
  "image.empty": "Empty-room plate",
  "image.moment": "Moment image",
  "sam.faces": "Privacy check · faces",
  "sam.plate": "Plate mask",
  "sam.structure": "Structure check",
  "sam.pieces": "Furniture cutouts",
  "sam.focus": "Focus point",
};

const time = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--:--:--" : d.toLocaleTimeString("en-GB", { hour12: false });
};

const nowIso = () => new Date().toISOString();

/** Adds console-side events when a polled job's stage or status changes. */
export function trackJob(prev: Job | null, next: Job, push: (e: JobEvent) => void) {
  if (!prev) push({ at: nowIso(), text: `Job ${next.id.slice(-6)} queued` });
  if (next.stage && next.stage !== prev?.stage && next.status === "running") {
    const stage = next.stage.replace(/^live:/, "");
    push({ at: nowIso(), text: `${stage === "moments" ? "Preparing moments" : `Room ${stage}`} · ${Math.round(next.progress)}%` });
  }
  if (next.status !== prev?.status && next.status === "done") push({ at: nowIso(), text: "Done · checks passed, result attached", tone: "ok" });
  if (next.status !== prev?.status && next.status === "failed") push({ at: nowIso(), text: next.error ?? "Stopped", tone: "fail" });
}

function target(t: Record<string, unknown>) {
  return [t.room, t.style, t.concept].filter((v) => typeof v === "string").join(" · ");
}

function CallLine({ e, running }: { e: JobLogEntry; running: boolean }) {
  const purpose = e.purpose.replace(/^live\./, "");
  const state = running ? "…" : e.error ? "✕" : e.ok ? "✓" : "–";
  return (
    <li className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] gap-x-3">
      <span className="text-ash">{time(e.at)}</span>
      <span className="min-w-0">
        <span className="text-ice/90">{modelName(e.model)}</span> <span className="text-ivory/85">{PURPOSE[purpose] ?? purpose}</span>
        {target(e.target) && <span className="text-ash"> · {target(e.target)}</span>}
        {e.error && <span className="block text-rose">{e.error}</span>}
      </span>
      <span className={`tabular-nums ${running ? "animate-pulse text-ice" : e.error ? "text-rose" : "text-ash"}`}>
        {running ? state : `${e.cached ? "cached" : `${(e.ms / 1000).toFixed(1)}s`} ${state}`}
      </span>
    </li>
  );
}

/** Terminal-style log of a Live-In job: Meta calls as they happen, plus stage changes. */
export default function JobTerminal({ title, job, events, onClose, className = "" }: { title: string; job: Job | null; events: JobEvent[]; onClose?: () => void; className?: string }) {
  const body = useRef<HTMLDivElement>(null);
  const calls = job?.log ?? [];
  const running = job ? job.status === "queued" || job.status === "running" : true;
  const lines = [
    ...events.map((e) => ({ at: e.at, event: e })),
    ...calls.map((c, i) => ({ at: c.at, call: c, last: i === calls.length - 1 })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  useEffect(() => {
    const el = body.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length, calls[calls.length - 1]?.ms]);

  return (
    <div className={`flex min-h-0 flex-col overflow-hidden rounded-xl bg-[rgb(8_9_11/0.96)] text-left ring-1 ring-ivory/15 shadow-[0_24px_60px_-30px_rgb(0_0_0/0.9)] ${className}`}>
      <div className="flex items-center gap-2 border-b border-ivory/10 px-3 py-2">
        <span aria-hidden className="flex gap-1.5">
          <span className="h-2 w-2 rounded-full bg-ivory/15" />
          <span className="h-2 w-2 rounded-full bg-ivory/15" />
          <span className={`h-2 w-2 rounded-full ${running ? "animate-pulse bg-ice" : job?.status === "failed" ? "bg-rose" : "bg-verdant"}`} />
        </span>
        <p className="data-label min-w-0 flex-1 truncate text-ivory/70">{title}</p>
        {job && <p className="font-mono text-micro tabular-nums text-ash">{calls.length} calls · {Math.round(job.progress)}%</p>}
        {onClose && <button type="button" aria-label="Close log" onClick={onClose} className="-my-1 -mr-1 grid h-7 w-7 place-items-center rounded-full text-ivory/60 transition hover:bg-ivory/10 hover:text-ivory pointer-coarse:h-10 pointer-coarse:w-10">×</button>}
      </div>
      {job && (
        <div aria-hidden className="h-px bg-ivory/10">
          <div className="h-px bg-ice/70 transition-[width] duration-500" style={{ width: `${Math.max(2, job.progress)}%` }} />
        </div>
      )}
      <div ref={body} role="log" aria-label={`${title} log`} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-3 font-mono text-micro leading-relaxed sm:text-caption">
        <ul className="space-y-1">
          {lines.map((l, i) =>
            "event" in l ? (
              <li key={`e${i}`} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3">
                <span className="text-ash">{time(l.at)}</span>
                <span className={l.event.tone === "ok" ? "text-verdant" : l.event.tone === "fail" ? "text-rose" : "text-champagne"}>› {l.event.text}</span>
              </li>
            ) : (
              <CallLine key={`c${i}`} e={l.call} running={running && l.last && !l.call.ms && !l.call.ok && !l.call.error} />
            ),
          )}
          {running && <li className="text-ice"><span className="animate-pulse">▍</span></li>}
        </ul>
      </div>
    </div>
  );
}
