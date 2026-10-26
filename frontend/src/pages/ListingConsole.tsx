import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, factLine, media, money, type Evidence, type Job, type Listing } from "../api";
import BeforeAfter from "../components/BeforeAfter";
import CompsTable from "../components/CompsTable";
import PipelineIndicator from "../components/PipelineIndicator";
import StatusMark from "../components/StatusMark";

const clean = (lines: string[]) => lines.map((l) => l.trim()).filter(Boolean);

function evidenceLabel(evidence: Evidence[] | undefined): string {
  if (!evidence?.length) return "Unsaved";
  return evidence
    .map((e) => (e.kind === "fact" ? `Fact · ${e.ref}` : e.kind === "broker" ? "Broker edit" : `Seen · ${e.ref}`))
    .join(", ");
}

function Header({ listing }: { listing: Listing }) {
  const { facts, copy, comps } = listing;
  const range = comps?.suggested_range;
  const price = facts.price
    ? money(facts.price, facts.currency)
    : range && `Guide ${money(range.low, range.currency)} – ${money(range.high, range.currency)}`;
  return (
    <header>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="eyebrow">{facts.city || "City not set"}</span>
        {listing.source === "seed" && <span className="eyebrow">Seeded hero listing</span>}
        <StatusMark status={listing.status} />
      </div>
      <h1 className="mt-4 max-w-4xl font-serif text-5xl leading-[1.05] sm:text-6xl">{copy?.title || "Untitled residence"}</h1>
      <div className="mt-5 flex flex-wrap items-center gap-x-8 gap-y-2">
        {factLine(facts) && <span className="font-mono text-sm text-ivory/75">{factLine(facts)}</span>}
        {price && <span className="font-mono text-sm text-champagne">{price}</span>}
        {facts.address && <span className="text-sm text-ash">{facts.address}</span>}
      </div>
    </header>
  );
}

function Processing({ listing, job }: { listing: Listing; job: Job | null }) {
  return (
    <section className="grid min-h-[60dvh] content-center gap-14">
      <div>
        <p className="eyebrow">Processing</p>
        <p className="mt-3 text-ash">{listing.uploads.map((u) => u.name).join(", ")}</p>
      </div>
      <PipelineIndicator job={job} />
    </section>
  );
}

