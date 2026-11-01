import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, factLine, media, type ListingSummary } from "../api";
import StatusMark from "../components/StatusMark";

const GridIcon = () => (
  <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.2} aria-hidden>
    <rect x="2.5" y="2.5" width="4.5" height="4.5" /><rect x="9" y="2.5" width="4.5" height="4.5" /><rect x="2.5" y="9" width="4.5" height="4.5" /><rect x="9" y="9" width="4.5" height="4.5" />
  </svg>
);

const ListIcon = () => (
  <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" aria-hidden>
    <path d="M2.5 4h11M2.5 8h11M2.5 12h11" />
  </svg>
);

function ListingCard({ item, broker }: { item: ListingSummary; broker: boolean }) {
  const facts = factLine(item.facts);
  return (
    <li className="inventory-card min-w-0">
      <Link to={!broker && item.status === "published" ? `/p/${item.id}` : `/listings/${item.id}`} className="group block">
        <div className="inventory-image relative overflow-hidden rounded-lg">
          {item.cover ? <img src={media(item.cover)} alt="" className="h-full w-full object-cover transition duration-700 group-hover:scale-[1.03]" /> : <div className="h-full w-full bg-sand" />}
          <span className="inventory-status absolute left-4 top-4 rounded-full px-4 py-2"><StatusMark status={item.status} /></span>
          <span aria-hidden="true" className="legible absolute bottom-4 right-5 text-xl text-ivory opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">↗</span>
        </div>
        <div className="pt-3">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4">
            <h3 className="text-balance font-serif text-2xl leading-tight">{item.title || "Untitled residence"}</h3>
            {item.price_display && <span className="font-mono text-xs text-clay">{item.price_display}</span>}
          </div>
          <p className="mt-1 text-sm text-taupe">{item.city || "City not set"}{facts ? ` · ${facts}` : ""}</p>
          {item.note && !/test upload/i.test(item.note) && <p className="mt-2 text-sm text-taupe">{item.note}</p>}
        </div>
      </Link>
    </li>
  );
}

export default function Inventory() {
  const [params] = useSearchParams();
  const broker = params.get("view") === "broker";
  const [items, setItems] = useState<ListingSummary[] | null>(null);
  const [error, setError] = useState("");
  const [city, setCity] = useState("");
  const [sort, setSort] = useState("recent");
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  useEffect(() => { api.listings().then(setItems).catch((e: Error) => setError(e.message)); }, []);
  const walkthroughs = useMemo(() => (items ?? []).filter((item) => item.source === "upload" && !item.prototype_test), [items]);
  const cities = [...new Set(walkthroughs.map((item) => item.city).filter((value): value is string => !!value))].sort();
  const visible = walkthroughs.filter((item) => !city || item.city === city).sort((a, b) => sort === "name" ? a.title.localeCompare(b.title) : b.updated_at.localeCompare(a.updated_at));
  return (
    <div className="inventory-page">
      <section className="inventory-hero relative">
        <p className="inventory-eyebrow">The collection / Inventory</p>
        <h1 className="inventory-title">Spaces with<br /><span>possibility.</span></h1>
        <p className="inventory-intro">Cinematic walkthroughs of exceptional properties.<br />Review, organize, and publish when it's right.</p>
        <div className="inventory-radar" aria-hidden="true"><span /><i /><b /></div>
        <Link to="/new" className="inventory-new">New walkthrough <span aria-hidden="true">→</span></Link>
      </section>
      <section aria-labelledby="inventory-heading">
        <div className="inventory-toolbar">
          <h2 id="inventory-heading" className="font-serif text-4xl sm:text-5xl">{broker ? "Broker console" : "Inventory"}</h2>
          <div className="inventory-controls">
            <div className="inventory-layout" role="group" aria-label="Layout">
              <button type="button" aria-label="Grid view" aria-pressed={layout === "grid"} onClick={() => setLayout("grid")}><GridIcon /></button>
              <button type="button" aria-label="List view" aria-pressed={layout === "list"} onClick={() => setLayout("list")}><ListIcon /></button>
            </div>
            <label><span className="sr-only">Filter by city</span><select value={city} onChange={(e) => setCity(e.target.value)}><option value="">All cities</option>{cities.map((name) => <option key={name}>{name}</option>)}</select></label>
            <label><span className="sr-only">Sort inventory</span><select value={sort} onChange={(e) => setSort(e.target.value)}><option value="recent">Recent</option><option value="name">Name</option></select></label>
          </div>
        </div>
        {error && <p role="alert" className="py-10 text-rose">{error}</p>}
        {items === null && !error && <p className="inventory-eyebrow py-10">Loading inventory</p>}
        {items && (visible.length ? <ul className={`grid grid-cols-1 gap-x-10 gap-y-10 ${layout === "grid" ? "md:grid-cols-2" : "inventory-list"}`}>{visible.map((item) => <ListingCard key={item.id} item={item} broker={broker} />)}</ul> : <div className="py-16"><p className="font-serif text-3xl">{city ? "No residences in this city." : "Your collection starts here."}</p><p className="mt-3 text-taupe">Start with a phone walkthrough to bring a space to life.</p><Link to="/new" className="mt-6 inline-flex min-h-11 items-center text-umber transition hover:text-ink">New walkthrough →</Link></div>)}
      </section>
    </div>
  );
}
