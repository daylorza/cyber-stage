import { useEffect, useRef, useState, type FormEvent } from "react";
import type { LiveRoom } from "../../api";
import { playDing, primeAudio } from "./ding";
import { avatarState, cleanGuideText, isOriginalRequest, matchImageStyle, mobileActions } from "./guideLogic";
import GuideAvatar from "./GuideAvatar";

type Reply = { text: string; emotion: string; actions_taken: string[]; staged_image_url: string | null; room_id: string | null; evidence: string[]; deposit: { mock_tx: string; simulated: boolean; payment_taken: boolean } | null };
type Props = { listingId: string; room: LiveRoom; rooms: LiveRoom[]; styleId: string; onStyle: (id: string) => void; onRoom: (index: number) => void; avatarOn: boolean; setAvatarOn: (on: boolean) => void; intro: boolean; styleChange: number };

export default function GuidePanel({ listingId, room, rooms, styleId, onStyle, onRoom, avatarOn, setAvatarOn, intro, styleChange }: Props) {
  const [open, setOpen] = useState(false);
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
  return (
    <section aria-label="Live-In Guide" className="pointer-events-auto absolute bottom-[env(safe-area-inset-bottom)] right-3 z-20 w-[min(24rem,calc(100vw-1.5rem))] flex max-h-[calc(40dvh-40px)] flex-col rounded-2xl bg-night/40 text-ivory shadow-xl ring-1 ring-ice/20 backdrop-blur-xl sm:max-h-[calc(70dvh-40px)] sm:bottom-[calc(7rem+20px)] sm:right-6 sm:overflow-hidden">
      {!open && brief && <div role="status" className="absolute bottom-[calc(100%+7rem)] right-0 max-w-full rounded-xl bg-[#080f14]/96 px-3 py-2 text-base leading-relaxed text-[#faf8f1] sm:hidden">{brief}</div>}
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex min-h-11 w-full items-center gap-3 px-4 py-[15px] text-left">{avatarOn && !intro && <GuideAvatar state={avatarState(busy, nodding, speaking)} excited={emotion === "excited"} />}<span className="min-w-0 flex-1">Live-In Guide{!open && brief && <span className="hidden break-words rounded-xl bg-[#080f14]/96 px-3 py-2 text-[#faf8f1] sm:block sm:text-[1.0625rem] sm:leading-relaxed">{brief}</span>}</span><span aria-hidden className="self-start sm:self-auto">{open ? "−" : "+"}</span></button>
      {open && <div className="flex min-h-0 flex-1 flex-col gap-1 px-4 pb-2" onTouchStart={e => { touchY.current = e.touches[0].clientY; }} onTouchEnd={e => { if (e.changedTouches[0].clientY - touchY.current > 70 && (historyRef.current?.scrollTop ?? 0) === 0) setOpen(false); }}>
        <button type="button" onClick={() => setAvatarOn(!avatarOn)} className="min-h-11 rounded-lg px-2 text-xs text-ivory/80" aria-pressed={avatarOn}>Avatar: {avatarOn ? "bubble" : "off"}</button>
        <div ref={historyRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain rounded-xl bg-[#080f14]/80 p-3 text-base leading-[1.5] tracking-normal text-[#faf8f1] sm:text-[1.0625rem]" aria-live="polite" style={{ WebkitOverflowScrolling: "touch" }}>
          {history.length === 0 && <p>Ask about the residence or choose an action.</p>}
          {history.map((item, index) => <p key={index} className="whitespace-pre-wrap break-words"><strong>{item.role}:</strong> {item.text}</p>)}
          {busy && <p>Guide is thinking…</p>}
          {deposit && <p role="status">Simulated deposit — no payment taken. A broker confirms the showing.<br />{deposit.mock_tx} · simulated: true · payment_taken: false</p>}
        </div>
        {evidence.length > 0 && <details className="shrink-0 text-xs"><summary>What the guide used</summary><span>{evidence.join(", ")}</span></details>}
        <div className="flex shrink-0 flex-nowrap gap-1 overflow-x-auto sm:hidden">{mobileActions(styleId, rooms.length, moreActions).map(action => <button key={action} type="button" disabled={busy} onClick={() => { if (action === "More") setMoreActions(true); else { setMoreActions(false); sendAction(action); } }} className="min-h-11 min-w-11 shrink-0 text-xs text-ivory disabled:opacity-50">{action === "Reserve it" ? <span className="flex h-[34px] items-center gap-2 rounded-full bg-ivory/[0.07] px-3 tracking-wide ring-1 ring-ivory/25 backdrop-blur-xl">Reserve<span aria-hidden className="h-3 w-3 rounded-full border border-ivory/70" /></span> : <span className="flex h-[34px] items-center justify-center rounded-full border border-ivory/20 bg-ivory/[0.05] px-3 tracking-wide">{action}</span>}</button>)}</div>
        <div className="my-[5px] hidden flex-nowrap gap-1 sm:flex">{["Price", "Amenities", ...(rooms.length > 1 ? ["Next room"] : []), "Reserve it"].map(action => <button key={action} type="button" disabled={busy} onClick={() => sendAction(action)} className="min-h-11 min-w-0 flex-1 whitespace-nowrap rounded-[2px] border border-ivory/20 bg-ivory/[0.05] px-[9px] text-xs tracking-wide disabled:opacity-50">{action.replace("Show me ", "")}</button>)}</div>
        <form onSubmit={submit} className="flex gap-2"><input aria-label="Message the guide" value={message} onChange={e => setMessage(e.target.value)} className="min-h-11 min-w-0 flex-1 rounded-lg bg-ivory/10 px-3 text-sm" placeholder="Ask the guide" /><button disabled={busy || !message.trim()} className="min-h-11 rounded-lg bg-ice/20 px-4 disabled:opacity-50">Send</button></form>
      </div>}
    </section>
  );
}
