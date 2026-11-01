import type { Job } from "../api";

const STAGES = [
  { id: "frames", label: "Frames", detail: "Sampling the walkthrough" },
  { id: "masks", label: "Masks", detail: "SAM 3.1 finding faces, photos, windows" },
  { id: "privacy", label: "Privacy", detail: "Blurring faces and personal items" },
  { id: "video", label: "Video", detail: "Blurred full walkthrough for the listing page" },
  { id: "rooms", label: "Rooms", detail: "Wonder classifying each space" },
  { id: "staging", label: "Staging", detail: "Furnishing each room" },
  { id: "copy", label: "Copy", detail: "Spark writing from evidence" },
  { id: "comps", label: "Comps", detail: "Pricing against comparables" },
  { id: "verify", label: "Verify", detail: "Independent checks" },
  { id: "ready", label: "Ready", detail: "Waiting for broker review" },
];

type StepState = "done" | "active" | "failed" | "pending";

const DOT: Record<StepState, string> = {
  done: "bg-ivory/70",
  active: "ice-dot animate-pulse",
  failed: "bg-rose",
  pending: "bg-ivory/15",
};

const LABEL: Record<StepState, string> = {
  done: "text-ivory/70",
  active: "text-ivory",
  failed: "text-rose",
  pending: "text-ash",
};

/** The pipeline read like a lift indicator: stages are floors, the current one is lit. */
export default function PipelineIndicator({ job }: { job: Job | null }) {
  const done = job?.status === "done";
  const failed = job?.status === "failed";
  const current = done ? STAGES.length - 1 : STAGES.findIndex((s) => s.id === job?.stage);
  const floor = current < 0 ? null : STAGES[current];

  const stateOf = (i: number): StepState => {
    if (done || i < current) return "done";
    if (i === current) return failed ? "failed" : "active";
    return "pending";
  };

  return (
    <div className="grid grid-cols-1 items-end gap-10 sm:grid-cols-[auto_1fr] sm:gap-12">
      <div aria-live="polite">
        <p className="eyebrow">{failed ? "Stopped at" : done ? "Arrived" : "Now on"}</p>
        <p className="mt-2 font-sans text-8xl leading-none font-[150] tracking-tighter tabular-nums text-ivory sm:text-[9rem]">
          {floor ? String(current + 1).padStart(2, "0") : "00"}
        </p>
        <p className="mt-3 text-lg font-light text-ivory/85">{floor ? floor.label : "Queued"}</p>
        <p className="text-sm text-ash">{floor ? floor.detail : "Waiting for a worker"}</p>
      </div>
      <ol aria-label="Processing stages" className="flex flex-col-reverse gap-3 sm:justify-self-end">
        {STAGES.map((s, i) => {
          const state = stateOf(i);
          return (
            <li key={s.id} aria-current={state === "active" ? "step" : undefined} className="flex items-center gap-4">
              <span className="w-6 text-right font-mono text-caption tabular-nums text-ash">{String(i + 1).padStart(2, "0")}</span>
              <span className={`h-1.5 w-1.5 rounded-full ${DOT[state]}`} />
              <span className={`text-sm tracking-wide ${LABEL[state]}`}>{s.label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
