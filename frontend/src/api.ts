export type Evidence =
  | { kind: "fact"; ref: string; value: unknown }
  | { kind: "visual"; ref: string; frame: string; room_id: string; text: string; t: number | null }
  | { kind: "broker"; ref: string }
  | { kind: "unknown"; ref: string };
export type Claim = { id?: string; text: string; evidence: Evidence[] };

export type Box = { concept: string; box: [number, number, number, number]; score: number | null };

export type Frame = {
  id: string;
  raw: string | null;
  path: string | null;
  t: number | null;
  upload: number;
  width: number | null;
  height: number | null;
  sharpness: number | null;
  sam: { privacy: Box[]; structure: Box[] } | null;
  wonder: {
    room_key: string;
    room_type: string;
    usable: boolean;
    coverage: number;
    observations: { id: string; text: string }[];
    condition: string;
  } | null;
  blur: { regions: number } | null;
};

export type Staging = {
  model: string | null;
  prompt: string;
  style: string;
  error: string | null;
  level?: number;
  purpose?: string;
  at?: string;
};

export type Room = {
  id: string;
  name: string;
  type: string;
  source_frame: string | null;
  before: string | null;
  after: string | null;
  style: string | null;
  frames: string[];
  hero_reason: string;
  staging: Staging | null;
  staging_history?: (Staging & { after: string | null; replaced_at: string })[];
  restage_error?: { level: number; error: string; at: string };
  rejected: boolean;
  /** Hero frame time in the walkthrough video, and the room's unbroken segment. */
  t?: number | null;
  span?: [number | null, number | null] | null;
  upload?: number | null;
  /** The main living space: the hero room. */
  main?: boolean;
};

/** Coverage of one uploaded video, plus the blurred copy the listing page plays. */
export type VideoCoverage = {
  upload: number;
  duration: number;
  fps: number;
  extracted: number;
  expected: number;
  first_t: number | null;
  last_t: number | null;
  kept?: number;
  path?: string | null;
  status?: "ready" | "held" | "failed";
  detail?: string;
  note?: string;
  blurred_boxes?: number;
  width?: number;
  height?: number;
};

export type PublishedVideo = { path: string; duration: number; width: number; height: number; upload: number; note: string | null };

export type MainRoom = { room: string | null; found: boolean; detail: string; name?: string; t?: number | null; span?: [number | null, number | null] };

export type TokenGuard = {
  main_room: string | null;
  status: "main_first" | "no_main_room" | "main_failed";
  detail: string;
  order: string[];
  skipped: string[];
  at: string;
};

export type LiveEligibility = { eligible: boolean; reason: string | null; status: "preparing" | "ready" | "failed" | null; main_room?: string; main_room_name?: string };

export type ChecklistStatus = "open" | "generated" | "failed" | "done" | "flagged";
export type ChecklistItem = { id: string; label: string; status: ChecklistStatus; detail: string; updated_at: string };
export type Checklist = { created_at: string; items: ChecklistItem[] };

export type Check = {
  id: string;
  item: string;
  kind: "code" | "meta";
  target: Record<string, unknown>;
  status: "pass" | "fail" | "unclear";
  reason: string;
  model: string | null;
};
export type Flag = { id: string; item: string; target: Record<string, unknown>; message: string; resolution: string };
export type Verification = { ran_at: string; passed: boolean; checks: Check[]; flags: Flag[] };

export type TraceEntry = {
  id: string;
  model: string;
  purpose: string;
  target: Record<string, unknown>;
  at: string;
  ms: number;
  ok: boolean;
  error: string | null;
  cached: boolean;
  summary: string;
};

export type MetaStatus = {
  configured: boolean;
  base_url: string | null;
  models: { spark: string; wonder: string; image: string; sam: string };
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
  sentences: Claim[];
  highlights: Claim[];
  evidence: Record<string, Evidence[]>;
  generator: { model: string | null; note: string };
};

export type Job = {
  id: string;
  listing_id: string;
  kind: "listing" | "verify" | "restage" | "live";
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
  verification: { passed: boolean; ran_at: string; checks: number; open?: number };
  video: PublishedVideo | null;
  note: string | null;
  live: LiveEligibility;
};

