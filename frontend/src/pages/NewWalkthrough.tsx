import { useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, clock } from "../api";

const ACCEPT = "video/mp4,video/quicktime,video/x-m4v,video/webm,image/jpeg,image/png,image/webp";
const CITIES = ["Miami", "Los Angeles", "New York"];
const STYLES = [
  { value: "modern-luxury", label: "Modern luxury" },
  { value: "coastal", label: "Coastal" },
  { value: "minimal", label: "Minimal" },
  { value: "2142", label: "Cyberpunk concept", note: "AI-imagined" },
];
const TIPS = ["Walk slowly, one steady pass", "Cover every room once", "Daylight, lights on"];

function Field({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="eyebrow mb-2 block">{label}</span>
      {children}
    </label>
  );
}

function size(bytes: number) {
  return bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${Math.ceil(bytes / 1e3)} KB`;
}

/** A chosen file as a thumbnail: first frame for video, the image itself for photos. */
function FilePreview({ file, url, onRemove }: { file: File; url: string; onRemove: () => void }) {
  const [duration, setDuration] = useState<number | null>(null);
  const video = file.type.startsWith("video/");
  return (
    <li className="group relative min-w-0 animate-fade-in [animation-duration:0.4s]">
      <div className="relative aspect-[4/3] overflow-hidden rounded-xl bg-smoke ring-1 ring-ivory/10">
        {video ? (
          <video src={`${url}#t=0.1`} muted playsInline preload="metadata" onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)} className="h-full w-full object-cover" aria-hidden />
        ) : (
          <img src={url} alt="" className="h-full w-full object-cover" />
        )}
        {video && duration != null && <span className="absolute bottom-2 left-2 rounded-full bg-night/70 px-2 py-0.5 font-mono text-micro tabular-nums text-ivory backdrop-blur">{clock(duration)}</span>}
        <button
          type="button"
          aria-label={`Remove ${file.name}`}
          onClick={onRemove}
          className="absolute right-1.5 top-1.5 grid h-8 w-8 place-items-center rounded-full bg-night/70 text-ivory/85 backdrop-blur transition hover:bg-night hover:text-ivory pointer-coarse:h-10 pointer-coarse:w-10"
        >
          ×
        </button>
      </div>
      <p className="mt-2 truncate text-xs text-ivory/85" title={file.name}>{file.name}</p>
      <p className="font-mono text-micro text-ash">{size(file.size)}</p>
    </li>
  );
}

