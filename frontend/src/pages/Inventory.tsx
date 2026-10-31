import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, media, type ListingSummary } from "../api";
import StatusMark from "../components/StatusMark";

function Row({ item }: { item: ListingSummary }) {
  return (
    <li>
      <Link
        to={`/listings/${item.id}`}
        className="group -mx-5 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-6 rounded-2xl px-5 py-6 transition hover:bg-ivory/[0.03]"
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
            <span className="eyebrow">{item.city || "City not set"}</span>
            <StatusMark status={item.status} />
          </div>
          <h3 className="mt-2 truncate font-serif text-3xl text-ivory/85 transition group-hover:text-ivory">
            {item.title || "Untitled residence"}
          </h3>
          {item.note && <p className="mt-1 text-sm text-ash">{item.note}</p>}
        </div>
        <div className="flex items-center gap-6">
          {item.price_display && <span className="font-mono text-sm text-champagne">{item.price_display}</span>}
          {item.cover && <img src={media(item.cover)} alt="" className="hidden h-20 w-36 rounded-xl object-cover sm:block" />}
        </div>
      </Link>
    </li>
  );
}

function Group({ title, items, empty }: { title: string; items: ListingSummary[]; empty?: string }) {
  if (!items.length && !empty) return null;
  return (
    <section className="mt-20">
      <h2 className="eyebrow">{title}</h2>
      {items.length ? (
        <ul className="mt-4">
          {items.map((item) => (
            <Row key={item.id} item={item} />
          ))}
        </ul>
      ) : (
        <p className="mt-6 text-ash">{empty}</p>
      )}
    </section>
  );
}

export default function Inventory() {
  const [items, setItems] = useState<ListingSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listings().then(setItems).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-8">
        <div>
          <h1 className="text-6xl font-[200] tracking-tight sm:text-8xl">Inventory.</h1>
          <p className="mt-5 max-w-md text-ash">
            Film the walkthrough, review the staged listing, publish when it's right.
          </p>
        </div>
        <Link to="/new" className="btn-primary">
          New walkthrough
        </Link>
      </div>

      {error && (
        <p role="alert" className="mt-16 text-rose">
          {error}
        </p>
      )}
      {items === null && !error && <p className="eyebrow mt-20">Loading inventory</p>}
      {items && (
        <>
          <Group
            title="Walkthroughs"
            items={items.filter((i) => i.source === "upload")}
            empty="No walkthroughs yet. Start with a steady phone video of an empty unit."
          />

        </>
      )}
    </>
  );
}
