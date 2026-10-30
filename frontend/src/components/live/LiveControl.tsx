import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Listing, type LivePayload } from "../../api";

type State = { status: "unknown" | "none" | "preparing" | "ready" | "failed"; error: string; progress: number; jobId: string | null };

const MAIN_TYPES = ["living", "dining"];
export const NO_MAIN_ROOM = "No main living space found in this video, so there is no room to walk into.";

/** Console control for any published listing with a main living space: prepare Live-In-It, then enter it. */
export default function LiveControl({ listing }: { listing: Listing }) {
  const listingId = listing.id;
  const isMiami = listing.facts.city.trim().toLowerCase() === "miami";
  const rooms = (listing.published?.rooms ?? listing.rooms).filter((r) => !r.rejected);
  const eligible = rooms.some((r) => r.main || MAIN_TYPES.includes(r.type));
  const [s, setS] = useState<State>({ status: "unknown", error: "", progress: 0, jobId: null });

  const fromPayload = (p: LivePayload): State => ({ status: p.status, error: p.error ?? "", progress: 0, jobId: p.job_id });

  useEffect(() => {
    let stopped = false;
    api
      .live(listingId)
      .then((p) => !stopped && setS(fromPayload(p)))
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
    setS({ status: "preparing", error: "", progress: 0, jobId: null });
    try {
      // A Miami listing also stands in for the seeded home-page residence.
      const { job_id } = await api.prepareLive(listingId, isMiami ? "seed_miami" : null);
      setS({ status: "preparing", error: "", progress: 0, jobId: job_id });
    } catch (e) {
      setS({ status: "failed", error: (e as Error).message, progress: 0, jobId: null });
    }
  }

  if (s.status === "unknown") return null;

  if (s.status === "ready")
    return (
      <Link to={`/p/${listingId}/live`} className="btn-glass">
        Enter residence
      </Link>
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
