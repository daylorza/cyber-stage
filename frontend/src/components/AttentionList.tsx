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
  onClaim,
  onRoom,
}: {
  listing: Listing;
  onClaim: (claimId: string) => void;
  onRoom: (roomId: string) => void;
}) {
  const flags = uniqueFlags(listing.verification?.flags ?? []);
  if (!flags.length) return null;

  return (
    <section aria-labelledby="attention-heading" className="glass bg-rose/[0.05]! p-6">
      <h2 id="attention-heading" className="eyebrow text-rose!">
        Needs your attention · {flags.length}
      </h2>
      <ul className="mt-4 space-y-4">
        {flags.map((f) => {
          const { claim, room } = f.target as { claim?: string; room?: string };
          const body = (
            <>
              <span className="block font-mono text-[10px] tracking-wider text-ash uppercase">{room || claim ? flagTarget(f, listing) : f.item.replace(/_/g, " ")}</span>
              <span className="mt-1 block text-sm text-ivory/90">{f.message}</span>
              <span className="mt-0.5 block text-xs text-ash">{f.resolution}</span>
            </>
          );
          return (
            <li key={f.id}>
              {room || claim ? (
                <button type="button" onClick={() => (room ? onRoom(room) : onClaim(claim!))} className="block w-full text-left transition hover:opacity-80">
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
