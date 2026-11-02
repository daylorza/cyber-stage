import { useEffect, useRef, useState, type FormEvent } from "react";
import type { LiveRoom } from "../../api";
import { playDing, primeAudio } from "./ding";
import { avatarState, cleanGuideText, isOriginalRequest, matchImageStyle, mobileActions } from "./guideLogic";
import GuideAvatar from "./GuideAvatar";
import museLogo from "../../assets/muse-logo.svg";

type Reply = { text: string; emotion: string; actions_taken: string[]; staged_image_url: string | null; room_id: string | null; evidence: string[]; deposit: { mock_tx: string; simulated: boolean; payment_taken: boolean } | null };
type Props = { listingId: string; room: LiveRoom; rooms: LiveRoom[]; styleId: string; onStyle: (id: string) => void; onRoom: (index: number) => void; avatarOn: boolean; setAvatarOn: (on: boolean) => void; intro: boolean; styleChange: number; docked?: boolean; onOpenChange?: (open: boolean) => void };

/** Credit line: the guide's replies come from Muse Spark. */
export function PoweredBy({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-micro tracking-wide text-ivory/65 ${className}`}>
      <span className="inline-flex shrink-0 items-center rounded-[4px] bg-white px-1 py-0.5"><img src={museLogo} alt="Muse" className="h-3 w-auto" /></span>
      Powered by Muse Spark 1.3
    </span>
  );
}

export default function GuidePanel({ listingId, room, rooms, styleId, onStyle, onRoom, avatarOn, setAvatarOn, intro, styleChange, docked = false, onOpenChange }: Props) {
  const [open, setOpen] = useState(false);
  useEffect(() => onOpenChange?.(open), [open, onOpenChange]);
  const [moreActions, setMoreActions] = useState(false);
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<{ role: string; text: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [deposit, setDeposit] = useState<Reply["deposit"]>(null);
  const thread = useRef(crypto.randomUUID());
  const historyRef = useRef<HTMLDivElement>(null);
  const touchY = useRef(0);
  const [evidence, setEvidence] = useState<string[]>([]);
  const [brief, setBrief] = useState("");
  useEffect(() => { const el = historyRef.current; if (el) el.scrollTop = el.scrollHeight; }, [history, busy, open]);
  const [emotion, setEmotion] = useState("warm");
  const [speaking, setSpeaking] = useState(false);
  const [nodding, setNodding] = useState(false);
  const speakingTimer = useRef(0);
  useEffect(() => () => clearTimeout(speakingTimer.current), []);
  useEffect(() => {
    if (!styleChange) return;
    setNodding(true);
    const timer = window.setTimeout(() => setNodding(false), 1300);
    return () => clearTimeout(timer);
  }, [styleChange]);
  function animateReply(text: string, nextEmotion = "warm") {
    setEmotion(nextEmotion);
    setSpeaking(true);
    clearTimeout(speakingTimer.current);
    speakingTimer.current = window.setTimeout(() => setSpeaking(false), Math.min(8000, Math.max(800, text.trim().split(/\s+/).length * 300)));
  }

  async function send(text: string) {
    text = text.trim();
    if (!text || busy) return;
    setMessage("");
    setHistory(h => [...h, { role: "You", text }]);
    if (isOriginalRequest(text)) {
      onStyle("original");
      setHistory(h => [...h, { role: "Guide", text: "Showing the original, unstaged room." }]);
      animateReply("Showing the original, unstaged room.");
      setBrief("Original / Unstaged");
      setOpen(false);
      return;
    }
    primeAudio();
    setBusy(true);
    try {
      const response = await fetch(`/api/listings/${encodeURIComponent(listingId)}/guide/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: thread.current, message: text, room_id: room.id, style_id: styleId }),
      });
      if (!response.ok) throw new Error("The guide is temporarily unavailable. Please try again.");
      const reply: Reply = await response.json();
      const destination = reply.room_id ? rooms.findIndex(r => r.id === reply.room_id) : -1;
      const target = destination >= 0 ? rooms[destination] : room;
      const selected = reply.staged_image_url && matchImageStyle(target.styles, reply.staged_image_url);
      if (selected) onStyle(selected);
      if (destination >= 0) onRoom(destination);
      if (reply.deposit?.simulated && reply.deposit.payment_taken === false) { setDeposit(reply.deposit); playDing(); }
      let responseText = cleanGuideText(reply.text);
      if (selected && reply.actions_taken.includes("switch_style")) {
        const label = ({ "modern-luxury": "Modern luxury", coastal: "Coastal", minimal: "Minimal", "2142": "Cyberpunk" } as Record<string, string>)[selected] ?? selected;
        responseText = `Now showing ${label} in the ${target.name.toLowerCase()}.` + (selected === "2142" ? "\nCyberpunk concept · AI-imagined, not a verified depiction of the property." : "");
      }
      setEvidence(reply.evidence ?? []);
      setHistory(h => [...h, { role: "Guide", text: responseText }]);
      animateReply(responseText, reply.emotion);
      if (selected || destination >= 0 || reply.deposit) {
        setBrief(reply.deposit ? "Simulated deposit — no payment taken. Broker confirms." : destination >= 0 ? `Now showing ${target.name}.` : responseText.split("\n")[0]);
        setOpen(false);
      }
    } catch (error) {
      setHistory(h => [...h, { role: "Guide", text: (error as Error).message }]);
    } finally { setBusy(false); }
  }

  function sendAction(action: string) { void send(action === "Price" ? "What is the price?" : action === "Amenities" ? "What amenities are documented for this residence?" : action); }

  function submit(e: FormEvent) { e.preventDefault(); void send(message); }
  const actions = <div className="flex shrink-0 flex-nowrap gap-1 overflow-x-auto sm:hidden">{mobileActions(styleId, rooms.length, moreActions).map(action => <button key={action} type="button" disabled={busy} onClick={() => { if (action === "More") setMoreActions(true); else { setMoreActions(false); sendAction(action); } }} className="min-h-11 min-w-11 shrink-0 text-xs text-ivory disabled:opacity-50">{action === "Reserve it" ? <span className="flex h-9 items-center gap-2 rounded-full bg-ivory/[0.07] px-3 tracking-wide ring-1 ring-ivory/25 backdrop-blur-xl">Reserve<span aria-hidden className="h-3 w-3 rounded-full border border-ivory/70" /></span> : <span className="flex h-9 items-center justify-center rounded-full border border-ivory/20 bg-ivory/[0.05] px-3 tracking-wide">{action}</span>}</button>)}</div>;
  const form = <form onSubmit={submit} className="flex gap-2"><input aria-label="Message the guide" value={message} onChange={e => setMessage(e.target.value)} className="min-h-11 min-w-0 flex-1 rounded-lg bg-ivory/10 px-3 text-base placeholder:text-ash sm:text-sm" placeholder="Ask the guide" /><button disabled={busy || !message.trim()} className="min-h-11 rounded-lg bg-ice/20 px-4 transition hover:bg-ice/30 disabled:opacity-50">Send</button></form>;
  const log = (
    <div ref={historyRef} className={`min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain rounded-xl bg-night/80 p-3 text-base leading-[1.5] tracking-normal text-ivory sm:text-[1.0625rem] ${docked ? "max-h-[45dvh]" : ""}`} aria-live="polite" style={{ WebkitOverflowScrolling: "touch" }}>
      {history.length === 0 && <p>Ask about the residence or choose an action.</p>}
      {history.map((item, index) => <p key={index} className="whitespace-pre-wrap break-words"><strong>{item.role}:</strong> {item.text}</p>)}
      {busy && <p>Guide is thinking…</p>}
      {deposit && <p role="status">Simulated deposit — no payment taken. A broker confirms the showing.<br />{deposit.mock_tx} · simulated: true · payment_taken: false</p>}
    </div>
  );
  const used = evidence.length > 0 && <details className="shrink-0 text-xs text-ivory/80"><summary className="flex min-h-11 cursor-pointer items-center">What the guide used</summary><span>{evidence.join(", ")}</span></details>;

  const chevron = <svg viewBox="0 0 16 16" aria-hidden className={`h-4 w-4 shrink-0 text-ivory/70 transition duration-300 ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" strokeLinejoin="round"><path d="M4 10l4-4 4 4" /></svg>;

  if (docked)
    return (
      <section aria-label="AI Live-In Guide" className="guide-dock pointer-events-auto flex min-h-0 flex-col text-ivory">
        <div className="flex items-center gap-1 pr-2">
          <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex min-h-12 min-w-0 flex-1 items-center gap-3 px-4 py-1.5 text-left">
            {avatarOn && !intro && <GuideAvatar state={avatarState(busy, nodding, speaking)} excited={emotion === "excited"} />}
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5"><span className="text-ui">AI Live-In Guide</span><PoweredBy /></span>
              <span role="status" className="block truncate text-xs text-ivory/65">{brief || (open ? "Ask anything about the residence" : "Tap to ask about price, rooms or amenities")}</span>
            </span>
            {chevron}
          </button>
          {open && <button type="button" onClick={() => setAvatarOn(!avatarOn)} className="btn-ghost shrink-0 px-2 text-xs text-ivory/70" aria-pressed={avatarOn}>Avatar {avatarOn ? "on" : "off"}</button>}
        </div>
        {open && <div className="flex min-h-0 flex-col gap-2 px-4 pb-1" onTouchStart={e => { touchY.current = e.touches[0].clientY; }} onTouchEnd={e => { if (e.changedTouches[0].clientY - touchY.current > 70 && (historyRef.current?.scrollTop ?? 0) === 0) setOpen(false); }}>
          {log}
          {used}
          {actions}
          {form}
        </div>}
      </section>
    );


  return (
    <section aria-label="AI Live-In Guide" className="hud-right pointer-events-auto absolute bottom-10 z-20 flex w-[min(24rem,calc(100vw-3rem))] flex-col items-end gap-3 text-ivory">
      {open && (
        <div className="flex max-h-[calc(100dvh-12rem)] w-full animate-fade-in flex-col gap-3 rounded-3xl bg-night/70 p-4 shadow-xl ring-1 ring-ivory/25 backdrop-blur-xl [animation-duration:0.4s]">
          <div className="flex items-center justify-between gap-3 px-1">
            <div className="min-w-0">
              <p className="eyebrow text-ivory/80!">AI Live-In Guide</p>
              <PoweredBy className="mt-1" />
            </div>
            <button type="button" onClick={() => setAvatarOn(!avatarOn)} className="btn-ghost shrink-0 whitespace-nowrap text-xs text-ivory/70" aria-pressed={avatarOn}>Avatar {avatarOn ? "on" : "off"}</button>
          </div>
          {log}
          {used}
          <div className="flex flex-wrap gap-1.5">{["Price", "Amenities", ...(rooms.length > 1 ? ["Next room"] : []), "Reserve it"].map(action => <button key={action} type="button" disabled={busy} onClick={() => sendAction(action)} className="h-9 rounded-full px-3.5 text-xs tracking-wide text-ivory/85 ring-1 ring-ivory/20 transition hover:bg-ivory/[0.06] hover:text-ivory hover:ring-ivory/40 disabled:opacity-50 [@media(hover:hover)]:hover:shadow-[0_0_18px_-4px_rgb(155_230_239/0.4)]">{action}</button>)}</div>
          {form}
        </div>
      )}
      {!open && brief && <p role="status" className="max-w-full animate-fade-in rounded-2xl bg-night/70 px-4 py-2.5 text-sm leading-relaxed text-ivory ring-1 ring-ivory/15 backdrop-blur-xl">{brief}</p>}
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="btn-enter guide-pill group">
        <span className="btn-enter-dot overflow-hidden">{avatarOn && !intro ? <GuideAvatar state={avatarState(busy, nodding, speaking)} excited={emotion === "excited"} /> : <span className="ice-dot" />}</span>
        <span className="flex flex-col items-start gap-0.5 text-left">
          <span>AI Live-In Guide</span>
          <PoweredBy />
        </span>
        {chevron}
      </button>
    </section>
  );
}
