import { useState } from "react";
import { media, type Room } from "../api";

type View = "before" | "after";

export const HELD_BACK = "Held back · privacy pass pending";

/** Before = the frame as filmed. After = the staged image generated from that same frame. */
export default function BeforeAfter({ room, className = "" }: { room: Room; className?: string }) {
  const [view, setView] = useState<View>(room.after ? "after" : "before");
  const showingAfter = view === "after" && room.after != null;
  const src = showingAfter ? room.after : room.before;

  const option = (value: View, label: string, disabled = false) => (
    <button
      type="button"
      aria-pressed={view === value}
      disabled={disabled}
      title={disabled ? (value === "after" ? "Staging pending" : HELD_BACK) : undefined}
      onClick={() => setView(value)}
      className="segment"
    >
      {label}
    </button>
  );

  return (
    <figure className={`relative overflow-hidden rounded-2xl bg-smoke ${className}`}>
      {src ? (
        <img
          src={media(src)}
          alt={`${room.name}, ${showingAfter ? "staged (AI-modified)" : "as filmed"}`}
          className="aspect-video w-full object-cover"
        />
      ) : (
        <div className="grid aspect-video w-full place-items-center">
          <p className="eyebrow">{HELD_BACK}</p>
        </div>
      )}
      <div role="group" aria-label="Staging view" className="glass segmented absolute left-3 top-3 rounded-full! text-xs sm:left-4 sm:top-4">
        {option("before", "Before", room.before == null)}
        {option("after", "After", room.after == null)}
      </div>
      <figcaption className="eyebrow legible absolute bottom-3 right-3 text-ivory/80! sm:bottom-4 sm:right-4">
        {showingAfter ? "AI-modified" : room.before == null ? "Held back" : room.after == null ? "Staging pending" : "As filmed"}
      </figcaption>
    </figure>
  );
}
