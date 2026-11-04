import { useEffect, useRef, useState } from "react";
import ConfirmDialog from "../ConfirmDialog";
import { Link } from "react-router-dom";
import { api, type Job, type Listing, type LivePayload } from "../../api";
import JobTerminal, { trackJob, type JobEvent } from "./JobTerminal";

type State = { status: "unknown" | "none" | "preparing" | "ready" | "failed"; error: string; progress: number; jobId: string | null };

const MAIN_TYPES = ["living", "dining"];
export const NO_MAIN_ROOM = "No main living space found in this video, so there is no room to walk into.";

/** Console control for any published listing with a main living space: prepare Live-In-It, then enter it. */
export default function LiveControl({ listing, onReady }: { listing: Listing; onReady?: () => void }) {
  const listingId = listing.id;
  const rooms = (listing.published?.rooms ?? listing.rooms).filter((r) => !r.rejected);
  const eligible = rooms.some((r) => r.main || MAIN_TYPES.includes(r.type));
  const [confirmPrepare, setConfirmPrepare] = useState(false);
  const [s, setS] = useState<State>({ status: "unknown", error: "", progress: 0, jobId: null });
  // Terminal log: the latest polled job and the console's own events.
  const [prep, setPrep] = useState<{ job: Job | null; events: JobEvent[] } | null>(null);
  const [logOpen, setLogOpen] = useState(true);
  const lastPrep = useRef<Job | null>(null);
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
      .then((p) => { if (!stopped) setS(fromPayload(p)); })
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
          if (p && p.status !== "preparing") return setS(fromPayload(p));
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

  // The Style Selector reloads whenever the residence becomes ready (first load or a re-prepare).
  useEffect(() => {
    if (s.status === "ready") onReady?.();
  }, [s.status]);

  if (s.status === "unknown") return null;

  if (s.status === "ready")
    return (
      <span className="flex flex-wrap items-center justify-center gap-1.5 max-sm:static sm:relative lg:static">
        {confirmPrepare && <ConfirmDialog message="Re-run full Live-In-It preparation? The current experience will be unavailable while it runs and could be replaced if preparation fails. Cached results may be reused; new Meta calls may use credits." onCancel={() => setConfirmPrepare(false)} onConfirm={() => { setConfirmPrepare(false); void prepare(); }} />}
        {prep && <JobTerminal title="Live-In-It preparation" job={prep.job} events={prep.events} onClose={() => setPrep(null)} className="absolute bottom-full mb-3 h-72 max-sm:inset-x-0 sm:right-0 sm:w-[min(34rem,calc(100vw-3rem))] lg:left-0 lg:right-auto" />}
        <Link to={`/p/${listingId}/live`} className="btn-glass">Enter residence</Link>
        <button type="button" className="btn-ghost text-sm text-ash hover:text-ivory" title="Rebuild Live-In-It; may use Meta credits" onClick={() => setConfirmPrepare(true)}>Re-run preparation</button>
      </span>
    );

  if (s.status === "preparing")
    return (
      <span className="max-sm:static sm:relative lg:static">
        {prep && logOpen && <JobTerminal title="Live-In-It preparation" job={prep.job} events={prep.events} onClose={() => setLogOpen(false)} className="absolute bottom-full mb-3 h-72 max-sm:inset-x-0 sm:right-0 sm:w-[min(34rem,calc(100vw-3rem))] lg:left-0 lg:right-auto" />}
        <button type="button" className="btn-glass" aria-live="polite" aria-expanded={logOpen} title={logOpen ? "Hide the preparation log" : "Show the preparation log"} onClick={() => setLogOpen((open) => !open)}>
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
    <span className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 max-sm:static sm:relative lg:static">
      {prep && <JobTerminal title="Live-In-It preparation" job={prep.job} events={prep.events} onClose={() => setPrep(null)} className="absolute bottom-full mb-3 h-72 max-sm:inset-x-0 sm:right-0 sm:w-[min(34rem,calc(100vw-3rem))] lg:left-0 lg:right-auto" />}
      {s.status === "failed" && s.error && <span className="max-w-[18rem] px-2 text-xs leading-snug text-rose">{s.error}</span>}
      <button type="button" className="btn-glass" title={s.error || undefined} onClick={prepare}>
        {s.status === "failed" ? "Retry preparation" : "Prepare Live-In-It"}
      </button>
    </span>
  );
}
