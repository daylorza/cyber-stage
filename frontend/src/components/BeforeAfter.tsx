import { useState } from "react";
import { media, type Room } from "../api";

type View = "before" | "after";

/** Before = the frame as filmed. After = the staged image generated from that same frame. */
export default function BeforeAfter({ room, className = "" }: { room: Room; className?: string }) {
  const [view, setView] = useState<View>(room.after ? "after" : "before");
  const showingAfter = view === "after" && room.after != null;

  const option = (value: View, label: string, disabled = false) => (
    <button
      type="button"
      aria-pressed={view === value}
      disabled={disabled}
      title={disabled ? "Staging pending" : undefined}
      onClick={() => setView(value)}
      className={`rounded-full px-3.5 py-1.5 transition disabled:cursor-not-allowed disabled:opacity-35 ${view === value ? "bg-ivory/90 text-night" : "text-ivory/80 hover:text-ivory"}`}
    >
      {label}
    </button>
  );

  return (
    <figure className={`relative overflow-hidden rounded-2xl bg-smoke ${className}`}>
      <img
        src={media(showingAfter ? room.after! : room.before)}
        alt={`${room.name}, ${showingAfter ? "staged (AI-modified)" : "as filmed"}`}
        className="aspect-video w-full object-cover"
      />
      <div role="group" aria-label="Staging view" className="glass absolute left-4 top-4 flex gap-0.5 rounded-full! p-1 text-xs">
        {option("before", "Before")}
        {option("after", "After", room.after == null)}
      </div>
      <figcaption className="eyebrow absolute bottom-4 right-4 text-ivory/70!">
        {showingAfter ? "AI-modified" : room.after == null ? "Staging pending" : "As filmed"}
      </figcaption>
    </figure>
  );
}
