import { useEffect, useRef, useState, type FormEvent } from "react";
import type { LiveRoom } from "../../api";
import { playDing, primeAudio } from "./ding";
import { avatarState, isOriginalRequest, matchImageStyle } from "./guideLogic";
import GuideAvatar from "./GuideAvatar";

type Reply = { text: string; emotion: string; actions_taken: string[]; staged_image_url: string | null; room_id: string | null; deposit: { mock_tx: string; simulated: boolean; payment_taken: boolean } | null };
type Props = { listingId: string; room: LiveRoom; rooms: LiveRoom[]; styleId: string; onStyle: (id: string) => void; onRoom: (index: number) => void; avatarOn: boolean; setAvatarOn: (on: boolean) => void; intro: boolean; styleChange: number };

export default function GuidePanel({ listingId, room, rooms, styleId, onStyle, onRoom, avatarOn, setAvatarOn, intro, styleChange }: Props) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<{ role: string; text: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [deposit, setDeposit] = useState<Reply["deposit"]>(null);
  const thread = useRef(crypto.randomUUID());
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
    setOpen(true);
    setHistory(h => [...h, { role: "You", text }]);
    if (isOriginalRequest(text)) {
      onStyle("original");
      setHistory(h => [...h, { role: "Guide", text: "Showing the original, unstaged room." }]);
      animateReply("Showing the original, unstaged room.");
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
      setHistory(h => [...h, { role: "Guide", text: reply.text }]);
      animateReply(reply.text, reply.emotion);
    } catch (error) {
      setHistory(h => [...h, { role: "Guide", text: (error as Error).message }]);
    } finally { setBusy(false); }
  }

  function submit(e: FormEvent) { e.preventDefault(); void send(message); }
  return (
    <section aria-label="Live-In Guide" className="pointer-events-auto absolute bottom-[calc(9rem+env(safe-area-inset-bottom))] right-3 z-20 w-[min(24rem,calc(100vw-1.5rem))] rounded-2xl bg-night/95 text-ivory shadow-xl ring-1 ring-ice/30 backdrop-blur-xl sm:bottom-28 sm:right-6">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex min-h-11 w-full items-center gap-3 px-4 py-1 text-left">{avatarOn && !intro && <GuideAvatar state={avatarState(busy, nodding, speaking)} excited={emotion === "excited"} />}<span className="flex-1">Live-In Guide</span><span aria-hidden>{open ? "−" : "+"}</span></button>
      {open && <div className="space-y-3 px-4 pb-4">
        <button type="button" onClick={() => setAvatarOn(!avatarOn)} className="min-h-11 rounded-lg px-2 text-xs text-ivory/80" aria-pressed={avatarOn}>Avatar: {avatarOn ? "2D" : "off"}</button>
        <div className="max-h-[min(30dvh,15rem)] space-y-2 overflow-y-auto text-sm" aria-live="polite">
          {history.length === 0 && <p>Ask about the residence or choose an action.</p>}
          {history.map((item, index) => <p key={index} className="whitespace-pre-wrap break-words"><strong>{item.role}:</strong> {item.text}</p>)}
          {busy && <p>Guide is thinking…</p>}
          {deposit && <p role="status">Simulated deposit — no payment taken<br />{deposit.mock_tx} · simulated: true · payment_taken: false</p>}
        </div>
        <div className="flex flex-wrap gap-1">{["Show me Coastal", "Show me Cyberpunk", "Next room", "Reserve it"].map(action => <button key={action} type="button" disabled={busy} onClick={() => void send(action)} className="min-h-11 rounded-full bg-ivory/10 px-3 text-xs disabled:opacity-50">{action}</button>)}</div>
        <form onSubmit={submit} className="flex gap-2"><input aria-label="Message the guide" value={message} onChange={e => setMessage(e.target.value)} className="min-h-11 min-w-0 flex-1 rounded-lg bg-ivory/10 px-3 text-sm" placeholder="Ask the guide" /><button disabled={busy || !message.trim()} className="min-h-11 rounded-lg bg-ice/20 px-4 disabled:opacity-50">Send</button></form>
      </div>}
    </section>
  );
}