export type Listing = {
  id: string;
  source: "upload" | "seed";
  status: ListingStatus;
  facts: Facts;
  uploads: { name: string; kind: "video" | "photo" }[];
  frames: Frame[];
  rooms: Room[];
  style: string;
  checklist: Checklist;
  verification: Verification | null;
  trace: TraceEntry[];
  copy?: Copy;
  comps?: Comps;
  review: {
    decision: "approved" | "rejected" | null;
    decided_at: string | null;
    notes: string;
    edited_fields: string[];
    open_checks?: string[];
  };
  job: Job | null;
  error?: string;
  note?: string;
  published?: PublishedPage;
  videos?: VideoCoverage[];
  main_room?: MainRoom;
  token_guard?: TokenGuard;
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

export type GeometryCheck = { status: "pass" | "fail"; reason: string; correlation: number | null };
export type StructureCheck = { status: "pass" | "fail" | "not_checked"; reason: string; outside_view?: string[]; corrected?: boolean };
/** box = x1, y1, x2, y2 normalized 0..1 on the style image. */
export type Piece = { concept: string; box: [number, number, number, number]; score: number | null };
/** Maps a generated image into the filmed frame: frame = s * image + b, per axis. */
export type Align = { sx: number; sy: number; bx: number; by: number };
export type LiveStyle = {
  label: string;
  image: string | null;
  source: "stage1" | "live";
  attempts?: number;
  available: boolean;
  error: string | null;
  geometry: GeometryCheck | null;
  structure: StructureCheck | null;
  pieces: Piece[];
  /** Alignment of this image to the filmed frame, and its furniture mask (frame coordinates). */
  align?: Align;
  mask?: string | null;
};
export type LiveRoom = {
  id: string;
  name: string;
  type: string;
  main?: boolean;
  t?: number | null;
  span?: [number | null, number | null] | null;
  before: string | null;
  plate: string | null;
  plate_source: "before" | "generated";
  plate_check: GeometryCheck | null;
  /** True when the plate is the as-filmed frame and SAM found furniture in it. */
  plate_furnished?: boolean;
  plate_align?: Align;
  styles: Record<string, LiveStyle>;
  window: [number, number, number, number] | null;
  size: [number, number] | null;
};
/** Every published room on the video timeline; `prepared` rooms are where the walk stops. */
export type WalkStop = { id: string; name: string; type: string; t: number; span: [number | null, number | null] | null; main: boolean; prepared: boolean };
export type LiveMoment = {
  id: "coffee" | "sit" | "view";
  label: string;
  room_id: string;
  focus: [number, number, number, number];
  images: Record<string, string>;
};
export type LivePayload = {
  listing_id: string;
  residence: string | null;
  status: "preparing" | "ready" | "failed";
  job_id: string | null;
  error: string | null;
  prepared_at: string | null;
  title: string;
  facts: Facts;
  price_display: string | null;
  approved_at: string;
  published_at: string;
  note: string | null;
  styles: { id: string; label: string }[];
  default_style: string;
  rooms: LiveRoom[];
  moments: LiveMoment[];
  video: PublishedVideo | null;
  path: WalkStop[];
  guard: { main_room: string; order: string[]; skipped_utility: string[]; held: string[] } | null;
  calls: number;
  calls_by_purpose: Record<string, number>;
};
export type Reservation = {
  id: string;
  listing_id: string;
  status: "pending_broker_confirmation";
  simulated: true;
  created_at: string;
  charged: false;
  payment_taken: false;
  provider: null;
  message: string;
};

export type ReviewBody = {
  action: "save" | "approve" | "reject";
  copy_edit?: { title: string; description: string; highlights: string[] };
  rejected_rooms?: string[];
  test_listing?: boolean;
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
  deleteListing: (id: string) => request<{ deleted: boolean }>(`/listings/${id}`, { method: "DELETE" }),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  upload,
  review: (id: string, body: ReviewBody) => request<Listing>(`/listings/${id}/review`, json(body)),
  publish: (id: string) => request<Listing>(`/listings/${id}/publish`, { method: "POST" }),
  unpublish: (id: string) => request<Listing>(`/listings/${id}/unpublish`, { method: "POST" }),
  page: (id: string) => request<PublishedPage>(`/listings/${id}/page`),
  metaStatus: () => request<MetaStatus>("/meta/status"),
  settings: () => request<{ blocking_checks: boolean }>("/settings"),
  reprocess: (id: string) => request<{ listing_id: string; job_id: string }>(`/listings/${id}/reprocess`, { method: "POST" }),
  live: (id: string) => request<LivePayload>(`/listings/${id}/live`),
  rerunLiveStyle: (id: string, room: string, style: string) => request<{ job_id: string }>(`/listings/${id}/live/rooms/${encodeURIComponent(room)}/styles/${encodeURIComponent(style)}/rerun`, { method: "POST" }),
  /** `residence` only links a Miami listing to the seeded home-page residence; any listing can be prepared. */
  prepareLive: (id: string, residence: string | null = null) =>
    request<{ listing_id: string; job_id: string }>(`/listings/${id}/live`, json({ residence })),
  residenceLive: (residenceId: string) =>
    request<{ listing_id: string; status: "preparing" | "ready" | "failed" }>(`/residences/${residenceId}/live`),
  reserve: (id: string) => request<Reservation>(`/listings/${id}/reserve`, { method: "POST" }),
  verify: (id: string) => request<{ listing_id: string; job_id: string }>(`/listings/${id}/verify`, { method: "POST" }),
  restage: (id: string, roomId: string) =>
    request<{ listing_id: string; job_id: string; room_id: string; level: number }>(
      `/listings/${id}/rooms/${roomId}/restage`,
      { method: "POST" },
    ),
};

export const media = (path: string) => `/api/media/${path}`;

export const exportLogsUrl = (id: string) => `/api/listings/${id}/export`;

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

export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function shortTime(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : "";
}

export function shortDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
}
