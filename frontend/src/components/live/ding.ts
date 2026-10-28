/** A short two-tone confirmation, synthesized on the spot. No audio file is shipped or fetched. */
let ctx: AudioContext | null = null;

function context(): AudioContext | null {
  if (ctx) return ctx;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  ctx = new Ctor();
  return ctx;
}

/** Call inside the click handler so the browser lets the sound play after the request returns. */
export function primeAudio() {
  const c = context();
  if (c && c.state === "suspended") void c.resume();
}

const PARTIALS: [number, number][] = [
  [1, 1],
  [2.003, 0.34],
  [3.01, 0.12],
];

function tone(c: AudioContext, out: AudioNode, freq: number, start: number, peak: number, decay: number) {
  for (const [ratio, level] of PARTIALS) {
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = "sine";
    osc.frequency.value = freq * ratio;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.linearRampToValueAtTime(peak * level, start + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + decay / ratio ** 0.35);
    osc.connect(gain).connect(out);
    osc.start(start);
    osc.stop(start + decay + 0.1);
  }
}

export function playDing() {
  const c = context();
  if (!c) return;
  if (c.state === "suspended") void c.resume();
  const master = c.createGain();
  master.gain.value = 0.5;
  const soften = c.createBiquadFilter();
  soften.type = "lowpass";
  soften.frequency.value = 6000;
  master.connect(soften).connect(c.destination);
  const now = c.currentTime + 0.02;
  tone(c, master, 987.77, now, 0.22, 1.1);
  tone(c, master, 1318.51, now + 0.16, 0.26, 1.7);
}
