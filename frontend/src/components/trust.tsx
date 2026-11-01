import { clock, type Check, type ChecklistStatus, type Claim, type Evidence, type Flag, type Listing, type Room } from "../api";

export type Tone = "pass" | "fail" | "unclear" | "none";

export const modelName = (model: string | null | undefined) => {
  const m = model?.toLowerCase() ?? "";
  return m.includes("wonder") ? "Wonder" : m.includes("sam") ? "SAM 3.1" : m.includes("spark") ? "Spark" : m.includes("image") ? "Muse Image" : (model ?? "Code");
};

export function evidenceLine(e: Evidence, rooms: Room[]): string {
  if (e.kind === "fact") return `Fact · ${e.ref} = ${String(e.value)}`;
  if (e.kind === "broker") return "Broker attested";
  if (e.kind === "unknown") return "Unresolved pointer";
  const room = rooms.find((r) => r.id === e.room_id)?.name ?? e.room_id;
  return `Seen · ${room} · ${e.text}${e.t != null ? ` · ${clock(e.t)}` : ""}`;
}

export function claimResult(checks: Check[], claimId: string | undefined, evidence: Evidence[] | undefined) {
  const own = claimId ? checks.filter((c) => c.target.claim === claimId) : [];
  if (!own.length) return { tone: "none" as Tone, label: "Checks run on save", reason: "" };
  const bad = own.find((c) => c.status === "fail") ?? own.find((c) => c.status === "unclear");
  if (bad) return { tone: bad.status as Tone, label: bad.status === "fail" ? "Not supported" : "Unclear", reason: bad.reason };
  const meta = own.find((c) => c.kind === "meta");
  if (meta) return { tone: "pass" as Tone, label: `Verified by ${modelName(meta.model)}`, reason: "" };
  return { tone: "pass" as Tone, label: evidence?.some((e) => e.kind === "fact") ? "Matches supplied fact" : "Evidence resolves", reason: "" };
}

export const roomIssues = (checks: Check[], roomId: string) => checks.filter((c) => c.target.room === roomId && c.status !== "pass");

export const ITEM_SHORT: Record<string, string> = {
  frames: "Frames",
  sam_masks: "Masks",
  wonder_classification: "Classification",
  staging_geometry: "Staging geometry",
  claim_evidence: "Claim evidence",
  comps_demo: "Comps",
  blur_pass: "Faces",
};

export function flagTarget(flag: Flag, listing: Listing): string {
  const { claim, room } = flag.target as { claim?: string; room?: string };
  if (claim === "title") return "Title";
  if (claim) return String(flag.target.text ?? claim);
  if (room) return listing.rooms.find((r) => r.id === room)?.name ?? room;
  return listing.checklist.items.find((i) => i.id === flag.item)?.label ?? flag.item;
}

const TONE_TEXT: Record<Tone, string> = { pass: "text-ice/80", fail: "text-rose", unclear: "text-rose", none: "text-ash" };
const TONE_DOT: Record<Tone, string> = { pass: "bg-ice/80", fail: "bg-rose", unclear: "bg-rose/70", none: "bg-ivory/20" };

export function ResultLine({ tone, label, reason }: { tone: Tone; label: string; reason?: string }) {
  return (
    <p className={`flex items-start gap-2 text-xs ${TONE_TEXT[tone]}`}>
      <span className={`mt-[5px] h-1 w-1 shrink-0 rounded-full ${TONE_DOT[tone]}`} />
      <span>
        {label}
        {reason && tone !== "pass" && <span className="text-ivory/70"> · {reason}</span>}
      </span>
    </p>
  );
}

export function ClaimTrust({ claim, listing, className = "" }: { claim: Claim | undefined; listing: Listing; className?: string }) {
  if (!claim) return <p className={`eyebrow text-micro! ${className}`}>Unsaved edit · checks run on save</p>;
  return <EvidenceBlock id={claim.id} evidence={claim.evidence} listing={listing} className={className} />;
}

export function EvidenceBlock({ id, evidence, listing, className = "" }: { id: string | undefined; evidence: Evidence[]; listing: Listing; className?: string }) {
  const result = claimResult(listing.verification?.checks ?? [], id, evidence);
  return (
    <div className={`space-y-1 ${className}`}>
      <p className="data-label flex flex-wrap gap-x-4 gap-y-0.5 text-ice/80">
        {evidence.length ? evidence.map((e, i) => <span key={i}>{evidenceLine(e, listing.rooms)}</span>) : <span className="text-rose">No evidence</span>}
      </p>
      <ResultLine {...result} />
    </div>
  );
}

const STATUS_DOT: Record<ChecklistStatus, string> = {
  done: "bg-ice/80",
  flagged: "bg-rose",
  failed: "bg-rose",
  generated: "bg-ivory/40",
  open: "bg-ivory/15",
};

export const STATUS_TEXT: Record<ChecklistStatus, string> = {
  done: "text-ivory/85",
  flagged: "text-rose",
  failed: "text-rose",
  generated: "text-ivory/60",
  open: "text-ash",
};

export const STATUS_WORD: Record<ChecklistStatus, string> = {
  done: "done",
  flagged: "flagged",
  failed: "failed",
  generated: "generated, not yet verified",
  open: "open",
};

export const StatusDot = ({ status }: { status: ChecklistStatus }) => (
  <span aria-hidden className={`block h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[status]}`} />
);
