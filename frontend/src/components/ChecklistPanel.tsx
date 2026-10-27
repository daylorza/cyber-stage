import { useState } from "react";
import { api, shortTime, type Listing, type MetaStatus } from "../api";
import { StatusDot, STATUS_TEXT, STATUS_WORD } from "./trust";

export const openItems = (listing: Listing) => listing.checklist.items.filter((i) => i.status !== "done");

function Summary({ listing, live }: { listing: Listing; live: boolean }) {
  const open = openItems(listing);
  const trouble = open.some((i) => i.status === "flagged" || i.status === "failed");
  if (live) return <span className="eyebrow text-ice/80!">Filling in · {listing.checklist.items.length - open.length} of {listing.checklist.items.length} ready</span>;
  if (!open.length && listing.verification?.passed)
    return <span className="eyebrow text-ice!">All checks passed · {shortTime(listing.verification.ran_at)}</span>;
  if (!open.length) return <span className="eyebrow text-ivory/70!">Awaiting verification</span>;
  return <span className={`eyebrow ${trouble ? "text-rose!" : "text-ivory/70!"}`}>Publish blocked · {open.length} open</span>;
}

export default function ChecklistPanel({
  listing,
  meta,
  live = false,
  onRerun,
}: {
  listing: Listing;
  meta?: MetaStatus | null;
  live?: boolean;
  onRerun?: () => void;
}) {
  const [busy, setBusy] = useState<"verify" | "reprocess" | null>(null);
  const [error, setError] = useState("");
  const canAct = !live && listing.source === "upload" && listing.status !== "published";

  async function act(kind: "verify" | "reprocess") {
    if (kind === "reprocess" && !window.confirm("Reprocess the walkthrough? This replaces the current draft and any edits to it.")) return;
    setBusy(kind);
    setError("");
    try {
      await (kind === "verify" ? api.verify(listing.id) : api.reprocess(listing.id));
      onRerun?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="checks-heading" className="glass p-6 sm:p-7">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="checks-heading" className="eyebrow">Pipeline checks</h2>
        <span aria-live="polite">
          <Summary listing={listing} live={live} />
        </span>
      </div>

      <ol className="mt-5 space-y-3">
        {listing.checklist.items.map((item) => {
          const loud = item.status === "flagged" || item.status === "failed";
          return (
            <li key={item.id} className="grid grid-cols-[0.375rem_minmax(0,1fr)] items-start gap-x-3.5">
              <span className="mt-[7px]">
                <StatusDot status={item.status} />
              </span>
              <div className="flex min-w-0 items-baseline justify-between gap-4">
                <span className={`shrink-0 text-[13px] ${STATUS_TEXT[item.status]}`}>
                  {item.label}
                  <span className="sr-only"> ({STATUS_WORD[item.status]})</span>
                </span>
                {!loud && item.detail && (
                  <span title={item.detail} className="min-w-0 truncate text-right text-xs text-ash">
                    {item.detail}
                  </span>
                )}
              </div>
              {loud && item.detail && <p className="col-start-2 mt-0.5 text-xs text-rose/75">{item.detail}</p>}
            </li>
          );
        })}
      </ol>

      {meta && !meta.configured && (
        <p className="mt-5 text-xs text-ash">Meta Model API not configured. Meta steps can't run, so publishing stays blocked.</p>
      )}

      {canAct && (
        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-1">
          <button type="button" disabled={!!busy} onClick={() => act("verify")} className="text-xs text-ash transition hover:text-ivory disabled:opacity-40">
            {busy === "verify" ? "Starting checks" : "Re-run checks"}
          </button>
          <button type="button" disabled={!!busy} onClick={() => act("reprocess")} className="text-xs text-ash transition hover:text-ivory disabled:opacity-40">
            {busy === "reprocess" ? "Starting" : "Reprocess walkthrough"}
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-3 text-xs text-rose">
          {error}
        </p>
      )}
    </section>
  );
}
