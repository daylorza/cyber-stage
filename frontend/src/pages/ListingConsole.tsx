import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, factLine, media, money, type Job, type Listing, type MetaStatus } from "../api";
import AttentionList from "../components/AttentionList";
import BeforeAfter from "../components/BeforeAfter";
import ChecklistPanel, { openItems } from "../components/ChecklistPanel";
import CompsTable from "../components/CompsTable";
import DecisionPanel from "../components/DecisionPanel";
import PipelineIndicator from "../components/PipelineIndicator";
import LiveControl from "../components/live/LiveControl";
import StatusMark from "../components/StatusMark";
import { ClaimTrust, EvidenceBlock, ITEM_SHORT, ResultLine, roomIssues } from "../components/trust";

const clean = (lines: string[]) => lines.map((l) => l.trim()).filter(Boolean);

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
      <h1 className="mt-4 max-w-4xl font-serif text-5xl leading-[1.05]">{copy?.title || "Untitled residence"}</h1>
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
    <section className="grid min-h-[60dvh] items-center gap-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
      <div className="grid content-center gap-14">
        <div aria-live="polite">
          <p className="eyebrow">
            {job?.kind === "restage" ? "Re-staging with a stricter prompt" : job?.kind === "verify" ? "Re-running independent checks" : "Processing"}
          </p>
          <p className="mt-3 text-ash">{listing.uploads.map((u) => u.name).join(", ")}</p>
        </div>
        <PipelineIndicator job={job} />
      </div>
      <ChecklistPanel listing={listing} live />
    </section>
  );
}

