import { useRef, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const ACCEPT = "video/mp4,video/quicktime,video/x-m4v,video/webm,image/jpeg,image/png,image/webp";
const CITIES = ["Miami", "Los Angeles", "New York"];
const STYLES = [
  { value: "modern-luxury", label: "Modern luxury" },
  { value: "coastal", label: "Coastal" },
  { value: "minimal", label: "Minimal" },
  { value: "2142", label: "Cyberpunk concept" },
];

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

  const add = (list: FileList | null) => list && setFiles((prev) => [...prev, ...Array.from(list)]);

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

  return (
    <form onSubmit={submit}>
      <h1 className="text-6xl font-[200] tracking-tight sm:text-8xl">Bring the walkthrough.</h1>
      <p className="mt-5 max-w-lg text-ash">
        One steady pass through the empty unit is enough. Add the facts you know; nothing else gets claimed.
      </p>

      <div className="mt-14 grid gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`glass grid min-h-[380px] place-items-center p-10 text-center transition ${dragging ? "bg-ice/[0.06]" : ""}`}
          >
            <div>
              <span className="mx-auto grid h-16 w-16 place-items-center rounded-full ring-1 ring-ivory/15">
                <span className="ice-dot" />
              </span>
              <p className="mt-6 text-xl font-light">Drop a phone walkthrough</p>
              <button type="button" onClick={() => input.current?.click()} className="btn-glass mt-5">
                Choose video or photos
              </button>
              <p className="eyebrow mt-6">MP4, MOV, WebM up to 3 min · JPG, PNG, WebP</p>
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
            </div>
          </div>
          {files.length > 0 && (
            <ul className="mt-4 space-y-1.5">
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-4 rounded-xl px-4 py-2.5 odd:bg-ivory/[0.025]">
                  <span className="truncate text-sm">{f.name}</span>
                  <span className="flex items-center gap-4">
                    <span className="font-mono text-xs text-ash">{size(f.size)}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${f.name}`}
                      onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                      className="text-ash transition hover:text-ivory"
                    >
                      Remove
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-6">
          <Field label="Address">
            <input name="address" className="field" placeholder="Building, unit, street" autoComplete="off" />
          </Field>
          <Field label="City">
            <input name="city" list="cities" className="field" placeholder="Miami" autoComplete="off" />
            <datalist id="cities">
              {CITIES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </Field>
          <div className="grid grid-cols-3 gap-4">
            <Field label="Beds">
              <input name="beds" inputMode="decimal" className="field" placeholder="3" />
            </Field>
            <Field label="Baths">
              <input name="baths" inputMode="decimal" className="field" placeholder="2.5" />
            </Field>
            <Field label="Sq ft">
              <input name="sqft" inputMode="numeric" className="field" placeholder="2,150" />
            </Field>
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)_7rem] gap-4">
            <Field label="Asking price">
              <input name="price" inputMode="numeric" className="field disabled:opacity-40" placeholder="4,850,000" disabled={estimate} />
            </Field>
            <Field label="Currency">
              <select name="currency" className="field" defaultValue="USD">
                <option>USD</option>
                <option>GBP</option>
                <option>EUR</option>
              </select>
            </Field>
          </div>
          <label className="flex cursor-pointer items-center gap-3 text-sm text-ivory/85">
            <input type="checkbox" checked={estimate} onChange={(e) => setEstimate(e.target.checked)} className="h-4 w-4 accent-[#9be6ef]" />
            Estimate the price from comparable sales
          </label>
          <label className="flex cursor-pointer items-center gap-3 text-sm text-ivory/85">
            <input type="checkbox" checked={test} onChange={(e) => setTest(e.target.checked)} className="h-4 w-4 accent-[#9be6ef]" />
            Test upload · label it "Not a real listing" everywhere
          </label>

          <fieldset>
            <legend className="eyebrow mb-2">Staging style</legend>
            <div className="glass flex w-fit gap-0.5 rounded-full! p-1 text-sm">
              {STYLES.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  aria-pressed={style === s.value}
                  onClick={() => setStyle(s.value)}
                  className={`rounded-full px-4 py-1.5 transition ${style === s.value ? "bg-ivory/90 text-night" : "text-ivory/80 hover:text-ivory"}`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </fieldset>

          {error && (
            <p role="alert" className="text-sm text-rose">
              {error}
            </p>
          )}

          <div className="flex items-center gap-5 pt-4">
            <button type="submit" className="btn-primary" disabled={uploading}>
              {uploading ? "Uploading" : "Process walkthrough"}
            </button>
            {uploading && (
              <span className="font-mono text-xs tabular-nums text-ice" aria-live="polite">
                {Math.round(progress * 100)}%
              </span>
            )}
          </div>
        </div>
      </div>
    </form>
  );
}
