import { useState, type ReactNode } from "react";
import { clock, media, type Box, type Frame, type Listing, type Room, type TraceEntry } from "../api";
import { uniqueFlags } from "./AttentionList";
import { HELD_BACK } from "./BeforeAfter";
import { EvidenceBlock, flagTarget, StatusDot } from "./trust";

const PURPOSE: Record<string, string> = {
  "sam.privacy": "SAM privacy masks",
  "sam.structure": "SAM structure",
  "wonder.classify": "Wonder room read",
  "image.stage": "Muse Image staging",
  "image.restage": "Muse Image re-stage (stricter)",
  "sam.staged_faces": "SAM faces on staged image",
  "spark.copy": "Spark copy",
  "verify.wonder.claim": "Wonder claim check",
  "verify.sam.structure": "SAM geometry check",
  "verify.sam.faces": "SAM face check",
};

const SHOWN_FRAMES = 6;
const SHOWN_CALLS = 8;

function Heading({ children, note }: { children: ReactNode; note?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
      <h3 className="font-serif text-2xl text-ivory/90">{children}</h3>
      {note}
    </div>
  );
}

function BoxOverlay({ frame, box, kind }: { frame: Frame; box: Box; kind: "privacy" | "structure" }) {
  const [x1, y1, x2, y2] = box.box;
  const w = frame.width!;
  const h = frame.height!;
  const privacy = kind === "privacy";
  return (
    <span
      aria-hidden
      className={`absolute outline outline-1 ${privacy ? "outline-dashed outline-rose" : "outline-ice/60"}`}
      style={{ left: `${(x1 / w) * 100}%`, top: `${(y1 / h) * 100}%`, width: `${((x2 - x1) / w) * 100}%`, height: `${((y2 - y1) / h) * 100}%` }}
    >
      <span className={`absolute left-0 top-0 whitespace-nowrap bg-night/70 px-1 font-mono text-micro leading-4 tracking-wide ${privacy ? "text-rose" : "text-ice/90"}`}>
        {privacy ? `blurred · ${box.concept}` : box.concept}
      </span>
    </span>
  );
}

