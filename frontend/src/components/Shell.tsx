import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import BrandMark from "./BrandMark";

const LINKS = [
  { to: "/", label: "Residences", end: true },
  { to: "/inventory", label: "Inventory", end: false },
  { to: "/new", label: "New walkthrough", end: false },
  ...(import.meta.env.DEV ? [{ to: "/prototype-testing", label: "Prototype Testing", end: false }] : []),
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
        className="grid h-11 w-11 place-items-center rounded-full bg-night/20 ring-1 ring-ivory/25 backdrop-blur-md transition hover:ring-ice/60"
      >
        <span className="ice-dot" />
      </button>
      <div
        className={`flex flex-col items-end transition duration-500 ${open ? "visible translate-y-0 opacity-100" : "invisible -translate-y-1 opacity-0"}`}
      >
        <span aria-hidden className="mr-[21.5px] h-8 w-px bg-gradient-to-b from-ivory/45 to-transparent" />
        <ul id="main-menu" className="mt-1 flex flex-col items-end gap-3 rounded-2xl bg-night/30 py-3 pl-5 pr-3 backdrop-blur-md">
          {LINKS.filter((l) => pathname !== "/inventory" || l.to !== "/new").map((l) => (
            <li key={l.to}>
              <NavLink
                to={l.to}
                end={l.end}
                className={({ isActive }) => `font-serif text-[15px] transition hover:text-ivory ${isActive ? "text-ivory" : "text-ivory/75"}`}
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
      <BrandMark />
    </Link>
  );
}

export default function Shell() {
  const inventory = useLocation().pathname === "/inventory";
  return (
    <div className={inventory ? "inventory-shell min-h-dvh" : "min-h-dvh"}>
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
