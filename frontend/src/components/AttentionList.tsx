import { useState } from "react";
import type { Flag, Listing } from "../api";
import { flagTarget } from "./trust";

export function uniqueFlags(flags: Flag[]): Flag[] {
  const seen = new Set<string>();
  return flags.filter((f) => {
    const key = Object.keys(f.target).length ? `${f.item}:${JSON.stringify(f.target)}:${f.message}` : f.item;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export default function AttentionList({
  listing,
  blocking = true,
  onClaim,
  onRoom,
}: {
  listing: Listing;
  blocking?: boolean;
  onClaim: (claimId: string) => void;
  onRoom: (roomId: string) => void;
}) {
  const [hidden, setHidden] = useState(false);
  const flags = uniqueFlags(listing.verification?.flags ?? []);
  if (!flags.length) return null;

  if (hidden) return <button type="button" className="btn-glass" onClick={() => setHidden(false)}>Show warnings</button>;

  return (
    <section aria-labelledby="attention-heading" className="glass bg-rose/[0.05]! p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h2 id="attention-heading" className="eyebrow text-rose!">
          Needs your attention · {flags.length}
          {!blocking && <span className="text-ash!"> · warnings only, won't block Approve or Publish</span>}
        </h2>
        <button type="button" className="btn-ghost shrink-0 text-sm text-ivory/75" onClick={() => setHidden(true)}>Hide warnings</button>
      </div>
      <ul className="mt-4 space-y-4">
        {flags.map((f) => {
          const { claim, room } = f.target as { claim?: string; room?: string };
          const body = (
            <>
              <span className="data-label block text-ash">{room || claim ? flagTarget(f, listing) : f.item.replace(/_/g, " ")}</span>
              <span className="mt-1 block text-sm text-ivory/90">{f.message}</span>
              <span className="mt-0.5 block text-xs text-ash">{f.resolution}</span>
            </>
          );
          return (
            <li key={f.id}>
              {room || claim ? (
                <button type="button" onClick={() => (room ? onRoom(room) : onClaim(claim!))} className="-mx-2 block w-[calc(100%+1rem)] rounded-lg px-2 py-1.5 text-left transition hover:bg-ivory/[0.04]">
                  {body}
                </button>
              ) : (
                <div>{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
