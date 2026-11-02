import { useEffect } from "react";
import { Link } from "react-router-dom";
import { BRAND } from "../brand";

const SHOWCASE = "/listings/lst_34d27df2a732#technical";

const LOOP = [
  ["Upload", "A phone walkthrough and the facts you know: beds, baths, size, address, price."],
  ["Read the room", "The best frames are kept, rooms are found, and what is actually in each room is noted."],
  ["Stage", "Each room is staged in the chosen style: furniture and decor only, never walls, windows or doors."],
  ["Write", "Copy is grounded only in what the camera saw and the facts supplied. Every claim is checked before the broker sees it."],
  ["Compare", "Demo comps, labelled demo."],
  ["Approve", "The broker edits, approves and publishes. Nothing publishes without broker approval."],
  ["Live in it", "A buyer steps inside Live-In-It, asks the AI Live-In Guide, switches styles and reserves a showing. Simulated deposit, no payment taken."],
];

const HELPS = [
  ["Brokers", "Skip the busywork and keep the judgment."],
  ["Buyers", "Picture living in the home before visiting."],
  ["Sellers", "Shown staged without moving furniture."],
];

const NOT = [
  "Not live MLS data, and not a valuation. Comps are seeded demo data.",
  "It does not replace the broker.",
  "The deposit is simulated; no payment is taken.",
  "Staged furniture is staged. It isn't included unless the broker's record says so.",
];

export default function About() {
  useEffect(() => {
    document.title = `About · ${BRAND}`;
  }, []);

  return (
    <article className="max-w-5xl">
      <p className="eyebrow">About</p>
      <h1 className="mt-4 text-balance text-[clamp(3rem,10vw,6rem)] font-[200] leading-[0.95] tracking-tight">Cyber Stage</h1>
      <p className="mt-6 max-w-2xl text-balance font-serif text-2xl leading-snug text-ivory/90 sm:text-3xl">
        Staging software for real estate and brokers. A phone walkthrough video in, a staged, broker-approved listing out.
      </p>
      <div className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-5">
        <Link to={SHOWCASE} className="btn btn-halo group px-6 py-3 text-base font-medium">Technical details — for judges <span aria-hidden className="transition group-hover:translate-x-1">→</span></Link>
        <Link to="/inventory" className="btn-ghost text-base text-ivory/80">See the inventory</Link>
      </div>

      <section className="mt-16 grid grid-cols-1 gap-6 border-t border-ivory/10 pt-10 sm:mt-20 md:grid-cols-[12rem_minmax(0,1fr)] md:gap-10">
        <h2 className="eyebrow">The problem</h2>
        <p className="max-w-2xl text-lg font-light leading-relaxed text-ivory/85">
          Empty homes are hard to sell from a phone video. Traditional staging costs time and money, a 3D tour alone still shows an empty room, and a generic AI image can change the room itself (walls, windows, doors), so a broker can't trust it.
        </p>
      </section>

      <section className="mt-12 grid grid-cols-1 gap-6 border-t border-ivory/10 pt-10 md:grid-cols-[12rem_minmax(0,1fr)] md:gap-10">
        <h2 className="eyebrow">How it works</h2>
        <ol className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2">
          {LOOP.map(([name, text], i) => (
            <li key={name} className="flex gap-4">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full font-mono text-micro text-ice ring-1 ring-ice/40">{String(i + 1).padStart(2, "0")}</span>
              <div className="min-w-0 pt-1">
                <p className="text-ivory">{name}</p>
                <p className="mt-1 text-sm leading-relaxed text-ivory/70">{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-12 grid grid-cols-1 gap-6 border-t border-ivory/10 pt-10 md:grid-cols-[12rem_minmax(0,1fr)] md:gap-10">
        <h2 className="eyebrow">Who it helps</h2>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {HELPS.map(([who, how]) => (
            <li key={who} className="glass p-5">
              <p className="font-serif text-xl">{who}</p>
              <p className="mt-2 text-sm leading-relaxed text-ivory/75">{how}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-12 grid grid-cols-1 gap-6 border-t border-ivory/10 pt-10 md:grid-cols-[12rem_minmax(0,1fr)] md:gap-10">
        <h2 className="eyebrow">What it is not</h2>
        <ul className="grid max-w-2xl grid-cols-1 gap-3">
          {NOT.map((n) => (
            <li key={n} className="flex gap-3 text-sm leading-relaxed text-ivory/80">
              <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-rose/80" />
              {n}
            </li>
          ))}
        </ul>
      </section>

      <p className="mt-16 border-t border-ivory/10 pt-8 text-sm text-ash">
        Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4, 2026 · Solo · Indie track · Team Bliss.
      </p>
    </article>
  );
}
