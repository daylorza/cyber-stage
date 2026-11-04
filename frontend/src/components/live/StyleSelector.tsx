import { useEffect, useRef, useState } from "react";
import ConfirmDialog from "../ConfirmDialog";
import { api, media, type Job, type LivePayload, type StyleVersion } from "../../api";
import JobTerminal, { trackJob, type JobEvent } from "./JobTerminal";

/** Room types the backend can render a new version for (it checks for the room's key furniture). */
const RENDERABLE = ["living", "bedroom", "dining"];

const stamp = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

function checks(v: StyleVersion) {
  const failed = ["geometry", "structure", "drift"].filter((k) => v.checker[k as keyof StyleVersion["checker"]]?.status === "fail");
  if (v.available) return { tone: "text-ivory/65", dot: "bg-verdant", text: "Checks passed" };
  if (v.broker_override) return { tone: "text-champagne", dot: "bg-champagne", text: "Shown by broker choice" };
  return { tone: "text-rose", dot: "bg-rose", text: failed.length ? `Failed ${failed.join(", ")}` : "Not shown" };
}

/**
 * The broker's style controls for a prepared residence: pick a room and style, choose a design
 * direction, render a new version, and make any kept version the one buyers see.
 */
export default function StyleSelector({ listingId, refresh }: { listingId: string; refresh: number }) {
  const [payload, setPayload] = useState<LivePayload | null>(null);
  const [directions, setDirections] = useState<Record<string, string[]>>({});
  const [versions, setVersions] = useState<Record<string, StyleVersion[]>>({});
  const [roomId, setRoomId] = useState("");
  const [styleId, setStyleId] = useState("");
  const [variant, setVariant] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [run, setRun] = useState<{ title: string; job: Job | null; events: JobEvent[] } | null>(null);
  const [message, setMessage] = useState("");
  const [switching, setSwitching] = useState<number | null>(null);
  const lastJob = useRef<Job | null>(null);
  const target = useRef({ room: "", roomName: "", style: "", label: "" });

  const load = async () => {
    const [p, v] = await Promise.all([api.live(listingId), api.liveVersions(listingId)]);
    setPayload(p);
    setVersions(v.versions);
    return p;
  };

  useEffect(() => {
    load().catch(() => setPayload(null));
    api.settings().then((s) => setDirections(s.variants ?? {})).catch(() => {});
  }, [listingId, refresh]);

  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    let timer = 0;
    const tick = async () => {
      try {
        const job = await api.job(jobId);
        if (stopped) return;
        const fresh: JobEvent[] = [];
        trackJob(lastJob.current, job, (e) => fresh.push(e));
        lastJob.current = job;
        setRun((prev) => prev && { ...prev, job, events: [...prev.events, ...fresh] });
        if (job.status !== "done" && job.status !== "failed") return void (timer = window.setTimeout(tick, 1000));
        const t = target.current;
        setJobId(null);
        if (job.status === "failed") return setMessage(`${t.roomName} · ${t.label}: ${job.error ?? "render failed; the current image stays."}`);
        const p = await load();
        const used = p.rooms.find((r) => r.id === t.room)?.styles[t.style]?.variant;
        setMessage(`Updated ${t.roomName} · ${t.label}${used ? ` · ${used}` : ""}`);
      } catch (e) {
        if (!stopped) { setMessage((e as Error).message); setJobId(null); }
      }
    };
    void tick();
    return () => { stopped = true; clearTimeout(timer); };
  }, [jobId, listingId]);

  if (!payload || payload.status !== "ready" || !payload.rooms.length) return null;

  const room = payload.rooms.find((r) => r.id === roomId) ?? payload.rooms.find((r) => RENDERABLE.includes(r.type)) ?? payload.rooms[0];
  const style = payload.styles.find((s) => s.id === styleId) ?? payload.styles.find((s) => s.id === payload.default_style) ?? payload.styles[0];
  const current = room.styles[style.id];
  const options = directions[style.id] ?? [];
  const list = [...(versions[`${room.id}:${style.id}`] ?? [])].reverse();
  const renderable = RENDERABLE.includes(room.type);
  const choice = `${style.label}${variant ? ` · ${variant}` : ""}`;

  const pickStyle = (id: string) => { setStyleId(id); setVariant(""); };

  async function render() {
    setConfirm(false);
    target.current = { room: room.id, roomName: room.name, style: style.id, label: style.label };
    lastJob.current = null;
    setRun({ title: `${choice} · ${room.name}`, job: null, events: [{ at: new Date().toISOString(), text: `Requesting ${choice} for ${room.name}` }] });
    setMessage("");
    try { setJobId((await api.rerunLiveStyle(listingId, room.id, style.id, variant || undefined)).job_id); }
    catch (e) { setMessage((e as Error).message); }
    setVariant("");
  }

  async function makeDefault(v: StyleVersion) {
    setSwitching(v.version);
    setMessage("");
    try {
      setVersions((await api.useLiveVersion(listingId, room.id, style.id, v.version)).versions);
      setPayload(await api.live(listingId));
      setMessage(`${room.name} · ${style.label} now shows v${v.version}${v.variant ? ` · ${v.variant}` : ""}`);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setSwitching(null);
    }
  }

  return (
    <section aria-labelledby="style-selector-heading" className="glass mt-8 p-5 sm:p-8">
      {confirm && <ConfirmDialog message={`Render ${choice} for ${room.name}? This makes a new Meta Image call. The current image is replaced only if the new one passes the checks; every version is kept.`} onCancel={() => setConfirm(false)} onConfirm={() => void render()} />}

      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div>
          <p className="eyebrow flex items-center gap-2"><span aria-hidden className="ice-dot" />Style selector</p>
          <h2 id="style-selector-heading" className="mt-3 text-balance text-2xl font-light tracking-tight sm:text-3xl">Set the look buyers walk into</h2>
        </div>
        {payload.rooms.length > 1 && (
          <div className="segmented bg-ivory/[0.04] ring-1 ring-ivory/10" role="group" aria-label="Room">
            {payload.rooms.map((r) => (
              <button key={r.id} type="button" className="segment text-sm" aria-pressed={r.id === room.id} onClick={() => setRoomId(r.id)}>{r.name}</button>
            ))}
          </div>
        )}
      </header>

      <div className="mt-7 grid grid-cols-2 gap-3 sm:grid-cols-4" role="group" aria-label="Style">
        {payload.styles.map((s) => {
          const entry = room.styles[s.id];
          const live = entry?.available && entry.image;
          const on = s.id === style.id;
          return (
            <button key={s.id} type="button" aria-pressed={on} onClick={() => pickStyle(s.id)} className="group text-left">
              <span className={`relative block aspect-[4/3] overflow-hidden rounded-xl ring-1 transition duration-300 ${on ? "ring-2 ring-ice/80 shadow-glow" : "ring-ivory/10 group-hover:ring-ivory/35"}`}>
                <img src={live ? media(entry.image!) : `/styles/${s.id}.jpg`} alt="" loading="lazy" className={`h-full w-full object-cover transition duration-500 ${live ? "" : "opacity-40 grayscale"} ${on ? "" : "group-hover:scale-[1.03]"}`} />
                {!live && <span className="data-label absolute inset-x-0 bottom-0 bg-night/70 px-2 py-1 text-center text-ivory/75">Not rendered</span>}
                {on && <span aria-hidden className="ice-dot absolute right-2 top-2" />}
              </span>
              <span className={`mt-2 block text-sm transition ${on ? "text-ivory" : "text-ivory/70 group-hover:text-ivory"}`}>{s.label}</span>
              <span className="block truncate text-caption text-ash">{entry?.variant ?? (live ? "Original direction" : "—")}</span>
            </button>
          );
        })}
      </div>

      <div className="mt-8 border-t border-ivory/10 pt-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="eyebrow">Design direction · {style.label}</p>
          {current?.variant && <p className="data-label text-ash">Showing now · <span className="text-ivory/80">{current.variant}</span></p>}
        </div>
        {options.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Design direction">
            {["", ...options].map((name) => (
              <button
                key={name || "rotate"}
                type="button"
                aria-pressed={variant === name}
                onClick={() => setVariant(name)}
                className={`hit-area rounded-full px-4 py-2 text-sm ring-1 transition ${variant === name ? "bg-ivory/90 text-night ring-ivory/90" : "text-ivory/80 ring-ivory/15 hover:text-ivory hover:ring-ivory/40"}`}
              >
                {name || "Auto"}
              </button>
            ))}
          </div>
        )}
        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-3">
          <button type="button" className="btn-primary" disabled={!!jobId || !renderable} onClick={() => setConfirm(true)}>
            {jobId ? "Rendering…" : `Render ${choice}`}
          </button>
          <p className="max-w-sm text-xs leading-relaxed text-ash">
            {renderable ? "Uses Meta credits. The current image changes only if the new one passes the checks." : "New renders are available for living rooms, bedrooms and dining rooms. You can still switch versions below."}
          </p>
        </div>
        <p role="status" className="mt-3 min-h-5 text-sm text-ice/90">{message}</p>
        {run && <JobTerminal title={run.title} job={run.job} events={run.events} onClose={jobId ? undefined : () => setRun(null)} className="mt-3 h-60" />}
      </div>

      <div className="mt-8 border-t border-ivory/10 pt-6">
        <p className="eyebrow">Versions · {style.label} in {room.name}{list.length ? ` · ${list.length}` : ""}</p>
        {list.length ? (
          <ul className="-mx-1 mt-4 flex snap-x gap-4 overflow-x-auto overscroll-x-contain p-1 pb-3">
            {list.map((v) => {
              const c = checks(v);
              return (
                <li key={v.version} className="w-52 shrink-0 snap-start">
                  <a href={v.image ? media(v.image) : undefined} target="_blank" rel="noreferrer" aria-label={`Open ${style.label} version ${v.version}`} className={`relative block aspect-[4/3] overflow-hidden rounded-xl ring-1 ${v.is_current ? "ring-2 ring-ice/70" : "ring-ivory/10 hover:ring-ivory/35"}`}>
                    {v.image ? <img src={media(v.image)} alt="" loading="lazy" className="h-full w-full object-cover" /> : <span className="block h-full w-full bg-ivory/5" />}
                    {v.is_current && <span className="data-label absolute left-2 top-2 rounded-full bg-night/75 px-2 py-0.5 text-ice backdrop-blur">Default</span>}
                  </a>
                  <p className="mt-2 flex items-baseline gap-2 text-sm">
                    <span className="font-mono text-ivory">v{v.version}</span>
                    <span className="truncate text-ivory/80">{v.variant ?? (v.broker_approved ? "Broker approved" : "")}</span>
                  </p>
                  <p className="data-label mt-0.5 text-ash">{stamp(v.created_at)}</p>
                  <p className={`mt-1 flex items-center gap-1.5 text-xs ${c.tone}`}><span aria-hidden className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />{c.text}</p>
                  {!v.is_current && v.image && (
                    <button type="button" className="btn-glass mt-3 w-full" disabled={!!jobId || switching !== null} title={v.available ? undefined : "This version didn't pass the checks; it will be shown anyway."} onClick={() => void makeDefault(v)}>
                      {switching === v.version ? "Switching…" : "Make default"}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-ash">No versions yet. Render one above and it appears here.</p>
        )}
      </div>
    </section>
  );
}
