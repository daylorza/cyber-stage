import { useEffect, useRef, useState } from "react";
import { HoverNav, Wordmark } from "../components/Shell";
import { CascadeScene } from "../components/prototype/CascadeScene";
import { ASSET_ROOT, generalRoot, loadManifest, type Manifest } from "../components/prototype/manifest";

const HEADER = "Prototype Testing — Not a real listing — AI-modified — Proof of concept";
const FOOTER = "Prototype Testing — Not a real listing — AI-modified";
/** Walk in at half speed: the room should be felt, not skimmed. */
const WALK_RATE = 0.5;
/** The beat between stopping in the living room and the first piece leaving the ceiling. */
const ARRIVE_BEAT_MS = 0;

type Phase = "loading" | "missing" | "ready" | "walking" | "paused" | "arriving" | "furnishing" | "furnished" | "ended";
const AT_ROOM: Phase[] = ["arriving", "furnishing", "furnished"];

const stamp = (s: number) => `0:${s.toFixed(1).padStart(4, "0")}`;

function PlayIcon({ playing }: { playing: boolean }) {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="currentColor" aria-hidden>
      {playing ? <path d="M4 3h3v10H4zM9 3h3v10H9z" /> : <path d="M4.5 2.8v10.4L13 8z" />}
    </svg>
  );
}

