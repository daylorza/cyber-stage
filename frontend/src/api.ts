export type Evidence = { kind: "fact" | "broker" | "visual"; ref: string; value?: unknown };
export type Claim = { text: string; evidence: Evidence[] };

export type Room = {
  id: string;
  name: string;
  type: string;
  source_frame: string;
  before: string;
  after: string | null;
  style: string | null;
  rejected: boolean;
};

export type Facts = {
  address: string;
  city: string;
  beds: number | null;
  baths: number | null;
  sqft: number | null;
  price: number | null;
  currency: string;
  estimate_price?: boolean;
};

export type Comp = {
  label: string;
  area: string;
  beds: number;
  baths: number;
  sqft: number;
  price: number;
  currency: string;
  status: string;
  date: string;
};

export type Comps = {
  source: string;
  label: string;
  items: Comp[];
  suggested_range: { low: number; high: number; median_per_sqft: number; currency: string; basis: string } | null;
};

export type Copy = {
  title: string;
  description: string;
  highlights: Claim[];
  evidence: Record<string, Evidence[]>;
};

export type Job = {
  id: string;
  listing_id: string;
  status: "queued" | "running" | "done" | "failed";
  stage: string | null;
  progress: number;
  error: string | null;
};

export type ListingStatus = "processing" | "draft" | "approved" | "rejected" | "published" | "failed";

export type PublishedPage = {
  id: string;
  title: string;
  description: string;
  highlights: Claim[];
  facts: Facts;
  price_display: string | null;
  rooms: Room[];
  comps: Comps;
  approved_at: string;
  published_at: string;
};

export type Listing = {
  id: string;
  source: "upload" | "seed";
  status: ListingStatus;
  facts: Facts;
  uploads: { name: string; kind: "video" | "photo" }[];
  frames: string[];
  rooms: Room[];
  copy?: Copy;
  comps?: Comps;
  review: { decision: "approved" | "rejected" | null; decided_at: string | null; notes: string; edited_fields: string[] };
  job: Job | null;
  error?: string;
  note?: string;
  published?: PublishedPage;
  updated_at: string;
};

export type ListingSummary = {
  id: string;
  status: ListingStatus;
  source: "upload" | "seed";
  title: string;
  city: string | null;
  facts: Facts;
  price_display: string | null;
  cover: string | null;
  rooms: number;
  note: string | null;
  updated_at: string;
};

export type ReviewBody = {
  action: "save" | "approve" | "reject";
  copy_edit?: { title: string; description: string; highlights: string[] };
  rejected_rooms?: string[];
};

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return `Request failed (${status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(errorMessage(res.status, body));
  return body as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function upload(form: FormData, onProgress: (fraction: number) => void) {
  return new Promise<{ listing_id: string; job_id: string }>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/listings");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300 ? resolve(xhr.response) : reject(new Error(errorMessage(xhr.status, xhr.response)));
    xhr.onerror = () => reject(new Error("The upload didn't reach the server. Check the connection and try again."));
    xhr.send(form);
  });
}

export const api = {
  listings: () => request<ListingSummary[]>("/listings"),
  listing: (id: string) => request<Listing>(`/listings/${id}`),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  upload,
  review: (id: string, body: ReviewBody) => request<Listing>(`/listings/${id}/review`, json(body)),
  publish: (id: string) => request<Listing>(`/listings/${id}/publish`, { method: "POST" }),
  page: (id: string) => request<PublishedPage>(`/listings/${id}/page`),
};

export const media = (path: string) => `/api/media/${path}`;

const SYMBOLS: Record<string, string> = { USD: "$", GBP: "£", EUR: "€" };

export function money(amount: number, currency = "USD"): string {
  return `${SYMBOLS[currency] ?? ""}${Math.round(amount).toLocaleString("en-US")}`;
}

export function factLine(f: Facts): string {
  return [
    f.beds != null && `${f.beds} bed`,
    f.baths != null && `${f.baths} bath`,
    f.sqft != null && `${f.sqft.toLocaleString("en-US")} sq ft`,
  ]
    .filter(Boolean)
    .join("  ·  ");
}

export function shortDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
}
