import { clock, media, type Listing } from "../api";

/** What the pipeline read from the walkthrough: coverage, the main living room, the token guard, the video it will publish. */
export default function SourcePanel({ listing }: { listing: Listing }) {
  const videos = listing.videos ?? [];
  const hasVideo = listing.uploads.some((u) => u.kind === "video");
  const main = listing.main_room;
  const guard = listing.token_guard;
  if (!hasVideo && !main) return null;
  const primary = videos.find((v) => v.status === "ready" && v.path);

  return (
    <section aria-labelledby="source-heading" className="glass grid grid-cols-1 gap-6 p-6 sm:grid-cols-[minmax(0,1fr)_auto] sm:p-7">
      <div className="min-w-0 space-y-4">
        <h2 id="source-heading" className="eyebrow">
          Walkthrough
        </h2>
        {hasVideo && videos.length === 0 && (
          <p className="text-sm text-rose">Video coverage not recorded: processed before full-video extraction. Reprocess the walkthrough.</p>
        )}
        {videos.map((v) => (
          <div key={v.upload} className="space-y-1">
            <p className="font-mono text-data text-ivory/85">
              {v.duration.toFixed(1)} s · {v.extracted} frames extracted · first {clock(v.first_t ?? 0)} · last {clock(v.last_t ?? 0)}
            </p>
            <p className="text-xs text-ash">
              {v.kept ?? v.extracted} kept after near-duplicates · 1 frame per second, whole video
            </p>
            <p className={`text-xs ${v.status === "ready" ? "text-ash" : "text-rose"}`}>
              Listing video: {v.status === "ready" ? (v.detail ?? "ready") : (v.detail ?? "not built")}
            </p>
          </div>
        ))}
        {main && (
          <p className={`text-sm ${main.found ? "text-ivory/85" : "text-rose"}`}>
            {main.found ? <span className="ice-dot mr-2.5 align-middle" /> : null}
            {main.detail}
          </p>
        )}
        {guard && <p className="text-xs text-ash">Token guard · {guard.detail}</p>}
        {primary?.note && <p className="text-xs text-ash">{primary.note}</p>}
      </div>
      {primary?.path && (
        <video
          src={media(primary.path)}
          controls
          muted
          playsInline
          preload="metadata"
          aria-label="The walkthrough video the listing page will play"
          className="max-h-64 w-full rounded-xl bg-night object-contain sm:w-auto"
          style={{ aspectRatio: primary.width && primary.height ? `${primary.width} / ${primary.height}` : undefined }}
        />
      )}
    </section>
  );
}