export default function NewWalkthrough() {
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [estimate, setEstimate] = useState(false);
  const [test, setTest] = useState(false);
  const [style, setStyle] = useState("modern-luxury");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [facts, setFacts] = useState({ city: "", beds: "" });

  const add = (list: FileList | null) => list && setFiles((prev) => [...prev, ...Array.from(list)]);
  const urls = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => urls.forEach((u) => URL.revokeObjectURL(u)), [urls]);

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    add(e.dataTransfer.files);
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!files.length) return setError("Add a walkthrough video or photos first.");
    const form = new FormData(e.currentTarget);
    files.forEach((f) => form.append("files", f));
    form.set("estimate_price", String(estimate));
    form.set("test_listing", String(test));
    form.set("style", style);
    setError("");
    setProgress(0);
    try {
      const { listing_id } = await api.upload(form, setProgress);
      navigate(`/listings/${listing_id}`);
    } catch (err) {
      setError((err as Error).message);
      setProgress(null);
    }
  }

  const uploading = progress !== null;
  const videos = files.filter((f) => f.type.startsWith("video/")).length;
  const photos = files.length - videos;
  const summary = [
    files.length ? [videos && `${videos} ${videos === 1 ? "video" : "videos"}`, photos && `${photos} ${photos === 1 ? "photo" : "photos"}`].filter(Boolean).join(" + ") : "No walkthrough yet",
    facts.city.trim(),
    facts.beds.trim() && `${facts.beds.trim()} bed`,
    STYLES.find((s) => s.value === style)?.label,
  ].filter(Boolean);

  return (
    <form
      onSubmit={submit}
      onInput={(e) => {
        const data = new FormData(e.currentTarget);
        setFacts({ city: String(data.get("city") ?? ""), beds: String(data.get("beds") ?? "") });
      }}
    >
      <h1 className="text-balance text-[clamp(3rem,11vw,6rem)] font-[200] leading-[0.95] tracking-tight">Bring the walkthrough.</h1>
      <p className="mt-6 max-w-lg text-ash">
        One steady pass through the empty unit is enough. Add the facts you know; nothing else gets claimed.
      </p>

      <div className="mt-12 grid grid-cols-1 gap-10 sm:mt-14 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-14">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`glass flex flex-col p-5 transition duration-300 sm:p-8 ${dragging ? "bg-ice/[0.06] shadow-[inset_0_0_0_1px_rgb(155_230_239/0.45)]!" : ""}`}
        >
          {files.length === 0 ? (
            <div className="grid flex-1 place-items-center py-8 text-center sm:py-12">
              <div>
                <span className={`mx-auto grid h-16 w-16 place-items-center rounded-full ring-1 transition ${dragging ? "ring-ice/60" : "ring-ivory/15"}`}>
                  <span className="ice-dot" />
                </span>
                <p className="mt-6 text-xl font-light">{dragging ? "Drop to add" : "Drop a phone walkthrough"}</p>
                <button type="button" onClick={() => input.current?.click()} className="btn-glass mt-5">
                  Choose video or photos
                </button>
                <p className="eyebrow mt-6 text-balance">MP4, MOV, WebM up to 3 min · JPG, PNG, WebP</p>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 flex-col">
              <div className="flex items-baseline justify-between gap-4">
                <p className="eyebrow">Walkthrough · {files.length} {files.length === 1 ? "file" : "files"}</p>
                <button type="button" onClick={() => input.current?.click()} className="btn-ghost text-sm text-ash">
                  Add more
                </button>
              </div>
              <ul className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
                {files.map((f, i) => (
                  <FilePreview key={urls[i]} file={f} url={urls[i]} onRemove={() => setFiles((prev) => prev.filter((_, j) => j !== i))} />
                ))}
              </ul>
              <button
                type="button"
                onClick={() => input.current?.click()}
                className={`mt-4 grid min-h-20 flex-1 place-items-center rounded-xl border border-dashed text-sm transition ${dragging ? "border-ice/60 text-ice" : "border-ivory/15 text-ash hover:border-ivory/35 hover:text-ivory"}`}
              >
                {dragging ? "Drop to add" : "Drop more files here, or tap to choose"}
              </button>
            </div>
          )}
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPT}
            className="sr-only"
            tabIndex={-1}
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
          <ol className="mt-6 grid gap-3 border-t border-ivory/10 pt-5 sm:grid-cols-3 sm:gap-4">
            {TIPS.map((tip, i) => (
              <li key={tip} className="flex items-baseline gap-3 text-sm text-ivory/75 sm:flex-col sm:gap-1">
                <span className="font-mono text-micro text-ice/80">{String(i + 1).padStart(2, "0")}</span>
                {tip}
              </li>
            ))}
          </ol>
        </div>

        <div className="min-w-0 space-y-6">
          <Field label="Address">
            <input name="address" className="field" placeholder="Building, unit, street" autoComplete="off" />
          </Field>
          <Field label="City">
            <input name="city" list="cities" className="field" placeholder="e.g. Miami" autoComplete="off" />
            <datalist id="cities">
              {CITIES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </Field>
          <div className="grid grid-cols-3 gap-4">
            <Field label="Beds">
              <input name="beds" inputMode="decimal" className="field max-sm:px-3" placeholder="3" />
            </Field>
            <Field label="Baths">
              <input name="baths" inputMode="decimal" className="field max-sm:px-3" placeholder="2.5" />
            </Field>
            <Field label="Sq ft">
              <input name="sqft" inputMode="numeric" className="field max-sm:px-3" placeholder="2,150" />
            </Field>
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)_7rem] gap-4">
            <Field label="Asking price">
              <input name="price" inputMode="numeric" className="field disabled:opacity-40" placeholder={estimate ? "Estimated from comps" : "e.g. 4,850,000"} disabled={estimate} />
            </Field>
            <Field label="Currency">
              <select name="currency" className="field" defaultValue="USD">
                <option>USD</option>
                <option>GBP</option>
                <option>EUR</option>
              </select>
            </Field>
          </div>
          <div>
            <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm text-ivory/85">
              <input type="checkbox" checked={estimate} onChange={(e) => setEstimate(e.target.checked)} className="check" />
              Estimate the price from comparable sales
            </label>
            <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm text-ivory/85">
              <input type="checkbox" checked={test} onChange={(e) => setTest(e.target.checked)} className="check" />
              Test upload · label it "Not a real listing" everywhere
            </label>
          </div>

          <fieldset>
            <legend className="eyebrow mb-3">Staging style</legend>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {STYLES.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  aria-pressed={style === s.value}
                  onClick={() => setStyle(s.value)}
                  className="group self-start text-left"
                >
                  <span className={`relative block aspect-[4/3] overflow-hidden rounded-xl ring-1 transition duration-300 ${style === s.value ? "ring-2 ring-ice/80 shadow-[0_0_24px_-6px_rgb(155_230_239/0.55)]" : "ring-ivory/10 group-hover:ring-ivory/35 [@media(hover:hover)]:group-hover:shadow-[0_0_22px_-8px_rgb(155_230_239/0.45)]"}`}>
                    <img src={`/styles/${s.value}.jpg`} alt="" loading="lazy" className={`h-full w-full object-cover transition duration-500 ${style === s.value ? "" : "opacity-70 group-hover:opacity-100"}`} />
                    {style === s.value && <span aria-hidden className="ice-dot absolute right-2 top-2" />}
                  </span>
                  <span className={`mt-2 block text-sm transition ${style === s.value ? "text-ivory" : "text-ivory/70 group-hover:text-ivory"}`}>{s.label}</span>
                  {s.note && <span className="block text-micro text-ash">{s.note}</span>}
                </button>
              ))}
            </div>
          </fieldset>
        </div>
      </div>

      <div className="glass fixed inset-x-3 bottom-[calc(0.75rem+env(safe-area-inset-bottom))] z-30 flex items-center gap-3 overflow-hidden rounded-3xl! py-1.5 pl-5 pr-1.5 sm:inset-x-auto sm:bottom-6 sm:right-[max(1.5rem,calc((100vw-80rem)/2+2.5rem))] sm:max-w-[min(44rem,calc(100vw-3rem))] sm:rounded-full!">
        {uploading && <span aria-hidden className="absolute inset-x-0 top-0 h-px origin-left bg-ice/80 shadow-glow transition-transform duration-300" style={{ transform: `scaleX(${progress})` }} />}
        <p className="min-w-0 flex-1 truncate text-xs text-ivory/75 sm:text-sm" aria-live="polite">
          {error ? <span role="alert" className="text-rose">{error}</span> : uploading ? <span className="font-mono tabular-nums text-ice">Uploading · {Math.round(progress * 100)}%</span> : summary.join(" · ")}
        </p>
        <button type="submit" className="btn-primary shrink-0" disabled={uploading}>
          {uploading ? "Uploading" : "Process walkthrough"}
        </button>
      </div>
    </form>
  );
}
