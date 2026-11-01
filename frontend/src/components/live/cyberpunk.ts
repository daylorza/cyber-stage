/** The Cyberpunk style sting, played on the click that selects it. Click-gated, so browsers allow it. */
let el: HTMLAudioElement | null = null;

function element(): HTMLAudioElement | null {
  if (el) return el;
  try {
    el = new Audio("/sounds/cyberpunk.mp3");
    el.preload = "auto";
    el.volume = 0.7;
  } catch {
    return null;
  }
  return el;
}

export function playCyberpunk() {
  const a = element();
  if (!a) return;
  try {
    a.currentTime = 0;
    void a.play().catch(() => undefined);
  } catch {
    /* silent when audio is unavailable */
  }
}