function Review({
  listing,
  meta,
  onChange,
  reload,
}: {
  listing: Listing;
  meta: MetaStatus | null;
  onChange: (l: Listing) => void;
  reload: () => void;
}) {
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
  const claimFor = (text: string) => copy.highlights.find((h) => h.text === text.trim());
  const room = listing.rooms[selected];
  const checks = listing.verification?.checks ?? [];
  const stagingFlagged =
    !!room &&
    (roomIssues(checks, room.id).some((c) => c.item === "staging_geometry") || !!room.staging?.error);
  const restageLevel = room?.staging?.level ?? 0;
  const open = openItems(listing);
  const blocked = open.length > 0;
  const descriptionClean = description.trim() === copy.description;
  const blockedHint = `Resolve first: ${open.map((i) => i.label).join(", ")}${dirty ? ". Save your edits to re-run the checks." : ""}`;
  const publishHint =
    listing.status !== "approved"
      ? "Approve the listing before publishing"
      : dirty
        ? "Save your edits first"
        : blocked
          ? blockedHint
          : !listing.verification?.passed
            ? "Independent verification has not passed"
            : undefined;

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

  const restage = async () => {
    if (!room) return;
    if (
      !window.confirm(
        `Re-stage ${room.name} with a stricter prompt? Only this room changes. This clears approval and makes a new Meta Image call.`,
      )
    )
      return;
    setBusy("restage");
    setError("");
    try {
      await api.restage(listing.id, room.id);
      reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const focusClaim = (id: string) => {
    const el = document.querySelector<HTMLElement>(`[data-claim~="${id}"]`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    el?.focus({ preventScroll: true });
  };

  const pickRoom = (id: string) => {
    const i = listing.rooms.findIndex((r) => r.id === id);
    if (i < 0) return;
    setSelected(i);
    document.getElementById("rooms-heading")?.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  return (
    <>
      <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="space-y-10">
          <Header listing={listing} />
          {listing.source === "upload" ? (
            <AttentionList listing={listing} onClaim={focusClaim} onRoom={pickRoom} />
          ) : (
            <p className="max-w-md text-sm text-ash">Seeded placeholder. The pipeline has not run on footage, so publishing stays blocked.</p>
          )}
        </div>
        <ChecklistPanel listing={listing} meta={meta} onRerun={reload} />
      </div>

      <div className="mt-12 grid gap-12 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="space-y-16">
          <section aria-labelledby="rooms-heading" className="scroll-mt-28">
            <h2 id="rooms-heading" className="eyebrow">
              {listing.rooms.length ? `Rooms · ${listing.rooms.length} from the walkthrough` : "Rooms"}
            </h2>
            {room ? (
              <>
                <BeforeAfter key={room.id} room={room} className={`mt-4 transition ${rejected.includes(room.id) ? "opacity-40 grayscale" : ""}`} />
                <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
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
                {(roomIssues(checks, room.id).length > 0 || room.staging?.error || room.restage_error) && (
                  <div className="mt-3 space-y-1.5" role="status">
                    {roomIssues(checks, room.id).map((c) => (
                      <ResultLine
                        key={c.id}
                        tone="fail"
                        label={`${ITEM_SHORT[c.item] ?? c.item}${c.target.side ? ` · ${String(c.target.side)}` : ""}`}
                        reason={c.reason}
                      />
                    ))}
                    {room.staging?.error && <ResultLine tone="fail" label="Staging" reason={room.staging.error} />}
                    {room.restage_error && <ResultLine tone="fail" label="Re-stage" reason={room.restage_error.error} />}
                    {!locked && !rejected.includes(room.id) && stagingFlagged && (
                      <div className="pl-3 pt-1">
                        {restageLevel < 2 ? (
                          <>
                            <button
                              type="button"
                              className="btn-glass"
                              disabled={!!busy || dirty}
                              title={dirty ? "Save your edits first" : undefined}
                              onClick={restage}
                            >
                              {busy === "restage" ? "Queueing" : "Re-stage with a stricter prompt"}
                            </button>
                            <p className="mt-1.5 text-xs text-ash">Attempt {restageLevel + 1} of 2 · only this room changes</p>
                          </>
                        ) : (
                          <p className="text-xs text-ash">Stricter re-stage tried twice. Exclude this room or re-film it.</p>
                        )}
                      </div>
                    )}
                    {!locked && !rejected.includes(room.id) && <p className="pl-3 text-xs text-ash">Exclude this room to remove it from the listing.</p>}
                  </div>
                )}
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
                        className={`relative shrink-0 overflow-hidden rounded-xl transition ${i === selected ? "ring-1 ring-ice/70" : "opacity-60 hover:opacity-100"}`}
                      >
                        {r.before ? (
                          <img src={media(r.before)} alt="" className={`h-16 w-28 object-cover ${rejected.includes(r.id) ? "grayscale" : ""}`} />
                        ) : (
                          <span className="eyebrow grid h-16 w-28 place-items-center bg-smoke px-2 text-center text-[0.55rem]! leading-snug">Held back</span>
                        )}
                        {roomIssues(checks, r.id).length > 0 && <span aria-hidden className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-rose" />}
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

        <aside aria-labelledby="copy-heading">
          <div className="glass space-y-6 p-6 sm:p-8">
            <div className="flex items-baseline justify-between gap-4">
              <h2 id="copy-heading" className="eyebrow">Listing copy</h2>
              <span className="eyebrow">Only what was seen or supplied</span>
            </div>
            <label className="block">
              <span className="eyebrow mb-2 block">Title</span>
              <input data-claim="title" className="field font-serif text-lg" value={title} disabled={locked} onChange={(e) => setTitle(e.target.value)} />
              {title.trim() === copy.title ? (
                <EvidenceBlock id="title" evidence={copy.evidence.title ?? []} listing={listing} className="mt-2 pl-1" />
              ) : (
                <ClaimTrust claim={undefined} listing={listing} className="mt-2 pl-1" />
              )}
            </label>
            <div>
              <label className="block">
                <span className="eyebrow mb-2 block">Description</span>
                <textarea
                  data-claim={copy.sentences.map((c) => c.id).join(" ")}
                  className="field min-h-36 resize-y leading-relaxed"
                  value={description}
                  disabled={locked}
                  placeholder="Describe only what the walkthrough shows or the facts state."
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
              {descriptionClean && copy.sentences.length > 0 ? (
                <ul className="mt-3 space-y-3 pl-1">
                  {copy.sentences.map((c) => (
                    <li key={c.id ?? c.text}>
                      <p className="line-clamp-1 text-xs text-ivory/60">{c.text}</p>
                      <EvidenceBlock id={c.id} evidence={c.evidence} listing={listing} className="mt-0.5" />
                    </li>
                  ))}
                </ul>
              ) : (
                description.trim() !== "" && <ClaimTrust claim={undefined} listing={listing} className="mt-2 pl-1" />
              )}
            </div>
            <fieldset>
              <legend className="eyebrow mb-2">Highlights</legend>
              <ul className="space-y-4">
                {highlights.map((h, i) => {
                  const claim = claimFor(h);
                  return (
                    <li key={i}>
                      <div className="flex items-center gap-2">
                        <input
                          data-claim={claim?.id}
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
                      <ClaimTrust claim={claim} listing={listing} className="mt-2 pl-1" />
                    </li>
                  );
                })}
              </ul>
              {!locked && (
                <button type="button" className="mt-4 text-sm text-ash transition hover:text-ivory" onClick={() => setHighlights((p) => [...p, ""])}>
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

      <DecisionPanel listing={listing} />

      <div className="glass fixed bottom-6 right-6 z-30 flex flex-wrap items-center gap-1.5 rounded-full! p-1.5">
        {locked ? (
          <>
            <LiveControl listingId={listing.id} city={listing.facts.city} />
            <Link to={`/p/${listing.id}`} className="btn-primary">
              View published page
            </Link>
          </>
        ) : (
          <>
            {dirty && <span className="eyebrow px-3 text-ice/80!">Unsaved edits</span>}
            <button type="button" className="btn" disabled={!dirty || !!busy} onClick={() => review("save")}>
              {busy === "save" ? "Saving" : "Save"}
            </button>
            <button type="button" className="btn text-rose" disabled={!!busy || (listing.status === "rejected" && !dirty)} onClick={() => review("reject")}>
              {busy === "reject" ? "Rejecting" : "Reject"}
            </button>
            <button
              type="button"
              className="btn-glass"
              disabled={!!busy || blocked || (listing.status === "approved" && !dirty)}
              title={blocked ? blockedHint : undefined}
              aria-describedby={blocked ? "action-hint" : undefined}
              onClick={() => review("approve")}
            >
              {busy === "approve" ? "Approving" : listing.status === "approved" && !dirty ? "Approved" : "Approve"}
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!!busy || !!publishHint}
              title={publishHint}
              aria-describedby={publishHint ? "action-hint" : undefined}
              onClick={() => run("publish", () => api.publish(listing.id))}
            >
              {busy === "publish" ? "Publishing" : "Publish"}
            </button>
          </>
        )}
      </div>
      <p id="action-hint" className="sr-only">
        {publishHint ?? (blocked ? blockedHint : "")}
      </p>
    </>
  );
}

export default function ListingConsole() {
  const { id = "" } = useParams();
  const [listing, setListing] = useState<Listing | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [meta, setMeta] = useState<MetaStatus | null>(null);
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

  useEffect(() => {
    api.metaStatus().then(setMeta).catch(() => setMeta(null));
  }, []);

  const jobId = listing?.status === "processing" ? listing.job?.id : undefined;
  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    let jobTimer = 0;
    let listingTimer = 0;
    const tickJob = async () => {
      try {
        const next = await api.job(jobId);
        if (stopped) return;
        setJob(next);
        if (next.status === "done" || next.status === "failed") {
          stopped = true;
          clearTimeout(listingTimer);
          return void (await load());
        }
        jobTimer = window.setTimeout(tickJob, 700);
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
    };
    const tickListing = async () => {
      const next = await api.listing(id).catch(() => null);
      if (next && !stopped) setListing((prev) => (prev ? { ...next, job: prev.job } : next));
      if (!stopped) listingTimer = window.setTimeout(tickListing, 1200);
    };
    jobTimer = window.setTimeout(tickJob, 300);
    listingTimer = window.setTimeout(tickListing, 1200);
    return () => {
      stopped = true;
      clearTimeout(jobTimer);
      clearTimeout(listingTimer);
    };
  }, [jobId, id, load]);

  if (!listing)
    return error ? (
      <p role="alert" className="text-rose">
        {error}
      </p>
    ) : (
      <p className="eyebrow">Opening listing</p>
    );

  const reviewing = !!listing.copy && !["processing", "failed"].includes(listing.status);

  return (
    <>
      {listing.status !== "processing" && !reviewing && <Header listing={listing} />}
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
      {reviewing && <Review listing={listing} meta={meta} onChange={setListing} reload={() => load().catch((e: Error) => setError(e.message))} />}
    </>
  );
}
