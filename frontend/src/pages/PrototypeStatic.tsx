import { useEffect, useRef, useState } from "react";
import { HoverNav } from "../components/Shell";
import { loadManifest, type Manifest } from "../components/prototype/manifest";
import { StaticScene, STATIC_ASSETS } from "../components/static/StaticScene";

const HEADER = "Static-image small clip — Not a real listing — AI-modified — Proof of concept";
const FOOTER = "Static-image small clip — Not a real listing — AI-modified";

type Phase = "loading" | "missing" | "playing" | "landed";

export default function PrototypeStatic() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const img = useRef<HTMLImageElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const scene = useRef<StaticScene | null>(null);

  useEffect(() => {
    document.title = "Static-image small clip";
    let live = true;
    loadManifest()
      .then(async (m: Manifest) => {
        if (!live || !canvas.current || !stage.current) return;
        const style = m.styles.find((s) => s.available);
        if (!style?.pieces?.length) throw new Error("no staged pieces in the manifest");
        const s = new StaticScene(canvas.current, m.camera, m.video.width / m.video.height, () => live && setPhase("landed"));
        scene.current = s;
        const box = stage.current;
        const fit = () => s.resize(box.clientWidth, box.clientHeight);
        fit();
        const observer = new ResizeObserver(fit);
        observer.observe(box);
        await s.build(style.pieces);
        if (!live) return;
        setPhase("playing");
        s.replay();
        if (import.meta.env.DEV) {
          (window as unknown as { __staticClip?: unknown }).__staticClip = {
            freeze: (t: number) => s.freeze(t),
            landed: () => s.showLanded(),
            replay: () => s.replay(),
            duration: () => s.duration,
            snapshot: () => {
              const photo = img.current!;
              const out = document.createElement("canvas");
              out.width = s.renderer.domElement.width;
              out.height = s.renderer.domElement.height;
              const ctx = out.getContext("2d")!;
              ctx.drawImage(photo, 0, 0, out.width, out.height);
              s.renderNow();
              ctx.drawImage(s.renderer.domElement, 0, 0);
              return out.toDataURL("image/png");
            },
          };
        }
        return () => observer.disconnect();
      })
      .catch((e: Error) => {
        if (!live) return;
        setError(e.message);
        setPhase("missing");
      });
    return () => {
      live = false;
      scene.current?.dispose();
      scene.current = null;
    };
    // Built once: manifest, camera and pieces are fixed for this photo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function record() {
    const s = scene.current;
    const photo = img.current;
    if (!s || !photo) return;
    const out = document.createElement("canvas");
    out.width = 1280;
    out.height = 720;
    const ctx = out.getContext("2d")!;
    const stream = out.captureStream(60);
    const rec = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported("video/webm;codecs=vp9") ? "video/webm;codecs=vp9" : "video/webm" });
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const stopped = new Promise<void>((res) => (rec.onstop = () => res()));
    setPhase("playing");
    s.replay();
    rec.start();
    const t0 = performance.now();
    await new Promise<void>((done) => {
      const draw = () => {
        ctx.drawImage(photo, 0, 0, out.width, out.height);
        s.renderNow();
        ctx.drawImage(s.renderer.domElement, 0, 0, out.width, out.height);
        if (performance.now() - t0 < (s.duration + 0.3) * 1000) requestAnimationFrame(draw);
        else done();
      };
      draw();
    });
    rec.stop();
    await stopped;
    const blob = new Blob(chunks, { type: "video/webm" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "static-clip.webm";
    a.click();
    URL.revokeObjectURL(a.href);
    setPhase("landed");
  }

  const status: Record<Phase, string> = {
    loading: "Loading the photo and furniture",
    missing: "",
    playing: "Furnishing · real 3D pieces, rendered shadows",
    landed: "Landed · hold — Replay drops them again",
  };

  return (
    <div className="fixed inset-0 flex flex-col bg-night text-ivory">
      <header className="relative z-40 flex h-16 items-center px-6 pr-20 sm:px-10 sm:pr-24">
        <p className="eyebrow flex items-center gap-2.5 text-ivory/80!">
          <span className="ice-dot" />
          {HEADER}
        </p>
        <div className="absolute right-6 top-3 sm:right-10">
          <HoverNav />
        </div>
      </header>

      <main className="flex min-h-0 flex-1 items-center justify-center px-6 py-4 sm:px-10" style={{ containerType: "size" }}>
        <div
          ref={stage}
          className="relative overflow-hidden rounded-2xl bg-smoke"
          style={{ width: "min(100cqw, calc(100cqh * 16 / 9))", aspectRatio: "16 / 9" }}
        >
          <img
            ref={img}
            src={STATIC_ASSETS.photo}
            alt="Static photo of an empty living room, the single input to this clip"
            className="absolute inset-0 h-full w-full object-fill"
          />
          <canvas ref={canvas} aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" />
          {phase === "missing" && (
            <div className="absolute inset-0 grid place-items-center bg-night/80 p-8 text-center">
              <div className="max-w-md">
                <p className="font-serif text-xl text-ivory/90">The static-clip assets are not built on this computer.</p>
                <p className="mt-4 text-sm leading-relaxed text-ash">
                  Run <span className="font-mono text-ivory/80">make prototype</span> for the photo manifest, and put
                  the GLB furniture in <span className="font-mono text-ivory/80">frontend/public/static-clip/</span>.
                  {error ? ` (${error})` : ""}
                </p>
              </div>
            </div>
          )}
        </div>
      </main>

      <footer className="flex flex-wrap items-center gap-x-6 gap-y-3 px-6 pb-5 sm:px-10">
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => { scene.current?.replay(); setPhase("playing"); }} disabled={phase === "loading" || phase === "missing"} className="btn-glass min-w-28">
            Replay clip
          </button>
          <button type="button" onClick={() => void record()} disabled={phase === "loading" || phase === "missing"} className="btn-glass">
            Record clip (.webm)
          </button>
        </div>
        <p role="status" aria-live="polite" className="min-w-0 flex-1 font-mono text-[11px] leading-relaxed text-ivory/60">
          {status[phase]}
        </p>
        <p className="eyebrow text-ivory/70!">{FOOTER}</p>
      </footer>
    </div>
  );
}
