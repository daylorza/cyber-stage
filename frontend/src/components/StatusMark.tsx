import type { ListingStatus } from "../api";

const STATUS: Record<ListingStatus, { label: string; tone: string }> = {
  processing: { label: "Processing", tone: "text-ice!" },
  draft: { label: "Awaiting review", tone: "text-ivory/70!" },
  approved: { label: "Broker approved", tone: "text-champagne!" },
  rejected: { label: "Rejected", tone: "text-rose!" },
  published: { label: "Published", tone: "text-champagne!" },
  failed: { label: "Failed", tone: "text-rose!" },
};

export default function StatusMark({ status }: { status: ListingStatus }) {
  const { label, tone } = STATUS[status];
  return (
    <span className={`eyebrow inline-flex items-center gap-2 ${tone}`}>
      <span className="h-1 w-1 rounded-full bg-current" />
      {label}
    </span>
  );
}