function Review({ listing, onChange }: { listing: Listing; onChange: (l: Listing) => void }) {
  const copy = listing.copy!;
  const [title, setTitle] = useState(copy.title);
  const [description, setDescription] = useState(copy.description);
  const [highlights, setHighlights] = useState(copy.highlights.map((h) => h.text));
  const [rejected, setRejected] = useState<string[]>([]);
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setTitle(copy.title);
    setDescription(copy.description);
    setHighlights(copy.highlights.map((h) => h.text));
    setRejected(listing.rooms.filter((r) => r.rejected).map((r) => r.id));
  }, [listing.updated_at]);

  const locked = listing.status === "published";
  const savedRejected = listing.rooms.filter((r) => r.rejected).map((r) => r.id);
  const dirty =
    title.trim() !== copy.title ||
    description.trim() !== copy.description ||
    clean(highlights).join("\n") !== copy.highlights.map((h) => h.text).join("\n") ||
    [...rejected].sort().join() !== [...savedRejected].sort().join();
  const evidenceFor = (text: string) => copy.highlights.find((h) => h.text === text.trim())?.evidence;
  const room = listing.rooms[selected];

  async function run(name: string, call: () => Promise<Listing>) {
    setBusy(name);
    setError("");
    try {
      onChange({ ...(await call()), job: listing.job });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const review = (action: "save" | "approve" | "reject") =>
    run(action, () =>
      api.review(listing.id, { action, copy_edit: { title, description, highlights: clean(highlights) }, rejected_rooms: rejected }),
    );

  return (
    <>
      <div className="mt-14 grid gap-12 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="space-y-16">
          <section aria-labelledby="rooms-heading">
            <h2 id="rooms-heading" className="eyebrow">
              {listing.rooms.length ? `Rooms · ${listing.rooms.length} from the walkthrough` : "Rooms"}
            </h2>
            {room ? (
              <>
                <BeforeAfter key={room.id} room={room} className={`mt-4 transition ${rejected.includes(room.id) ? "opacity-40 grayscale" : ""}`} />
                <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <p className="text-lg font-light">{room.name}</p>
                    <p className="eyebrow mt-1">{room.type === "unclassified" ? "Room type pending" : room.type}</p>
                  </div>
                  {!locked && (
                    <button
                      type="button"
                      className="btn-glass"
                      aria-pressed={rejected.includes(room.id)}
                      onClick={() =>
                        setRejected((prev) => (prev.includes(room.id) ? prev.filter((id) => id !== room.id) : [...prev, room.id]))
                      }
                    >
                      {rejected.includes(room.id) ? "Include in listing" : "Exclude from listing"}
                    </button>
                  )}
                </div>
                {listing.rooms.length > 1 && (
                  <div className="mt-6 flex gap-3 overflow-x-auto pb-2" role="tablist" aria-label="Rooms">
                    {listing.rooms.map((r, i) => (
                      <button
                        key={r.id}
                        type="button"
                        role="tab"
                        aria-selected={i === selected}
                        aria-label={r.name}
                        onClick={() => setSelected(i)}
                        className={`shrink-0 overflow-hidden rounded-xl transition ${i === selected ? "ring-1 ring-ice/70" : "opacity-60 hover:opacity-100"}`}
                      >
                        <img src={media(r.before)} alt="" className={`h-16 w-28 object-cover ${rejected.includes(r.id) ? "grayscale" : ""}`} />
                      </button>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="glass mt-4 p-8 text-ash">
                {listing.source === "seed"
                  ? "Placeholder until the hero walkthrough is filmed. Facts and comps are seeded."
                  : "No rooms were found in this upload."}
              </p>
            )}
          </section>

          {listing.comps && <CompsTable comps={listing.comps} />}
        </div>

        <aside aria-labelledby="copy-heading" className="lg:sticky lg:top-28 lg:self-start">
          <div className="glass space-y-6 p-6 sm:p-8">
            <div className="flex items-baseline justify-between gap-4">
              <h2 id="copy-heading" className="eyebrow">Listing copy</h2>
              <span className="eyebrow">Only what was seen or supplied</span>
            </div>
            <label className="block">
              <span className="eyebrow mb-2 block">Title</span>
              <input className="field font-serif text-lg" value={title} disabled={locked} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label className="block">
              <span className="eyebrow mb-2 block">Description</span>
              <textarea
                className="field min-h-36 resize-y leading-relaxed"
                value={description}
                disabled={locked}
                placeholder="Describe only what the walkthrough shows or the facts state."
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <fieldset>
              <legend className="eyebrow mb-2">Highlights</legend>
              <ul className="space-y-2">
                {highlights.map((h, i) => (
                  <li key={i}>
                    <div className="flex items-center gap-2">
                      <input
                        className="field"
                        value={h}
                        disabled={locked}
                        aria-label={`Highlight ${i + 1}`}
                        onChange={(e) => setHighlights((prev) => prev.map((v, j) => (j === i ? e.target.value : v)))}
                      />
                      {!locked && (
                        <button
                          type="button"
                          aria-label={`Remove highlight ${i + 1}`}
                          onClick={() => setHighlights((prev) => prev.filter((_, j) => j !== i))}
                          className="px-2 text-ash transition hover:text-ivory"
                        >
                          ×
                        </button>
                      )}
                    </div>
                    <p className="eyebrow mt-1.5 pl-1 text-[0.6rem]! text-ice/70!">{evidenceLabel(evidenceFor(h))}</p>
                  </li>
                ))}
              </ul>
              {!locked && (
                <button type="button" className="mt-3 text-sm text-ash transition hover:text-ivory" onClick={() => setHighlights((p) => [...p, ""])}>
                  Add highlight
                </button>
              )}
            </fieldset>
          </div>
          {error && (
            <p role="alert" className="mt-4 text-sm text-rose">
              {error}
            </p>
          )}
        </aside>
      </div>

      <div className="glass fixed bottom-6 right-6 z-30 flex flex-wrap items-center gap-1.5 rounded-full! p-1.5">
        {locked ? (
          <Link to={`/p/${listing.id}`} className="btn-primary">
            View published page
          </Link>
        ) : (
          <>
            {dirty && <span className="eyebrow px-3 text-ice/80!">Unsaved edits</span>}
            <button type="button" className="btn" disabled={!dirty || !!busy} onClick={() => review("save")}>
              {busy === "save" ? "Saving" : "Save"}
            </button>
            <button type="button" className="btn text-rose" disabled={!!busy || (listing.status === "rejected" && !dirty)} onClick={() => review("reject")}>
              {busy === "reject" ? "Rejecting" : "Reject"}
            </button>
            <button type="button" className="btn-glass" disabled={!!busy || (listing.status === "approved" && !dirty)} onClick={() => review("approve")}>
              {busy === "approve" ? "Approving" : listing.status === "approved" && !dirty ? "Approved" : "Approve"}
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!!busy || listing.status !== "approved" || dirty}
              title={listing.status !== "approved" ? "Approve the listing before publishing" : undefined}
              onClick={() => run("publish", () => api.publish(listing.id))}
            >
              {busy === "publish" ? "Publishing" : "Publish"}
            </button>
          </>
        )}
      </div>
    </>
  );
}

export default function ListingConsole() {
  const { id = "" } = useParams();
  const [listing, setListing] = useState<Listing | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(
    () =>
      api.listing(id).then((l) => {
        setListing(l);
        setJob(l.job);
      }),
    [id],
  );

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  const jobId = listing?.status === "processing" ? listing.job?.id : undefined;
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer = 0;
    const tick = async () => {
      try {
        const next = await api.job(jobId);
        if (cancelled) return;
        setJob(next);
        if (next.status === "done" || next.status === "failed") return void (await load());
        timer = window.setTimeout(tick, 700);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    timer = window.setTimeout(tick, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, load]);

  if (!listing)
    return error ? (
      <p role="alert" className="text-rose">
        {error}
      </p>
    ) : (
      <p className="eyebrow">Opening listing</p>
    );

  return (
    <>
      {listing.status !== "processing" && <Header listing={listing} />}
      {error && (
        <p role="alert" className="mt-6 text-sm text-rose">
          {error}
        </p>
      )}
      {listing.status === "processing" && <Processing listing={listing} job={job} />}
      {listing.status === "failed" && (
        <section className="glass mt-12 max-w-2xl p-8">
          <p className="eyebrow text-rose!">Processing stopped</p>
          <p className="mt-3 text-lg font-light">{listing.error ?? job?.error ?? "The walkthrough couldn't be processed."}</p>
          <Link to="/new" className="btn-glass mt-6">
            Upload again
          </Link>
        </section>
      )}
      {listing.copy && !["processing", "failed"].includes(listing.status) && <Review listing={listing} onChange={setListing} />}
    </>
  );
}
