import { useEffect, useState } from "react";
import ConfirmDialog from "../ConfirmDialog";
import { Link } from "react-router-dom";
import { api, type Listing, type LivePayload } from "../../api";

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
    setSelectedStyle(null);
    setStyleMessage("Starting style rerun…");
    try { setStyleJob((await api.rerunLiveStyle(listingId, room, style)).job_id); }
    catch (e) { setStyleMessage((e as Error).message); }
  }

  if (s.status === "unknown") return null;

  if (s.status === "ready")
    return (
      <span className="flex items-center gap-1.5">
        {confirmPrepare && <ConfirmDialog message="Re-run full Live-In-It preparation? The current experience will be unavailable while it runs and could be replaced if preparation fails. Cached results may be reused; new Meta calls may use credits." onCancel={() => setConfirmPrepare(false)} onConfirm={() => { setConfirmPrepare(false); void prepare(); }} />}
        <button type="button" className="btn-glass" onClick={() => setConfirmPrepare(true)}>
          Re-run preparation
        </button>
        <Link to={`/p/${listingId}/live`} className="btn-glass">Enter residence</Link>
        <details className="relative">
          <summary className="btn-glass cursor-pointer">Re-run a style</summary>
          <div className="absolute bottom-full right-0 mb-3 w-72 max-h-80 overflow-auto rounded-xl bg-night p-4 shadow-xl ring-1 ring-ivory/20">
            {payload?.rooms.filter((room) => ["living", "bedroom", "dining"].includes(room.type)).map((room) => <div key={room.id} className="mb-3"><p className="eyebrow mb-2">{room.name}</p>{payload.styles.map((style) => <button key={style.id} type="button" disabled={!!styleJob} onClick={() => setSelectedStyle({ room: room.id, roomName: room.name, style: style.id, label: style.label })} className="block w-full py-1 text-left text-sm text-ivory/80 hover:text-ivory disabled:opacity-40">{room.styles[style.id] ? "Re-run" : "Generate"} {style.label}</button>)}</div>)}
            {selectedStyle && <div className="my-3 rounded-lg bg-ivory/[0.05] p-3 ring-1 ring-ice/30">
              <p className="text-sm text-ivory">Generate {selectedStyle.label} for {selectedStyle.roomName}?</p>
              <p className="mt-2 text-xs leading-relaxed text-ivory/70">This uses Meta credits. The current image is replaced only if checks pass.</p>
              <div className="mt-3 flex gap-2">
                <button type="button" className="btn-glass" onClick={() => void rerunStyle(selectedStyle.room, selectedStyle.style)}>Confirm</button>
                <button type="button" className="btn-glass" onClick={() => setSelectedStyle(null)}>Cancel</button>
              </div>
            </div>}
            <p role="status" className="text-xs text-ivory/70">{styleJob ? "Preparing style…" : styleMessage}</p>
          </div>
        </details>
      </span>
    );

  if (s.status === "preparing")
    return (
      <button type="button" className="btn-glass" disabled aria-live="polite">
        Preparing · {Math.round(s.progress)}%
      </button>
    );

  if (!eligible)
    return (
      <span className="flex items-center gap-3 px-3">
        <button type="button" className="btn-glass" disabled title={NO_MAIN_ROOM}>
          Enter residence
        </button>
        <span className="max-w-[16rem] text-xs leading-snug text-rose/80">No main living space found in this video</span>
      </span>
    );

  return (
    <span className="flex items-center gap-3">
      {s.status === "failed" && s.error && <span className="max-w-[18rem] px-2 text-xs leading-snug text-rose/80">{s.error}</span>}
      <button type="button" className="btn-glass" title={s.error || undefined} onClick={prepare}>
        Prepare Live-In-It
      </button>
    </span>
  );
}