export default function PrototypeTesting() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [phase, setPhaseState] = useState<Phase>("loading");
  const [styleId, setStyleId] = useState<string | null>(null);
  const [time, setTime] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const scene = useRef<CascadeScene | null>(null);
  const meta = useRef<Manifest | null>(null);
  /** Work 3: ?listing=<id> renders that listing's generalised cascade assets
   *  (built by prototype.general); no param keeps the POC prototype. */
  const [assetRoot] = useState(() => {
    const id = new URLSearchParams(window.location.search).get("listing");
    return id ? generalRoot(id) : ASSET_ROOT;
  });
  const isGeneral = assetRoot !== ASSET_ROOT;
  const phaseRef = useRef<Phase>("loading");
  /** The hero frame stops the walk once per pass through the clip. */
  const armed = useRef(true);
  const busy = useRef(false);
  const timer = useRef(0);

  const go = (p: Phase) => {
    phaseRef.current = p;
    setPhaseState(p);
  };

  useEffect(() => {
    document.title = "Prototype Testing";
    loadManifest(assetRoot)
      .then((m) => {
        meta.current = m;
        setManifest(m);
        setStyleId(m.styles.find((s) => s.available)?.id ?? null);
      })
      .catch(() => go("missing"));
    return () => clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The Three.js layer: one canvas over the video, same box, resized with it.
  useEffect(() => {
    if (!manifest || !canvas.current || !stage.current) return;
    const s = new CascadeScene(canvas.current, manifest.camera, manifest.video.width / manifest.video.height, assetRoot);
    scene.current = s;
    const box = stage.current;
    const fit = () => s.resize(box.clientWidth, box.clientHeight);
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(box);
    let live = true;
    const first = manifest.styles.find((st) => st.available);
    // QA in dev: ?hold keeps the walk from starting (headless Chrome cannot screenshot a playing 4K video).
    const hold = import.meta.env.DEV && new URLSearchParams(window.location.search).has("hold");
    (first ? s.setStyle(first) : Promise.resolve()).then(() => {
      if (!live) return;
      go("ready");
      const v = video.current;
      if (!v || hold) return;
      v.playbackRate = WALK_RATE;
      v.play().then(
        () => live && go("walking"),
        () => live && go("paused"),
      );
    });
    if (import.meta.env.DEV) {
      // QA handle for screenshots: hold the hero frame, freeze the cascade at a time.
      (window as unknown as { __prototype?: unknown }).__prototype = {
        hero: () => holdHero(),
        freeze: (t: number) => s.freeze(t),
        landed: () => s.showLanded(),
        ready: () => phaseRef.current !== "loading",
        /** The stage as shown (video frame + Three.js layer), as a PNG data URL. */
        snapshot: () => {
          const v = video.current!;
          const out = document.createElement("canvas");
          out.width = s.renderer.domElement.width;
          out.height = s.renderer.domElement.height;
          const ctx = out.getContext("2d")!;
          ctx.drawImage(v, 0, 0, out.width, out.height);
          s.renderNow();
          ctx.drawImage(s.renderer.domElement, 0, 0);
          return out.toDataURL("image/png");
        },
        duration: () => s.duration,
        colour: () => s.colourFit,
        phase: () => phaseRef.current,
      };
    }
    return () => {
      live = false;
      observer.disconnect();
      s.dispose();
      scene.current = null;
    };
    // The scene is built once per manifest.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest]);

  // Watch the frames as they are shown; stop exactly on the frame the staging was made from.
  useEffect(() => {
    const v = video.current;
    if (!manifest || !v) return;
    const hero = manifest.hero;
    const early = 0.5 / manifest.video.fps;
    let handle = 0;
    let shown = 0;
    const onFrame = (_: number, frame: VideoFrameCallbackMetadata) => {
      if (armed.current && phaseRef.current === "walking" && frame.mediaTime >= hero.pts - early) arrive();
      if (Math.abs(frame.mediaTime - shown) >= 0.1) {
        shown = frame.mediaTime;
        setTime(frame.mediaTime);
      }
      handle = v.requestVideoFrameCallback(onFrame);
    };
    handle = v.requestVideoFrameCallback(onFrame);
    return () => v.cancelVideoFrameCallback(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest]);

  function holdHero(): Promise<void> {
    const v = video.current;
    const m = meta.current;
    if (!v || !m) return Promise.resolve();
    armed.current = false;
    v.pause();
    go("arriving");
    const matched = () => {
      // First stop on the hero frame: match the pieces to how this browser shows the HDR clip.
      const s = scene.current;
      if (!s || s.colourFit) return Promise.resolve();
      const img = new Image();
      img.src = m.hero.plate;
      return img.decode().then(() => s.matchVideo(v, img), () => undefined);
    };
    return new Promise<void>((resolve) => {
      if (Math.abs(v.currentTime - m.hero.seek) < 1e-3) return resolve();
      v.addEventListener("seeked", () => resolve(), { once: true });
      v.currentTime = m.hero.seek;
    }).then(matched);
  }

  function arrive() {
    void holdHero().then(() => {
      clearTimeout(timer.current);
      timer.current = window.setTimeout(furnish, ARRIVE_BEAT_MS);
    });
  }

  async function furnish() {
    const s = scene.current;
    if (!s || !AT_ROOM.includes(phaseRef.current)) return;
    s.showLanded();
    go("furnished");
  }

  async function togglePlay() {
    const v = video.current;
    const s = scene.current;
    if (!v || !s || busy.current) return;
    const p = phaseRef.current;
    if (p === "walking") {
      v.pause();
      go("paused");
      return;
    }
    busy.current = true;
    clearTimeout(timer.current);
    if (AT_ROOM.includes(p)) s.clear();
    if (p === "ended") {
      armed.current = true;
      v.currentTime = 0;
    }
    v.playbackRate = WALK_RATE;
    go("walking");
    await v.play().catch(() => go("paused"));
    busy.current = false;
  }

  async function chooseFurniture() {
    const s = scene.current;
    if (!s || busy.current) return;
    busy.current = true;
    clearTimeout(timer.current);
    if (AT_ROOM.includes(phaseRef.current)) {
      go("arriving");
    } else await holdHero();
    busy.current = false;
    await furnish();
  }

  async function chooseStyle(id: string) {
    const s = scene.current;
    const style = meta.current?.styles.find((st) => st.id === id);
    if (!s || !style?.available || id === styleId || busy.current) return;
    busy.current = true;
    setStyleId(id);
    const there = AT_ROOM.includes(phaseRef.current);
    await s.setStyle(style);
    busy.current = false;
    if (there) await furnish();
  }

  const style = manifest?.styles.find((st) => st.id === styleId);
  const placeholder = style?.pieces?.find((piece) => piece.concept === "sofa")?.box;
  const status: Record<Phase, string> = {
    loading: "Loading the walkthrough",
    missing: "",
    ready: "Ready",
    walking: `Walking in · ${stamp(time)} · half speed`,
    paused: `Paused · ${stamp(time)}`,
    arriving: "Living room",
    furnishing: `Furnishing · ${style?.label ?? ""}`,
    furnished: `${style?.label ?? ""} · AI-staged`,
    ended: "End of the walkthrough",
  };
  const playing = phase === "walking";

  return (
    <div className="fixed inset-0 flex flex-col bg-night text-ivory">
      <header className="page-x hud-pt relative z-40 flex min-h-28 flex-col items-start gap-1 pb-3 pr-20! sm:pr-24!">
        <Wordmark />
        <p className="eyebrow flex items-center gap-2.5 text-ivory/80!">
          <span className="ice-dot" />
          {isGeneral ? (manifest?.label ?? HEADER) : HEADER}
        </p>
        {/* Over the page, not in its flow: opening the menu never resizes the video. */}
        <div className="hud-top hud-right absolute">
          <HoverNav />
        </div>
      </header>

      <main className="page-x flex min-h-0 flex-1 items-center justify-center py-4" style={{ containerType: "size" }}>
        <div
          ref={stage}
          className="relative overflow-hidden rounded-2xl bg-smoke"
          style={{ width: "min(100cqw, calc(100cqh * 16 / 9))", aspectRatio: "16 / 9" }}
        >
          {manifest && (
            <>
              <video
                ref={video}
                src={manifest.video.src}
                muted
                playsInline
                preload="auto"
                disablePictureInPicture
                aria-label="Proof-of-concept walkthrough, an empty apartment as filmed"
                // The clip is HDR; held to standard range it is shown the way the canvas reads it.
                className="absolute inset-0 h-full w-full object-fill [dynamic-range-limit:standard]"
                onEnded={() => go("ended")}
              />
              <canvas ref={canvas} aria-hidden className={`pointer-events-none absolute inset-0 h-full w-full ${phase === "furnished" && style?.image ? "invisible" : ""}`} />
              {phase === "furnished" && style?.image && <img src={`/api/media/${style.image}`} alt="AI-staged room" className="pointer-events-none absolute inset-0 h-full w-full object-fill" />}
              {playing && !armed.current && placeholder && time <= manifest.hero.pts + 3 && (
                <div aria-label="Furniture placeholder, not motion tracked" className="pointer-events-none absolute grid place-items-center rounded-md border border-ice/70 bg-ice/25 text-center text-xs text-ivory"
                  style={{ left: `${placeholder[0] * 100}%`, top: `${placeholder[1] * 100}%`, width: `${(placeholder[2] - placeholder[0]) * 100}%`, height: `${(placeholder[3] - placeholder[1]) * 100}%` }}>Furniture placeholder</div>
              )}
            </>
          )}
          {phase === "missing" && (
            <div className="absolute inset-0 grid place-items-center p-8 text-center">
              <div className="max-w-md">
                <p className="font-serif text-xl text-ivory/90">The prototype assets are not built on this computer.</p>
                <p className="mt-4 text-sm leading-relaxed text-ash">
                  {isGeneral ? (
                    <>
                      Build this listing&apos;s cascade with{" "}
                      <span className="font-mono text-ivory/80">python -m prototype.general</span> (listing id, its
                      uploaded clip, and per-video calibration lines), then reload.
                    </>
                  ) : (
                    <>
                      Put the proof-of-concept clip at meta-hackathon/poc-luxury-empty-apartment.mp4, then run{" "}
                      <span className="font-mono text-ivory/80">make prototype</span>.
                    </>
                  )}
                </p>
              </div>
            </div>
          )}
        </div>
      </main>

      <footer className="page-x flex flex-wrap items-center gap-x-6 gap-y-3 pb-[calc(1.25rem+env(safe-area-inset-bottom))]">
        <div className="flex items-center gap-2">
          <button type="button" onClick={togglePlay} disabled={!manifest || phase === "loading"} className="btn-glass min-w-28">
            <PlayIcon playing={playing} />
            {playing ? "Pause" : "Play"}
          </button>
          <button type="button" onClick={chooseFurniture} disabled={!manifest || !style?.available || phase === "loading"} className="btn-glass">
            Choose furniture
          </button>
        </div>

        {manifest && (
          <div className="relative max-w-full transition-opacity duration-700 [@media(hover:hover)]:opacity-20 [@media(hover:hover)]:hover:opacity-100 focus-within:opacity-100">
            <div role="group" aria-label="Style" className="flex max-w-full items-center gap-1 overflow-x-auto rounded-full bg-ivory/[0.04] p-1 ring-1 ring-ivory/10">
              {manifest.styles.map((st) => {
                const active = st.id === styleId;
                const off = `${st.label} is off. ${st.reason ?? ""}`;
                return (
                  <button
                    key={st.id}
                    type="button"
                    aria-pressed={active}
                    aria-disabled={!st.available}
                    aria-label={st.available ? st.label : off}
                    onClick={() => void chooseStyle(st.id)}
                    onMouseEnter={() => !st.available && setNote(off)}
                    onMouseLeave={() => setNote(null)}
                    onFocus={() => !st.available && setNote(off)}
                    onBlur={() => setNote(null)}
                    className={`shrink-0 rounded-full px-4 py-1.5 text-data tracking-wide transition pointer-coarse:min-h-11 ${
                      active ? "bg-ivory/[0.1] text-ivory" : st.available ? "text-ivory/70 hover:text-ivory" : "cursor-not-allowed text-ash"
                    }`}
                  >
                    {st.label}
                    {!st.available && <span className="ml-1.5 font-mono text-micro uppercase tracking-[0.15em] text-ash">off</span>}
                  </button>
                );
              })}
            </div>
            {/* PT-02: the full reason is an overlay tooltip, never in flow. In-flow
                text wrapped to several lines, grew the footer, shrank the stage
                (flex-1 + container query) and moved the button under the cursor:
                hover -> resize -> mouseleave -> resize, i.e. the glitch. The
                native title tooltip duplicated it and is gone. */}
            {note && (
              <p role="tooltip" className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-80 max-w-[80vw] -translate-x-1/2 rounded-xl bg-night/95 px-4 py-3 font-mono text-caption leading-relaxed text-ivory/85 ring-1 ring-ivory/15">
                {note}
              </p>
            )}
          </div>
        )}

        <p role="status" aria-live="polite" className="min-w-0 flex-1 font-mono text-caption leading-relaxed text-ivory/70">
          {status[phase]}
        </p>

        <p className="eyebrow text-ivory/70!">{isGeneral ? (manifest?.label ?? FOOTER) : FOOTER}</p>

        {manifest && manifest.styles.some((st) => !st.available) && (
          <p className="basis-full font-mono text-micro leading-relaxed text-ash">
            {manifest.styles
              .filter((st) => !st.available)
              .map((st) => `${st.label} is off: ${st.reason_short ?? st.reason}`)
              .join(" · ")}
            . Hover a style for the full reason.
          </p>
        )}
      </footer>
    </div>
  );
}
