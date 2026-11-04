import { useEffect, useState } from "react";
import { api, media, type LivePayload, type StyleVersion } from "../../api";

const stamp = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

function checkerLine(v: StyleVersion) {
  const parts = [v.checker.geometry && `Geometry ${v.checker.geometry.status}`, v.checker.structure && `Structure ${v.checker.structure.status}`, v.checker.drift && `Drift ${v.checker.drift.status}`].filter(Boolean);
  return parts.length ? parts.join(" · ") : "No checker result recorded";
}

/** Every kept version of each room's style image. "Use this version" only switches which one shows: no Meta calls, nothing deleted. */
export default function StyleVersions({ listingId, payload, refresh, disabled, onChanged }: { listingId: string; payload: LivePayload; refresh: number; disabled: boolean; onChanged: () => void }) {
  const [versions, setVersions] = useState<Record<string, StyleVersion[]> | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let stopped = false;
    api.liveVersions(listingId).then((r) => !stopped && setVersions(r.versions)).catch((e: Error) => !stopped && setError(e.message));
    return () => { stopped = true; };
  }, [listingId, refresh]);

  async function use(room: string, style: string, version: number) {
    const key = `${room}:${style}:${version}`;
    setBusy(key);
    setError("");
    try {
      setVersions((await api.useLiveVersion(listingId, room, style, version)).versions);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  if (!versions) return error ? <p className="px-2 text-xs text-rose">{error}</p> : null;
  const groups = payload.rooms.flatMap((room) => payload.styles.map((style) => ({ room, style, list: versions[`${room.id}:${style.id}`] ?? [] }))).filter((g) => g.list.length);
  if (!groups.length) return <p className="px-2 text-xs text-ash">No versions yet. The next re-run keeps today's images as version 1 before adding version 2.</p>;

  return (
    <div className="space-y-2 px-2">
      {groups.map(({ room, style, list }) => {
        const current = list.find((v) => v.is_current);
        return (
          <details key={`${room.id}:${style.id}`} className="group/v">
            <summary className="disclosure cursor-pointer text-sm text-ivory/85 hover:text-ivory pointer-coarse:py-2">
              {room.name} · {style.label} <span className="font-mono text-caption text-ash">{list.length} {list.length === 1 ? "version" : "versions"}{current ? ` · v${current.version} current` : ""}</span>
            </summary>
            <ul className="mt-2 space-y-3">
              {[...list].reverse().map((v) => (
                <li key={v.version} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3">
                  {v.image ? <img src={media(v.image)} alt={`${style.label}, version ${v.version}`} loading="lazy" className="h-12 w-[4.5rem] rounded-md object-cover ring-1 ring-ivory/10" /> : <span className="h-12 w-[4.5rem] rounded-md bg-ivory/5" />}
                  <div className="min-w-0 text-xs leading-snug">
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-mono text-ivory">v{v.version}</span>
                      <span className="text-ash">{stamp(v.created_at)}</span>
                      {v.variant && <span className="text-ivory/80">{v.variant}</span>}
                      {v.is_current && <span className="rounded-full bg-ice/15 px-2 py-0.5 text-ice">Current</span>}
                      {v.broker_approved && <span className="rounded-full bg-champagne/15 px-2 py-0.5 text-champagne">Broker approved</span>}
                    </p>
                    <p className={`mt-1 ${v.available ? "text-ivory/65" : v.broker_override ? "text-champagne" : "text-rose"}`}>{checkerLine(v)}{v.available ? "" : v.broker_override ? " · shown by broker choice" : " · not shown"}</p>
                    <p className="mt-0.5 truncate text-ash" title={v.created_by}>{v.created_by}{v.model ? ` · ${v.model}` : ""}</p>
                    <p className="mt-1.5 flex gap-4">
                      {v.image && <a href={media(v.image)} target="_blank" rel="noreferrer" className="btn-ghost text-ivory/80">View</a>}
                      {!v.is_current && v.image && <button type="button" disabled={disabled || !!busy} title={v.available ? undefined : "This version didn't pass the checks; it will be shown anyway."} onClick={() => void use(room.id, style.id, v.version)} className="btn-ghost text-ice/90">{busy === `${room.id}:${style.id}:${v.version}` ? "Switching…" : "Make default"}</button>}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </details>
        );
      })}
      {error && <p role="alert" className="text-xs text-rose">{error}</p>}
    </div>
  );
}
