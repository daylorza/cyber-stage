import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type Listing } from "../api";

const REPO = "https://github.com/daylorza/cyber-stage";

const RUBRIC = [
  { name: "Impact", weight: 30, how: "A real broker and buyer problem: empty rooms don't sell from a phone video. Broker approval is the trust gate; nothing publishes without it." },
  { name: "Use of Meta AI tooling", weight: 25, how: "Four Meta models chained end to end, each doing a job only it can do. The checker runs outside the generator, and the guide acts on the room instead of only chatting." },
  { name: "Demo", weight: 25, how: "Working loop: upload → staged → approve → publish → Live-In-It → AI Live-In Guide, plus a 3-minute video with sped-up runs labelled pre-existing vs built this week." },
  { name: "Technical depth", weight: 20, how: "Async jobs, cached calls with a per-listing brake, geometry / structure / framing verification, a LangChain guide with tools and per-thread memory, versioned style renders with a broker Style Selector, before/after provenance, and a test suite run on every change." },
];

const MODELS = [
  { name: "Muse Spark 1.3", role: "Copy + AI Live-In Guide brain", where: "Writes the listing copy. Runs the Live-In Guide with LangChain tools that read prepared listing data, change the displayed room or style, and simulate a deposit.", why: "Reasoning model: turns evidence and facts into grounded claims and tool calls." },
  { name: "Muse Wonder 1.0", role: "Sees and classifies rooms", where: "Room type, coverage and observations per frame; re-checks visually supported claims. Fact-only and broker-attested claims follow different checks.", why: "Multimodal understanding of what the camera actually saw." },
  { name: "Muse Image 1.0", role: "Stages furniture and decor only", where: "One image per style from the room's best frame: Modern luxury, Coastal, Minimal, Cyberpunk (style ID 2142), each with four design directions.", why: "Image generation that keeps the filmed room's walls, windows and doors." },
  { name: "SAM 3.1", role: "Segments the room", where: "Windows, doors and structure for the checker; furniture masks; faces and personal items for the privacy blur.", why: "Precise masks the checker and the blur can measure against." },
];

const STEPS: [string, string][] = [
  ["Ingest", "Upload + facts"],
  ["Frames", "ffmpeg · 1 fps, near-duplicates dropped"],
  ["Segment", "SAM 3.1"],
  ["Classify rooms", "Wonder 1.0"],
  ["Best frame per room", "Code · Wonder coverage + sharpness"],
  ["Stage", "Image 1.0"],
  ["Grounded copy", "Spark 1.3"],
  ["Independent check", "Separate verification code · own Wonder + SAM calls, not a separate model or third party"],
  ["Approve + publish", "Broker"],
];

const ENGINEERING = [
  "Jobs run async with status polling; the UI never blocks on a model call.",
  "Meta calls are disk-cached by model + purpose + prompt + image hash, with a 400-call brake per listing (internal runs: ~47 for photos, ~87 for a video; not a benchmark).",
  "Checker thresholds: geometry 0.25, structure IoU 0.3, framing drift 0.05. Results are recorded, never rewritten.",
  "Demo mode: a failed glass or geometry check doesn't hide a room; only missing furniture disables a style. SAM can miss floor-to-ceiling glass; that is recorded, not shown as a pass.",
  "AI Live-In Guide: Spark 1.3 via LangChain, server-side key, tools on existing data only, 12-turn memory per demo session. No new Image or SAM call on a style switch, no silent credit spend on load; Original is the before image, with no call.",
];

const LIMITS = [
  "No head-to-head benchmarks against Matterport, Varjo or Zillow: none were run, none are claimed.",
  "The full loop takes minutes, not seconds; a timed hero run is still to be recorded.",
  "Comps are seeded demo data, not a live MLS feed. The deposit is simulated; no payment is taken.",
  "Cyberpunk (style ID 2142) is a labelled concept style, not a real interior style and not a verified depiction of this home.",
  "A broker can make a style version the default even if it failed the checks. That choice is recorded on the version and labelled \"shown by broker choice\", never shown as a pass.",
];

