import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type LivePayload } from "../api";
import { BRAND } from "../brand";
import LiveTour from "../components/live/LiveTour";

function Quiet({ eyebrow, children }: { eyebrow: string; children?: React.ReactNode }) {
  return (
    <div className="fixed inset-0 grid place-items-center bg-night px-6">
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

const linkClass = "eyebrow mt-8 inline-block text-ivory/70! transition hover:text-ivory!";

export default function LiveInIt() {
  const { id = "" } = useParams();
  const listingPath = `/p/${id}`;
  const [payload, setPayload] = useState<LivePayload | null>(null);
  const [error, setError] = useState("");

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

  if (!payload) return <Quiet eyebrow="Opening residence" />;

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

  return <LiveTour key={payload.listing_id} payload={payload} />;
}