function FrameCard({ frame, boxes }: { frame: Frame; boxes: boolean }) {
  const sized = frame.width && frame.height;
  const w = frame.wonder;
  return (
    <figure>
      <div className="relative overflow-hidden rounded-xl bg-smoke" style={{ aspectRatio: sized ? `${frame.width} / ${frame.height}` : "16 / 10" }}>
        {frame.path ? (
          <img src={media(frame.path)} alt={`Frame ${frame.id}${w ? `, ${w.room_type}` : ""}, blurred`} loading="lazy" className="h-full w-full object-cover" />
        ) : (
          <div className="grid h-full w-full place-items-center px-4 text-center">
            <p className="eyebrow">{HELD_BACK}</p>
          </div>
        )}
        {boxes && frame.path && sized && frame.sam && (
          <>
            {frame.sam.structure.map((b, i) => (
              <BoxOverlay key={`s${i}`} frame={frame} box={b} kind="structure" />
            ))}
            {frame.sam.privacy.map((b, i) => (
              <BoxOverlay key={`p${i}`} frame={frame} box={b} kind="privacy" />
            ))}
          </>
        )}
      </div>
      <figcaption className="mt-3">
        <p className="data-label flex items-baseline justify-between text-ash">
          <span>{frame.id}</span>
          <span>{frame.t != null ? clock(frame.t) : `Upload ${frame.upload}`}</span>
        </p>
        {w ? (
          <>
            <p className="mt-2 text-sm capitalize text-ivory/90">
              {w.room_type}
              <span className="font-mono text-xs normal-case text-ash">
                {" "}
                · {Math.round(w.coverage * 100)}% coverage · {w.usable ? "usable" : "not usable"}
              </span>
            </p>
            {w.condition && <p className="text-xs text-ash">{w.condition}</p>}
            <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Observations">
              {w.observations.map((o) => (
                <li key={o.id} title={o.id} className="rounded-full bg-ivory/[0.05] px-2.5 py-1 text-caption text-ivory/80">
                  {o.text}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="mt-2 text-sm text-ash">Not classified</p>
        )}
      </figcaption>
    </figure>
  );
}

function Saw({ listing }: { listing: Listing }) {
  const [boxes, setBoxes] = useState(true);
  const [all, setAll] = useState(false);
  const frames = all ? listing.frames : listing.frames.slice(0, SHOWN_FRAMES);
  if (!listing.frames.length)
    return (
      <div>
        <Heading>Saw</Heading>
        <p className="mt-6 text-sm text-ash">No frames: this listing has no walkthrough footage.</p>
      </div>
    );
  return (
    <div>
      <Heading
        note={
          <button type="button" aria-pressed={boxes} onClick={() => setBoxes((b) => !b)} className="btn-ghost text-xs text-ash aria-pressed:text-ice">
            {boxes ? "SAM boxes on" : "SAM boxes off"}
          </button>
        }
      >
        Saw
      </Heading>
      <div className="mt-6 grid gap-x-6 gap-y-10 sm:grid-cols-2 xl:grid-cols-3">
        {frames.map((f) => (
          <FrameCard key={f.id} frame={f} boxes={boxes} />
        ))}
      </div>
      {listing.frames.length > SHOWN_FRAMES && (
        <button type="button" onClick={() => setAll((a) => !a)} className="btn-ghost mt-8 text-sm text-ash">
          {all ? "Show fewer frames" : `Show all ${listing.frames.length} frames`}
        </button>
      )}
    </div>
  );
}

function RoomDecision({ room }: { room: Room }) {
  const src = room.after ?? room.before;
  const st = room.staging;
  return (
    <li className="grid gap-5 sm:grid-cols-[8.5rem_minmax(0,1fr)]">
      <div className={`aspect-video overflow-hidden rounded-lg bg-smoke ${room.rejected ? "opacity-40 grayscale" : ""}`}>
        {src ? <img src={media(src)} alt="" loading="lazy" className="h-full w-full object-cover" /> : <p className="eyebrow grid h-full place-items-center px-2 text-center text-micro!">Held back</p>}
      </div>
      <div className="min-w-0">
        <p className="flex flex-wrap items-baseline gap-x-4">
          <span className="text-base">{room.name}</span>
          <span className="eyebrow">{room.type}</span>
          {room.rejected && <span className="eyebrow text-rose!">Excluded by broker</span>}
        </p>
        <p className="mt-1.5 text-sm text-ash">
          Hero frame <span className="font-mono text-xs text-ivory/80">{room.source_frame ?? "none"}</span>
          {room.hero_reason && ` · ${room.hero_reason}`}
        </p>
        {st && (
          <p className="mt-0.5 text-sm text-ash">
            Staged <span className="text-ivory/80">{st.style}</span> · <span className="font-mono text-xs">{st.model ?? "no model"}</span>
            {st.level ? ` · stricter re-stage, attempt ${st.level}` : ""}
          </p>
        )}
        {room.staging_history && room.staging_history.length > 0 && (
          <p className="mt-0.5 text-xs text-ash">Replaced {room.staging_history.length} earlier staging(s)</p>
        )}
        {st?.error && <p className="mt-1 text-sm text-rose">{st.error}</p>}
        {!st && <p className="mt-0.5 text-sm text-ash">Not staged</p>}
        {st?.prompt && (
          <details className="group mt-2">
            <summary className="btn-ghost w-fit cursor-pointer list-none text-xs text-ash [&::-webkit-details-marker]:hidden">
              <span className="group-open:hidden">Show staging prompt</span>
              <span className="hidden group-open:inline">Hide staging prompt</span>
            </summary>
            <p className="mt-2 max-w-2xl rounded-lg bg-ivory/[0.03] p-3 text-xs leading-relaxed text-ivory/70">{st.prompt}</p>
          </details>
        )}
      </div>
    </li>
  );
}

function Decided({ listing }: { listing: Listing }) {
  const copy = listing.copy;
  const claims = [
    ...(copy ? [{ key: "title", id: "title", text: copy.title, evidence: copy.evidence.title ?? [], label: "Title" }] : []),
    ...(copy?.highlights ?? []).map((c) => ({ key: c.id ?? c.text, id: c.id, text: c.text, evidence: c.evidence, label: "Highlight" })),
    ...(copy?.sentences ?? []).map((c) => ({ key: c.id ?? c.text, id: c.id, text: c.text, evidence: c.evidence, label: "Sentence" })),
  ];
  return (
    <div>
      <Heading>Decided</Heading>
      <div className="mt-6 grid gap-x-14 gap-y-12 lg:grid-cols-2">
        <div>
          <p className="eyebrow">Rooms</p>
          {listing.rooms.length > 0 ? (
            <ul className="mt-5 space-y-8">
              {listing.rooms.map((r) => (
                <RoomDecision key={r.id} room={r} />
              ))}
            </ul>
          ) : (
            <p className="mt-5 text-sm text-ash">No rooms decided.</p>
          )}
        </div>
        {claims.length > 0 && (
          <div>
            <p className="eyebrow">Copy claims{copy?.generator.model ? ` · written by ${copy.generator.model}` : ""}</p>
            <ul className="mt-5 space-y-5">
              {claims.map((c) => (
                <li key={`${c.label}-${c.key}`}>
                  <p className="text-sm text-ivory/90">
                    <span className="data-label mr-3 text-ash">{c.label}</span>
                    {c.text}
                  </p>
                  <EvidenceBlock id={c.id} evidence={c.evidence} listing={listing} className="mt-1.5" />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function StillOpen({ listing }: { listing: Listing }) {
  const open = listing.checklist.items.filter((i) => i.status !== "done");
  const flags = listing.source === "seed" ? [] : uniqueFlags(listing.verification?.flags ?? []);
  return (
    <div>
      <Heading>Still open</Heading>
      {!open.length && !flags.length ? (
        <p className="mt-6 flex items-center gap-3 text-sm text-ice/90">
          <span className="ice-dot" />
          Nothing open. Every check passed.
        </p>
      ) : (
        <ul className="mt-6 space-y-4">
          {open.map((i) => (
            <li key={i.id} className="flex items-start gap-3.5">
              <span className="mt-[7px]">
                <StatusDot status={i.status} />
              </span>
              <p className="text-sm text-ivory/85">
                {i.label}
                {i.detail && <span className="block text-xs text-ash">{i.detail}</span>}
              </p>
            </li>
          ))}
          {flags.map((f) => (
            <li key={f.id} className="flex items-start gap-3.5">
              <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-rose" />
              <p className="text-sm text-ivory/85">
                {flagTarget(f, listing)}: {f.message}
                <span className="block text-xs text-ash">{f.resolution}</span>
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function targetText(t: Record<string, unknown>, listing: Listing): string {
  const parts: string[] = [];
  const room = typeof t.room === "string" ? listing.rooms.find((r) => r.id === t.room)?.name ?? t.room : null;
  if (room) parts.push(room);
  if (typeof t.frame === "string") parts.push(t.frame);
  if (typeof t.claim === "string") {
    const text = t.claim === "title" ? listing.copy?.title : [...(listing.copy?.highlights ?? []), ...(listing.copy?.sentences ?? [])].find((c) => c.id === t.claim)?.text;
    parts.push(text ?? t.claim);
  }
  if (typeof t.concept === "string") parts.push(t.concept);
  if (typeof t.side === "string") parts.push(t.side);
  if (!parts.length && typeof t.frames === "number") parts.push(`${t.frames} frames`);
  return parts.join(" · ");
}

function CallList({ title, rows, listing }: { title: string; rows: TraceEntry[]; listing: Listing }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, SHOWN_CALLS);
  return (
    <div className="min-w-0">
      <p className="eyebrow">
        {title} · {rows.length}
      </p>
      {rows.length === 0 ? (
        <p className="mt-4 text-sm text-ash">None recorded.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {shown.map((r) => (
            <li key={r.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4">
              <div className="min-w-0">
                <p className="text-sm text-ivory/90">{PURPOSE[r.purpose] ?? r.purpose}</p>
                <p className="truncate text-xs text-ash" title={targetText(r.target, listing) || r.summary}>
                  {targetText(r.target, listing) || r.summary}
                </p>
              </div>
              <p className={`data-label text-right ${r.ok ? "text-ash" : "text-rose"}`}>
                <span className="block">{r.model}</span>
                <span className="block">
                  {r.ok ? `${r.ms} ms` : "error"}
                  {r.cached && " · cached"}
                </span>
              </p>
              {!r.ok && r.error && <p className="col-span-2 mt-0.5 text-xs text-rose">{r.error}</p>}
            </li>
          ))}
        </ul>
      )}
      {rows.length > SHOWN_CALLS && (
        <button type="button" onClick={() => setAll((a) => !a)} className="btn-ghost mt-5 text-sm text-ash">
          {all ? "Show fewer" : `Show all ${rows.length}`}
        </button>
      )}
    </div>
  );
}

function Calls({ listing }: { listing: Listing }) {
  const independent = listing.trace.filter((t) => t.purpose.startsWith("verify."));
  const generator = listing.trace.filter((t) => !t.purpose.startsWith("verify."));
  const cached = listing.trace.filter((t) => t.cached).length;
  return (
    <div>
      <Heading note={<p className="font-mono text-xs text-ash">{`${listing.trace.length} Meta calls · ${independent.length} independent · ${cached} cached`}</p>}>
        Meta calls
      </Heading>
      <div className="mt-6 grid gap-x-12 gap-y-10 lg:grid-cols-2">
        <CallList title="Generator" rows={generator} listing={listing} />
        <CallList title="Independent checks" rows={independent} listing={listing} />
      </div>
    </div>
  );
}

export default function DecisionPanel({ listing }: { listing: Listing }) {
  const [open, setOpen] = useState(true);
  return (
    <section aria-labelledby="decision-heading" className="pt-4">
      <div className="flex items-baseline justify-between gap-6">
        <h2 id="decision-heading" className="font-serif text-2xl sm:text-3xl">
          What the model saw and decided
        </h2>
        <button type="button" aria-expanded={open} aria-controls="decision-body" onClick={() => setOpen((o) => !o)} className="btn-ghost shrink-0 text-sm text-ash">
          {open ? "Collapse" : "Expand"}
        </button>
      </div>
      {open && (
        <div id="decision-body" className="mt-10 space-y-16 sm:space-y-20">
          <Saw listing={listing} />
          <Decided listing={listing} />
          <StillOpen listing={listing} />
          <Calls listing={listing} />
        </div>
      )}
    </section>
  );
}