const STYLE_FLOW: [string, string][] = [
  ["Pick", "Room, style and design direction, or Auto to rotate through every direction before repeating one."],
  ["Render", "One Muse Image call with the direction written into the prompt. A retry keeps the same direction."],
  ["Check", "Geometry, structure and framing drift on the new image, plus SAM furniture detection. The live image changes only if it passes."],
  ["Keep", "Every render is saved as a numbered version (v1, v2, …) with its model, direction, timestamp and check results. Nothing is overwritten."],
  ["Choose", "Make default switches which version buyers see: no Meta call, no regeneration. Choosing a version that failed is a recorded broker override."],
];

const EXTERIORS = [
  ["Champagne halo", "Full 2142 skyline", "Blue hour", "One flying vehicle"],
  ["Glacier glass", "Full 2142 skyline", "Daylight", "None"],
  ["Liquid chrome", "Real view, buildings rebuilt as 2142", "Blue hour", "One flying vehicle"],
  ["Pearl atrium", "Real view, buildings rebuilt as 2142", "Daylight", "None"],
];

const STYLE_LABELS: Record<string, string> = { "modern-luxury": "Modern luxury", coastal: "Coastal", minimal: "Minimal", "2142": "Cyberpunk · 2142" };

const modelOf = (purpose: string) => {
  const p = purpose.replace(/^verify\./, "");
  return p.startsWith("sam") ? "SAM 3.1" : p.startsWith("wonder") ? "Wonder 1.0" : p.startsWith("image") ? "Image 1.0" : p.startsWith("spark") ? "Spark 1.3" : "Other";
};

function Block({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section className="border-t border-ivory/10 pt-10 sm:pt-12">
      <p className="eyebrow">{eyebrow}</p>
      <h3 className="mt-2 font-serif text-2xl sm:text-3xl">{title}</h3>
      <div className="mt-6 sm:mt-8">{children}</div>
    </section>
  );
}

