import { useEffect, useState } from "react";
import BeforeAfter from "../components/BeforeAfter";
import { HoverNav } from "../components/Shell";
import { api, type Room } from "../api";
import { Link } from "react-router-dom";

export default function LosAngelesListing() {
  const [room, setRoom] = useState<Room | null>(null);
  useEffect(() => { api.page("lst_190d1a7673a8").then((page) => setRoom(page.rooms.find((item) => item.id === "room_2") ?? null)).catch(() => setRoom(null)); }, []);
  return (
    <main className="relative min-h-screen bg-night text-ivory">
      <div className="fixed right-6 top-6 z-40 sm:right-10"><HoverNav /></div>
      <section className="relative min-h-screen overflow-hidden">
      <img src="/residences/los-angeles.png" alt="" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-t from-night via-night/50 to-night/20" />
      <div className="relative flex min-h-screen flex-col justify-between p-8 sm:p-12">
        <Link to="/" className="eyebrow w-fit text-ivory/80!">← Residences</Link>
        <div>
          <p className="eyebrow text-ivory/70!">Los Angeles · Private collection</p>
          <h1 className="mt-3 font-serif text-5xl sm:text-7xl">The Hillside Residence</h1>
          <p className="mt-4 text-sm text-ivory/70">Demo imagery — not a real listing.</p>
          <Link to="/p/lst_190d1a7673a8/live?room=room_2" className="btn-glass mt-8 inline-flex">Enter residence →</Link>
        </div>
      </div>
      </section>
      {room && <section className="mx-auto max-w-7xl px-6 py-16 sm:px-10"><h2 className="eyebrow mb-6">Los Angeles · AI-staged demo</h2><BeforeAfter room={{ ...room, name: "Los Angeles" }} /></section>}
    </main>
  );
}
