import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, factLine, media, money, shortDate, type PublishedPage as Page } from "../api";
import BeforeAfter from "../components/BeforeAfter";
import CompsTable from "../components/CompsTable";
import { Wordmark } from "../components/Shell";

export default function PublishedPage() {
  const { id = "" } = useParams();
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.page(id).then(setPage).catch((e: Error) => setError(e.message));
  }, [id]);

  if (!page)
    return (
      <div className="grid min-h-dvh place-items-center px-6">
        {error ? <p className="text-ash">{error}</p> : <p className="eyebrow">Opening residence</p>}
      </div>
    );

  const heroSrc = page.rooms[0]?.after ?? page.rooms[0]?.before;
  const range = page.comps.suggested_range;
  const price =
    page.price_display ?? (range ? `Guide ${money(range.low, range.currency)} – ${money(range.high, range.currency)}` : null);

  return (
    <div>
      <header className="pointer-events-none fixed inset-x-0 top-0 z-40 px-6 py-6 sm:px-10">
        <Wordmark />
      </header>

      <section className="relative min-h-[88dvh] overflow-hidden">
        {heroSrc && <img src={media(heroSrc)} alt="" className="absolute inset-0 h-full w-full object-cover" />}
        <div className="absolute inset-0 bg-gradient-to-t from-night via-night/55 to-night/10" />
        <div className="relative mx-auto flex min-h-[88dvh] max-w-7xl flex-col justify-end px-6 pb-16 sm:px-10">
          <p className="eyebrow text-ivory/70!">{page.facts.city}</p>
          <h1 className="mt-4 max-w-4xl font-serif text-5xl leading-[1.04] sm:text-7xl">{page.title}</h1>
          <p className="mt-6 font-mono text-sm text-ivory/80">{factLine(page.facts)}</p>
          <div className="mt-8 flex flex-wrap items-center gap-x-8 gap-y-3">
            {price && <span className="font-mono text-base text-champagne">{price}</span>}
            <span className="eyebrow inline-flex items-center gap-2.5 text-ivory/80!">
              <span className="ice-dot" />
              Broker approved {shortDate(page.approved_at)}
            </span>
            {page.verification?.passed && (
              <span className="eyebrow inline-flex items-center gap-2.5 text-ivory/80!">
                <span className="ice-dot" />
                Independently verified · {page.verification.checks} checks
              </span>
            )}
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-7xl space-y-24 px-6 pb-32 pt-12 sm:px-10">
        <section className="grid gap-12 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div>
            {page.description ? (
              <p className="whitespace-pre-line text-xl font-light leading-relaxed text-ivory/90">{page.description}</p>
            ) : (
              <p className="text-ash">{page.facts.address}</p>
            )}
          </div>
          {page.highlights.length > 0 && (
            <ul className="space-y-3">
              {page.highlights.map((h) => (
                <li key={h.text} className="flex items-center gap-4 text-lg font-light">
                  <span className="h-1 w-1 rounded-full bg-champagne" />
                  {h.text}
                </li>
              ))}
            </ul>
          )}
        </section>

        {page.rooms.length > 0 && (
          <section aria-labelledby="rooms-heading">
            <h2 id="rooms-heading" className="eyebrow">
              Rooms
            </h2>
            <div className="mt-6 grid gap-6 md:grid-cols-2">
              {page.rooms.map((room) => (
                <BeforeAfter key={room.id} room={room} />
              ))}
            </div>
          </section>
        )}

        <CompsTable comps={page.comps} />

        <p className="eyebrow">Published {shortDate(page.published_at)}</p>
      </main>
    </div>
  );
}
