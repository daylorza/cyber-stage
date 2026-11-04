import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import BrandMark from "./BrandMark";

const LINKS = [
  { to: "/", label: "Home", end: true },
  { to: "/about", label: "About", end: false },
  { to: "/inventory", label: "Inventory", end: false },
  { to: "/inventory?view=broker", label: "Console", end: false },
  { to: "/new", label: "New stage", end: false },
];

export function HoverNav() {
  const [open, setOpen] = useState(false);
  const { pathname, search } = useLocation();
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
        className="nav-orb"
      >
        <span className="ice-dot" />
      </button>
      <div
        className={`flex flex-col items-end transition duration-500 ${open ? "visible translate-y-0 opacity-100" : "invisible -translate-y-1 opacity-0"}`}
      >
        <span aria-hidden className="nav-tick" />
        <ul id="main-menu" className="mt-1 flex flex-col items-end gap-3 rounded-2xl bg-night/30 py-3 pl-5 pr-3 backdrop-blur-md pointer-coarse:gap-0 pointer-coarse:py-1">
          {LINKS.filter((l) => pathname !== "/inventory" || (l.to !== "/new" && l.to !== "/inventory")).map((l) => (
            <li key={l.to}>
              <NavLink
                to={l.to}
                end={l.end}
                className={({ isActive }) => `font-serif text-ui transition hover:text-ivory pointer-coarse:flex pointer-coarse:min-h-11 pointer-coarse:items-center ${(l.label === "Console" ? pathname === "/inventory" && new URLSearchParams(search).get("view") === "broker" : isActive) ? "text-ivory" : "text-ivory/75"}`}
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
    <Link to="/" className="eyebrow pointer-events-auto flex min-h-11 items-center gap-2.5 text-ivory/75! transition hover:text-ivory!">
      <BrandMark />
    </Link>
  );
}

/** Wordmark left, menu right, on the shared gutter. Once the page scrolls, both get a dark backing. */
export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <header data-scrolled={scrolled} className="site-header hud-pt pointer-events-none fixed inset-x-0 top-0 z-40">
      <div className="page-x mx-auto flex max-w-7xl items-start justify-between">
        <Wordmark />
        <HoverNav />
      </div>
    </header>
  );
}

export default function Shell() {
  const { pathname } = useLocation();
  const inventory = pathname === "/inventory";
  return (
    <div className={inventory ? "inventory-shell min-h-dvh" : "min-h-dvh"}>
      <SiteHeader />
      <main className="page-x mx-auto max-w-7xl pb-[calc(10rem+env(safe-area-inset-bottom))] pt-28 sm:pt-32">
        <Outlet />
        {(inventory || pathname === "/about" || pathname === "/new" || pathname.startsWith("/listings/")) && (
          <footer className={`mt-16 flex min-h-[40vh] flex-col justify-between gap-12 border-t py-10 sm:mt-24 sm:flex-row sm:items-end ${inventory ? "border-linen" : "border-ivory/10"}`}>
            <div>
              <Link to="/" className={inventory ? "inventory-eyebrow inline-flex min-h-11 items-center" : "eyebrow inline-flex min-h-11 items-center"}><BrandMark /></Link>
              <p className={`mt-4 max-w-md font-serif text-3xl ${inventory ? "text-umber" : "text-ivory"}`}>Every space has a story.</p>
            </div>
            <nav aria-label="Footer" className={`flex flex-wrap content-start gap-x-8 gap-y-2 text-sm sm:max-w-md sm:justify-end ${inventory ? "text-bark" : "text-ivory/75"}`}>
              <Link to="/" className={`flex min-h-11 items-center ${inventory ? "hover:text-ink" : "hover:text-ivory"}`}>Home</Link>
              <Link to="/about" className={`flex min-h-11 items-center ${inventory ? "hover:text-ink" : "hover:text-ivory"}`}>About</Link>
              <Link to="/inventory" className={`flex min-h-11 items-center ${inventory ? "hover:text-ink" : "hover:text-ivory"}`}>Inventory</Link>
              <a href="https://www.linkedin.com/in/dayanalorza/" className="flex min-h-11 items-center">LinkedIn</a>
              <a href="https://x.com/day__bliss" className="flex min-h-11 items-center">X</a>
              <a href="https://github.com/daylorza/cyber-stage" className="flex min-h-11 items-center">GitHub</a>
            </nav>
          </footer>
        )}
      </main>
    </div>
  );
}