/** Judges-facing: what Cyber Stage uses, how it is built, and how it meets the rubric. Real numbers for this listing only. */
export default function TechnicalDetails({ listing, children }: { listing?: Listing; children?: ReactNode }) {
  const root = useRef<HTMLElement>(null);
  const [inView, setInView] = useState(false);
  const [directions, setDirections] = useState<Record<string, string[]>>({});
  useEffect(() => {
    api.settings().then((s) => setDirections(s.variants ?? {})).catch(() => {});
  }, []);
  useEffect(() => {
    if (window.location.hash === "#technical") root.current?.scrollIntoView({ block: "start" });
  }, []);
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { rootMargin: "0px 0px -40% 0px" });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const trace = listing?.trace ?? [];
  const byModel = ["Spark 1.3", "Wonder 1.0", "Image 1.0", "SAM 3.1"].map((m) => ({
    model: m,
    generator: trace.filter((t) => modelOf(t.purpose) === m && !t.purpose.startsWith("verify.")).length,
    checker: trace.filter((t) => modelOf(t.purpose) === m && t.purpose.startsWith("verify.")).length,
  }));
  const checks = listing?.verification?.checks ?? [];
  const passed = checks.filter((c) => c.status === "pass").length;
  const stats = [
    { label: "Meta calls", value: trace.length },
    { label: "Cached", value: trace.filter((t) => t.cached).length },
    { label: "Checks passed", value: checks.length ? `${passed} / ${checks.length}` : "—" },
    { label: "Rooms", value: listing?.rooms.length ?? 0 },
    { label: "Frames", value: listing?.frames.length ?? 0 },
  ];
  const toTop = () => window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });

  return (
    <section ref={root} id="technical" aria-labelledby="technical-heading" className="mt-20 scroll-mt-28 sm:mt-28">
      <div className="max-w-3xl">
        <p className="eyebrow text-ice/80!">For judges</p>
        <h2 id="technical-heading" tabIndex={-1} className="mt-2 outline-none text-balance font-serif text-4xl sm:text-5xl">Technical details — for judges</h2>
        <p className="mt-4 text-ash">
          Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4, 2026 · Solo · Indie track · Team Bliss.
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          {listing && <Link to="/about" className="btn-ghost text-ivory/85">What is Cyber Stage? About →</Link>}
          <a href={REPO} target="_blank" rel="noreferrer" className="btn-ghost text-ivory/85">Repository ↗</a>
          <a href="https://youtu.be/e4h0FqXTF5A" target="_blank" rel="noreferrer" className="btn-ghost text-ivory/85">Demo video ↗</a>
        </div>
      </div>

      <div className="mt-12 space-y-12 sm:mt-14 sm:space-y-16">
        <Block eyebrow="Rubric" title="How Cyber Stage meets the rubric">
          <p className="mb-6 max-w-3xl text-sm text-ash">Stage 1 is pass/fail on theme fit and use of Meta AI products. Stage 2 and the final score each criterion 0–10.</p>
          <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {RUBRIC.map((r) => (
              <li key={r.name} className="glass p-5 sm:p-6">
                <div className="flex items-baseline justify-between gap-4">
                  <p className="text-lg">{r.name}</p>
                  <p className="font-mono text-data tabular-nums text-champagne">{r.weight}%</p>
                </div>
                <div aria-hidden className="mt-3 h-px w-full bg-ivory/10">
                  <div className="h-px bg-champagne/70" style={{ width: `${(r.weight / 30) * 100}%` }} />
                </div>
                <p className="mt-4 text-sm leading-relaxed text-ivory/75">{r.how}</p>
              </li>
            ))}
          </ul>
        </Block>

        <Block eyebrow="Meta AI tooling · 25%" title="Four Meta models, each doing one job">
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {MODELS.map((m) => (
              <li key={m.name} className="glass flex flex-col p-5">
                <p className="eyebrow text-ice/80!">{m.name}</p>
                <p className="mt-3 font-serif text-xl leading-snug">{m.role}</p>
                <p className="mt-3 text-sm leading-relaxed text-ivory/75">{m.where}</p>
                <p className="mt-auto pt-4 text-xs leading-relaxed text-ash">{m.why}</p>
              </li>
            ))}
          </ul>
          <p className="mt-5 text-sm text-ash">Meta models only at runtime. Scaffolding, not models: React, Vite, Tailwind, FastAPI, ffmpeg, Pillow. No non-Meta model or embedder, no real payment.</p>
        </Block>

        <Block eyebrow="Technical depth · 20%" title="The pipeline, in order">
          <ol className="grid grid-cols-1 gap-x-4 gap-y-0 lg:grid-cols-9">
            {STEPS.map(([name, tag], i) => (
              <li key={name} className="relative flex gap-4 pb-6 lg:flex-col lg:gap-3 lg:pb-0">
                <span className="relative flex flex-col items-center lg:flex-row">
                  <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full font-mono text-micro ring-1 ${name === "Independent check" ? "text-champagne ring-champagne/50" : "text-ice ring-ice/40"}`}>{String(i + 1).padStart(2, "0")}</span>
                  {i < STEPS.length - 1 && <span aria-hidden className="mt-1 w-px flex-1 bg-ivory/15 lg:ml-1 lg:mt-0 lg:h-px lg:w-auto" />}
                </span>
                <span className="min-w-0 pt-1 lg:pt-0">
                  <span className="block text-sm text-ivory">{name}</span>
                  <span className={`mt-0.5 block text-xs leading-snug ${name === "Independent check" ? "text-champagne/90" : "text-ash"}`}>{tag}</span>
                </span>
              </li>
            ))}
          </ol>
          <ul className="mt-10 grid max-w-4xl grid-cols-1 gap-3">
            {ENGINEERING.map((e) => (
              <li key={e} className="flex gap-3 text-sm leading-relaxed text-ivory/80">
                <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ice/70" />
                {e}
              </li>
            ))}
          </ul>
        </Block>

        <Block eyebrow="Technical depth · Style selector" title="Directed, versioned style renders">
          <p className="max-w-3xl text-sm leading-relaxed text-ivory/75">Each style has four design directions, so two rooms in the same style don't come out looking identical. After publishing, the broker's Style Selector, right below Enter residence, lets them render a chosen direction for a room and pick which kept version buyers see.</p>
          {Object.keys(directions).length > 0 && (
            <ul className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {Object.entries(directions).map(([id, names]) => (
                <li key={id} className="glass p-5">
                  <p className="eyebrow text-ice/80!">{STYLE_LABELS[id] ?? id}</p>
                  <ul className="mt-3 space-y-1.5">
                    {names.map((n) => <li key={n} className="font-serif text-lg leading-snug">{n}</li>)}
                  </ul>
                </li>
              ))}
            </ul>
          )}
          <ol className="mt-10 grid grid-cols-1 gap-x-6 gap-y-5 md:grid-cols-5">
            {STYLE_FLOW.map(([name, text], i) => (
              <li key={name} className="flex gap-4 md:flex-col md:gap-3">
                <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full font-mono text-micro ring-1 ${name === "Check" ? "text-champagne ring-champagne/50" : "text-ice ring-ice/40"}`}>{String(i + 1).padStart(2, "0")}</span>
                <span className="min-w-0">
                  <span className="block text-sm text-ivory">{name}</span>
                  <span className="mt-1 block text-xs leading-relaxed text-ash">{text}</span>
                </span>
              </li>
            ))}
          </ol>
          <div className="mt-10 max-w-4xl">
            <p className="eyebrow">Cyberpunk · 2142 exteriors</p>
            <p className="mt-2 text-sm text-ash">Pristine and high-tech: no noir, neon signage or grime. Each direction sets its own window view, so every combination is covered once.</p>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[34rem] text-left text-sm">
                <thead className="data-label text-ash">
                  <tr className="border-b border-ivory/10">{["Direction", "View", "Light", "Flying vehicle"].map((h) => <th key={h} scope="col" className="py-2 pr-4 font-normal">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {EXTERIORS.map(([d, view, light, car]) => (
                    <tr key={d} className="border-b border-ivory/5">
                      <th scope="row" className="py-2.5 pr-4 font-normal text-ivory">{d}</th>
                      <td className="py-2.5 pr-4 text-ivory/75">{view}</td>
                      <td className="py-2.5 pr-4 text-ivory/75">{light}</td>
                      <td className="py-2.5 text-ivory/75">{car}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Block>

        {listing && <Block eyebrow="Live data" title="This listing, measured">
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            {stats.map((s) => (
              <div key={s.label} className="glass p-4 sm:p-5">
                <dt className="eyebrow">{s.label}</dt>
                <dd className="mt-2 font-serif text-3xl tabular-nums">{s.value}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-6 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {byModel.map((m) => (
              <p key={m.model} className="flex items-baseline justify-between gap-4 rounded-xl bg-ivory/[0.025] px-4 py-3 text-sm">
                <span>{m.model}</span>
                <span className="font-mono text-xs tabular-nums text-ash">
                  {m.generator} generate · {m.checker} check
                </span>
              </p>
            ))}
          </div>
          <p className="mt-4 text-xs text-ash">Counted from this listing's recorded Meta call trace and verification results. Check calls come from the independent checker, never the call that generated the output.</p>
        </Block>}

        <Block eyebrow="Honesty" title="Limits we state plainly">
          <ul className="grid max-w-4xl grid-cols-1 gap-3">
            {LIMITS.map((l) => (
              <li key={l} className="flex gap-3 text-sm leading-relaxed text-ivory/80">
                <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-rose/80" />
                {l}
              </li>
            ))}
          </ul>
        </Block>

        {children && (
          <Block eyebrow="Diagnostics" title="Source data, checks and model decisions">
            <div className="space-y-4">{children}</div>
          </Block>
        )}
      </div>

      <div className="mt-14 border-t border-ivory/10 pt-8">
        <button type="button" onClick={toTop} className="btn-glass text-base">↑ Back to top</button>
      </div>

      <button
        type="button"
        onClick={toTop}
        aria-hidden={!inView}
        tabIndex={inView ? 0 : -1}
        className={`btn-glass hud-right fixed z-30 text-base transition duration-300 ${inView ? "visible translate-y-0 opacity-100" : "invisible -translate-y-1 opacity-0"}`}
        style={{ top: "calc(var(--gutter-top) + env(safe-area-inset-top) + 3.75rem)" }}
      >
        ↑ {listing ? "Back to listing" : "Back to top"}
      </button>
    </section>
  );
}
