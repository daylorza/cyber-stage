import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { BRAND } from "../brand";

const LINKS = [
  { to: "/", label: "Residences", end: true },
  { to: "/inventory", label: "Inventory", end: false },
  { to: "/new", label: "New walkthrough", end: false },
  { to: "/prototype-testing", label: "Prototype Testing", end: false },
];

export function HoverNav() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);

  return (
    <nav
      aria-label="Main"
      className="pointer-events-auto flex flex-col items-end"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
    >
      <button
        type="button"
        aria-label="Menu"
        aria-expanded={open}
        aria-controls="main-menu"
        onClick={() => setOpen((o) => !o)}
        className="grid h-10 w-10 place-items-center rounded-full bg-ivory/[0.03] ring-1 ring-ivory/15 backdrop-blur transition hover:ring-ice/50"
      >
        <span className="ice-dot" />
      </button>
      <div
        className={`flex flex-col items-end transition duration-300 ${open ? "visible translate-y-0 opacity-100" : "invisible -translate-y-1 opacity-0"}`}
      >
        <span aria-hidden className="mr-[19.5px] h-7 w-px bg-gradient-to-b from-ivory/30 to-transparent" />
        <ul id="main-menu" className="mt-1 flex flex-col items-end gap-2.5 text-[13px]">
          {LINKS.map((l) => (
            <li key={l.to}>
              <NavLink
                to={l.to}
                end={l.end}
                className={({ isActive }) => `tracking-wide transition hover:text-ivory ${isActive ? "text-ivory" : "text-ash"}`}
              >
                {l.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}

export function Wordmark() {
  return (
    <Link to="/" className="eyebrow pointer-events-auto flex items-center gap-2.5 text-ivory/75! transition hover:text-ivory!">
      <span className="ice-dot" />
      {BRAND}
    </Link>
  );
}

export default function Shell() {
  return (
    <div className="min-h-dvh">
      <header className="pointer-events-none fixed inset-x-0 top-0 z-40 flex items-start justify-between px-6 py-6 sm:px-10">
        <Wordmark />
        <HoverNav />
      </header>
      <main className="mx-auto max-w-7xl px-6 pb-40 pt-28 sm:px-10">
        <Outlet />
      </main>
    </div>
  );
}
