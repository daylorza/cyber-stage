import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type LivePayload } from "../../api";

type State = { status: "unknown" | "none" | "preparing" | "ready" | "failed"; error: string; progress: number; jobId: string | null };

/** Console control for the Miami hero: prepare Live-In-It, then enter it. Published listings only. */
export default function LiveControl({ listingId, city }: { listingId: string; city: string }) {
  const isMiami = city.trim().toLowerCase() === "miami";
  const [s, setS] = useState<State>({ status: "unknown", error: "", progress: 0, jobId: null });

  const fromPayload = (p: LivePayload): State => ({ status: p.status, error: p.error ?? "", progress: 0, jobId: p.job_id });

  useEffect(() => {
    if (!isMiami) return;
    let stopped = false;
    api
      .live(listingId)
      .then((p) => !stopped && setS(fromPayload(p)))
      .catch(() => !stopped && setS({ status: "none", error: "", progress: 0, jobId: null }));
    return () => {
      stopped = true;
    };
  }, [listingId, isMiami]);

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
      const { job_id } = await api.prepareLive(listingId);
      setS({ status: "preparing", error: "", progress: 0, jobId: job_id });
    } catch (e) {
      setS({ status: "failed", error: (e as Error).message, progress: 0, jobId: null });
    }
  }

  if (!isMiami || s.status === "unknown") return null;

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

  return (
    <button type="button" className="btn-glass" title={s.error || undefined} onClick={prepare}>
      Prepare Live-In-It
    </button>
  );
}
