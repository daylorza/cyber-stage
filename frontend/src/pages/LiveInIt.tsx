import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type LivePayload } from "../api";
import { BRAND } from "../brand";
import LiveTour from "../components/live/LiveTour";
import BrandMark from "../components/BrandMark";
import { Wordmark } from "../components/Shell";

function Quiet({ eyebrow, children }: { eyebrow: string; children?: React.ReactNode }) {
  return (
    <div className="fixed inset-0 grid place-items-center bg-night px-6">
      <div className="hud-top hud-left absolute"><Wordmark /></div>
      <div className="max-w-md text-center" role="status" aria-live="polite">
        <p className="eyebrow inline-flex items-center gap-2.5">
          <span className="ice-dot" />
          {eyebrow}
        </p>
        {children}
      </div>
    </div>
  );
}

const linkClass = "eyebrow mt-6 inline-flex min-h-11 items-center text-ivory/75! transition hover:text-ivory!";

export default function LiveInIt() {
  const { id = "" } = useParams();
  const listingPath = `/p/${id}`;
  const [payload, setPayload] = useState<LivePayload | null>(null);
  const [error, setError] = useState("");
  const [loadingScreen, setLoadingScreen] = useState(true);
  const [fadeLoader, setFadeLoader] = useState(false);

  useEffect(() => {
    if (!payload && !error) return;
    const fade = window.setTimeout(() => setFadeLoader(true), 500);
    const finish = window.setTimeout(() => setLoadingScreen(false), 1700);
    return () => { clearTimeout(fade); clearTimeout(finish); };
  }, [id, payload, error]);

  useEffect(() => {
    document.title = BRAND;
    let stopped = false;
    let timer = 0;
    const load = async () => {
      try {
        const next = await api.live(id);
        if (stopped) return;
        setPayload(next);
        setError("");
        if (next.status === "preparing") timer = window.setTimeout(load, 2000);
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
    };
    void load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [id]);

  const loader = (
    <div className={`cyber-loader fixed inset-0 z-[110] grid place-items-center ${fadeLoader ? "cyber-loader-fade" : ""}`} role="status" aria-label="Opening residence">
      <div className="cyber-loader-content text-center">
        <div className="text-sm uppercase tracking-[0.35em]"><BrandMark /></div>
        <div className="cyber-loader-track mt-8"><div className="cyber-loader-progress" /></div>
        <p className="eyebrow cyber-loader-label mt-4">Opening residence</p>
      </div>
    </div>
  );

  if (!payload && !error) return loader;

  if (error) {
    const unpublished = /isn't published/i.test(error);
    return (
      <Quiet eyebrow={unpublished ? "Not yet open" : "Live-In-It"}>
        <p className="mt-5 font-serif text-xl text-ivory/90">
          {unpublished ? "Live-In-It opens after the broker publishes this listing." : error}
        </p>
        <Link to={unpublished ? "/" : listingPath} className={linkClass}>
          {unpublished ? "Back to the residences" : "View the listing"}
        </Link>
      </Quiet>
    );
  }

  if (!payload) return null;

  if (payload.status === "preparing")
    return (
      <Quiet eyebrow="Preparing the residence">
        <p className="mt-5 text-ash">Staging each room. This takes a few minutes.</p>
      </Quiet>
    );

  if (payload.status === "failed" || payload.rooms.length === 0)
    return (
      <Quiet eyebrow="Live-In-It">
        <p className="mt-5 font-serif text-xl text-ivory/90">{payload.error ?? "This residence isn't ready to walk through."}</p>
        <Link to={listingPath} className={linkClass}>
          View the listing
        </Link>
      </Quiet>
    );

  return <><LiveTour key={payload.listing_id} payload={payload} />{fadeLoader && <div className="spatial-scan spatial-scan-fixed" aria-hidden="true"><div className="spatial-scan-grid" /><div className="spatial-scan-line" /></div>}{loadingScreen && loader}</>;
}
