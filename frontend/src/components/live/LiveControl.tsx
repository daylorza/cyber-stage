import { useEffect, useRef, useState } from "react";
import ConfirmDialog from "../ConfirmDialog";
import { Link } from "react-router-dom";
import { api, type Job, type Listing, type LivePayload } from "../../api";
import JobTerminal, { trackJob, type JobEvent } from "./JobTerminal";

type State = { status: "unknown" | "none" | "preparing" | "ready" | "failed"; error: string; progress: number; jobId: string | null };

const MAIN_TYPES = ["living", "dining"];
export const NO_MAIN_ROOM = "No main living space found in this video, so there is no room to walk into.";

/** Console control for any published listing with a main living space: prepare Live-In-It, then enter it. */
export default function LiveControl({ listing }: { listing: Listing }) {
  const listingId = listing.id;
  const rooms = (listing.published?.rooms ?? listing.rooms).filter((r) => !r.rejected);
  const eligible = rooms.some((r) => r.main || MAIN_TYPES.includes(r.type));
  const [confirmPrepare, setConfirmPrepare] = useState(false);
  const [payload, setPayload] = useState<LivePayload | null>(null);
  const [styleJob, setStyleJob] = useState<string | null>(null);
  const [styleMessage, setStyleMessage] = useState("");
  const [selectedStyle, setSelectedStyle] = useState<{ room: string; roomName: string; style: string; label: string } | null>(null);
  const [s, setS] = useState<State>({ status: "unknown", error: "", progress: 0, jobId: null });
  // Terminal logs: the latest polled job and the console's own events, per kind of job.
  const [prep, setPrep] = useState<{ job: Job | null; events: JobEvent[] } | null>(null);
  const [styleRun, setStyleRun] = useState<{ title: string; job: Job | null; events: JobEvent[] } | null>(null);
  const lastPrep = useRef<Job | null>(null);
  const lastStyle = useRef<Job | null>(null);
  const observe = (last: { current: Job | null }, job: Job) => {
    const events: JobEvent[] = [];
    trackJob(last.current, job, (e) => events.push(e));
    last.current = job;
    return events;
  };

  const fromPayload = (p: LivePayload): State => ({ status: p.status, error: p.error ?? "", progress: 0, jobId: p.job_id });

  useEffect(() => {
    let stopped = false;
    api
      .live(listingId)
      .then((p) => { if (!stopped) { setPayload(p); setS(fromPayload(p)); } })
      .catch(() => !stopped && setS({ status: "none", error: "", progress: 0, jobId: null }));
    return () => {
      stopped = true;
    };
  }, [listingId]);

  const jobId = s.status === "preparing" ? s.jobId : null;
  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    let timer = 0;
    const tick = async () => {
      try {
        const job = await api.job(jobId);
        if (stopped) return;
        const fresh = observe(lastPrep, job);
        setPrep((prev) => ({ job, events: [...(prev?.events ?? []), ...fresh] }));
        if (job.status === "done" || job.status === "failed") {
          const p = await api.live(listingId).catch(() => null);
          if (stopped) return;
          if (p && p.status !== "preparing") { setPayload(p); return setS(fromPayload(p)); }
          return setS({ status: "failed", error: job.error ?? p?.error ?? "Live-In-It couldn't be prepared.", progress: 0, jobId: null });
        }
        setS((prev) => ({ ...prev, progress: job.progress }));
        timer = window.setTimeout(tick, 1000);
      } catch (e) {
        if (!stopped) setS({ status: "failed", error: (e as Error).message, progress: 0, jobId: null });
      }
    };
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [jobId, listingId]);

  async function prepare() {
    lastPrep.current = null;
    setPrep({ job: null, events: [{ at: new Date().toISOString(), text: "Requesting Live-In-It preparation" }] });
    setS({ status: "preparing", error: "", progress: 0, jobId: null });
    try {
      // Seeded home-page residences are removed: always prepare without a residence link.
      const { job_id } = await api.prepareLive(listingId, null);
      setS({ status: "preparing", error: "", progress: 0, jobId: job_id });
    } catch (e) {
      setS({ status: "failed", error: (e as Error).message, progress: 0, jobId: null });
    }
  }

  useEffect(() => {
    if (!styleJob) return;
    let stopped = false;
    let timer = 0;
    const tick = async () => {
      try {
        const job = await api.job(styleJob);
        if (stopped) return;
        const fresh = observe(lastStyle, job);
        setStyleRun((prev) => prev && { ...prev, job, events: [...prev.events, ...fresh] });
        if (job.status === "done" || job.status === "failed") {
          setStyleMessage(job.status === "done" ? "Style updated." : (job.error ?? "Style rerun failed; previous image retained."));
          setStyleJob(null);
          if (job.status === "done") setPayload(await api.live(listingId));
        } else timer = window.setTimeout(tick, 1000);
      } catch (e) {
        if (!stopped) { setStyleMessage((e as Error).message); setStyleJob(null); }
      }
    };
    void tick();
    return () => { stopped = true; clearTimeout(timer); };
  }, [styleJob, listingId]);

  async function rerunStyle(room: string, style: string) {
    const picked = selectedStyle;
    lastStyle.current = null;
    setStyleRun({ title: `Style · ${picked?.label ?? style} · ${picked?.roomName ?? room}`, job: null, events: [{ at: new Date().toISOString(), text: `Requesting ${picked?.label ?? style} for ${picked?.roomName ?? room}` }] });
    setSelectedStyle(null);
    setStyleMessage("Starting style rerun…");
    try { setStyleJob((await api.rerunLiveStyle(listingId, room, style)).job_id); }
    catch (e) { setStyleMessage((e as Error).message); }
  }

  if (s.status === "unknown") return null;

  if (s.status === "ready")
    return (
      <span className="flex flex-wrap items-center justify-center gap-1.5 max-sm:static sm:relative">
        {confirmPrepare && <ConfirmDialog message="Re-run full Live-In-It preparation? The current experience will be unavailable while it runs and could be replaced if preparation fails. Cached results may be reused; new Meta calls may use credits." onCancel={() => setConfirmPrepare(false)} onConfirm={() => { setConfirmPrepare(false); void prepare(); }} />}
        {prep && <JobTerminal title="Live-In-It preparation" job={prep.job} events={prep.events} onClose={() => setPrep(null)} className="absolute bottom-full mb-3 h-72 max-sm:inset-x-0 sm:right-0 sm:w-[min(34rem,calc(100vw-3rem))]" />}
        <Link to={`/p/${listingId}/live`} className="btn-glass">Enter residence</Link>
        <details className="group max-sm:static sm:relative">
          <summary className="btn-glass cursor-pointer list-none [&::-webkit-details-marker]:hidden">More <span aria-hidden className="inline-block text-ivory/60 transition group-open:rotate-180">⌃</span></summary>
          <div className={`absolute bottom-full mb-3 grid max-h-[min(32rem,75dvh)] grid-cols-1 gap-4 overflow-auto rounded-2xl bg-night/95 p-4 shadow-xl ring-1 ring-ivory/20 backdrop-blur-xl max-sm:inset-x-0 sm:right-0 ${styleRun ? "sm:w-[min(48rem,calc(100vw-3rem))] sm:grid-cols-[18rem_minmax(0,1fr)] sm:overflow-hidden" : "sm:w-80"}`}>
            <div className="min-w-0 sm:overflow-y-auto">
            <button type="button" onClick={() => setConfirmPrepare(true)} className="block w-full rounded-lg px-2 py-2 text-left text-sm text-ivory/85 transition hover:bg-ivory/[0.05] hover:text-ivory pointer-coarse:py-3">
              Re-run preparation
              <span className="block text-xs text-ash">Rebuilds Live-In-It; may use Meta credits</span>
            </button>
            <div className="my-3 h-px bg-ivory/10" />
            <p className="eyebrow mb-2 px-2">Re-run a style</p>
            {payload?.rooms.filter((room) => ["living", "bedroom", "dining"].includes(room.type)).map((room) => <div key={room.id} className="mb-3 px-2"><p className="mb-1 text-xs text-ivory/60">{room.name}</p>{payload.styles.map((style) => <button key={style.id} type="button" disabled={!!styleJob} onClick={() => setSelectedStyle({ room: room.id, roomName: room.name, style: style.id, label: style.label })} className="block w-full py-1 text-left text-sm text-ivory/80 transition hover:text-ivory disabled:opacity-40 pointer-coarse:py-3">{room.styles[style.id] ? "Re-run" : "Generate"} {style.label}</button>)}</div>)}
            {selectedStyle && <div className="my-3 rounded-lg bg-ivory/[0.05] p-3 ring-1 ring-ice/30">
              <p className="text-sm text-ivory">Generate {selectedStyle.label} for {selectedStyle.roomName}?</p>
              <p className="mt-2 text-xs leading-relaxed text-ivory/70">This uses Meta credits. The current image is replaced only if checks pass.</p>
              <div className="mt-3 flex gap-2">
                <button type="button" className="btn-glass" onClick={() => void rerunStyle(selectedStyle.room, selectedStyle.style)}>Confirm</button>
                <button type="button" className="btn-glass" onClick={() => setSelectedStyle(null)}>Cancel</button>
              </div>
            </div>}
            <p role="status" className="px-2 text-xs text-ivory/70">{styleJob ? "Preparing style…" : styleMessage}</p>
            </div>
            {styleRun && <JobTerminal title={styleRun.title} job={styleRun.job} events={styleRun.events} onClose={styleJob ? undefined : () => setStyleRun(null)} className="h-72 sm:h-auto sm:min-h-[22rem]" />}
          </div>
        </details>
      </span>
    );

  if (s.status === "preparing")
    return (
      <span className="max-sm:static sm:relative">
        {prep && <JobTerminal title="Live-In-It preparation" job={prep.job} events={prep.events} className="absolute bottom-full mb-3 h-72 max-sm:inset-x-0 sm:right-0 sm:w-[min(34rem,calc(100vw-3rem))]" />}
        <button type="button" className="btn-glass" disabled aria-live="polite">
          Preparing · {Math.round(s.progress)}%
        </button>
      </span>
    );

  if (!eligible)
    return (
      <span className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 px-3">
        <button type="button" className="btn-glass" disabled title={NO_MAIN_ROOM}>
          Enter residence
        </button>
        <span className="max-w-[16rem] text-xs leading-snug text-rose">No main living space found in this video</span>
      </span>
    );

  return (
    <span className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 max-sm:static sm:relative">
      {prep && <JobTerminal title="Live-In-It preparation" job={prep.job} events={prep.events} onClose={() => setPrep(null)} className="absolute bottom-full mb-3 h-72 max-sm:inset-x-0 sm:right-0 sm:w-[min(34rem,calc(100vw-3rem))]" />}
      {s.status === "failed" && s.error && <span className="max-w-[18rem] px-2 text-xs leading-snug text-rose">{s.error}</span>}
      <button type="button" className="btn-glass" title={s.error || undefined} onClick={prepare}>
        Prepare Live-In-It
      </button>
    </span>
  );
}
