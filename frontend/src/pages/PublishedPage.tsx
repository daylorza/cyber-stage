import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, clock, factLine, media, money, shortDate, type PublishedPage as Page, type Room } from "../api";
import BeforeAfter from "../components/BeforeAfter";
import CompsTable from "../components/CompsTable";
import { SiteHeader } from "../components/Shell";

/** Enter residence, or why it can't open yet. */
function EnterResidence({ id, page }: { id: string; page: Page }) {
  const live = page.live;
  if (live?.status === "ready")
    return (
      <Link to={`/p/${id}/live`} className="btn-enter group">
        <span className="btn-enter-dot">
          <span className="ice-dot" />
        </span>
        Enter residence
        <span aria-hidden className="transition group-hover:translate-x-1">→</span>
      </Link>
    );
  const reason = !live?.eligible
    ? (live?.reason ?? "Live-In-It isn't available for this listing.")
    : live.status === "preparing"
      ? "The residence is being prepared."
      : "The broker hasn't prepared the residence yet.";
  return (
    <div>
      <span aria-disabled className="btn-enter cursor-not-allowed opacity-45 hover:bg-ivory/[0.08] hover:ring-ivory/25">
        <span className="btn-enter-dot">
          <span className="h-1.5 w-1.5 rounded-full bg-ivory/40" />
        </span>
        Enter residence
      </span>
      <p className="eyebrow mt-3 max-w-xs normal-case tracking-wide text-ivory/60!">{reason}</p>
    </div>
  );
}

/** The walkthrough, played whole and in order: the page itself. */
function Walkthrough({ page, rooms }: { page: Page; rooms: Room[] }) {
  const video = page.video!;
  const ref = useRef<HTMLVideoElement>(null);
  const [now, setNow] = useState(0);
  const portrait = video.height > video.width;
  const current = [...rooms].reverse().find((r) => (r.span?.[0] ?? r.t ?? 0) <= now + 0.25);

  const seek = (t: number) => {
    const el = ref.current;
    if (!el) return;
    el.currentTime = t;
    void el.play().catch(() => undefined);
  };

  return (
    <figure className={portrait ? "mx-auto w-full max-w-[min(26rem,100%)] lg:mx-0" : "w-full"}>
      <video
        ref={ref}
        src={media(video.path)}
        autoPlay
        muted
        playsInline
        controls
        preload="auto"
        onLoadedData={(e) => {
          e.currentTarget.defaultPlaybackRate = 1;
          e.currentTarget.playbackRate = 1;
        }}
        onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)}
        aria-label={`${page.title}: full walkthrough video, ${clock(video.duration)}`}
        className="block max-h-[78dvh] w-full rounded-2xl bg-night object-contain shadow-[0_40px_120px_-40px_rgb(0_0_0/0.9)]"
        style={{ aspectRatio: `${video.width} / ${video.height}` }}
      />
      {rooms.length > 0 && (
        <div className="relative mt-4 h-6" aria-label="Rooms in the walkthrough">
          <div className="absolute inset-x-0 top-1/2 h-px bg-ivory/15" />
          <div className="absolute left-0 top-1/2 h-px bg-ice/60" style={{ width: `${Math.min(100, (now / video.duration) * 100)}%` }} />
          {rooms.map((r) => (
            <button
              key={r.id}
              type="button"
              title={`${r.name} · ${clock(r.t ?? 0)}`}
              aria-label={`Play from ${r.name}, ${clock(r.t ?? 0)}`}
              onClick={() => seek(r.span?.[0] ?? r.t ?? 0)}
              className="absolute top-1/2 grid h-6 w-6 -translate-x-1/2 -translate-y-1/2 place-items-center"
              style={{ left: `${((r.span?.[0] ?? r.t ?? 0) / video.duration) * 100}%` }}
            >
              <span className={`block rounded-full transition ${r.id === current?.id ? "h-2 w-2 bg-ice shadow-glow" : "h-1.5 w-1.5 bg-ivory/50"}`} />
            </button>
          ))}
        </div>
      )}
      <figcaption className="eyebrow mt-2 flex items-center justify-between gap-4 text-ivory/60!">
        <span>Full walkthrough · {clock(video.duration)} · as filmed</span>
        <span>{current?.name ?? ""}</span>
      </figcaption>
      {rooms.length > 0 && (
        <ul className="mt-5 flex flex-wrap gap-x-5 gap-y-2 pointer-coarse:gap-y-0">
          {rooms.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => seek(r.span?.[0] ?? r.t ?? 0)}
                className={`flex items-baseline gap-2 text-sm transition hover:text-ivory pointer-coarse:min-h-11 pointer-coarse:items-center ${r.id === current?.id ? "text-ivory" : "text-ivory/60"}`}
              >
                {r.name}
                <span className="font-mono text-caption text-ash">{clock(r.span?.[0] ?? r.t ?? 0)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}

export default function PublishedPage() {
  const { id = "" } = useParams();
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.page(id).then(setPage).catch((e: Error) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (page) document.title = page.title;
  }, [page]);

  if (!page)
    return (
      <div className="grid min-h-dvh place-items-center px-6">
        {error ? <p className="text-ash">{error}</p> : <p className="eyebrow">Opening residence</p>}
      </div>
    );

  const rooms = page.rooms;
  const range = page.comps.suggested_range;
  const price =
    page.price_display ?? (range ? `Guide ${money(range.low, range.currency)} – ${money(range.high, range.currency)}` : null);
  const timed = rooms.filter((r) => r.t != null).sort((a, b) => (a.t ?? 0) - (b.t ?? 0));
  const backdrop = rooms.find((r) => r.main)?.before ?? rooms[0]?.before;
  const heroSrc = rooms[0]?.after ?? rooms[0]?.before;
  const portrait = page.video ? page.video.height > page.video.width : false;

  const details = (
    <>
      <p className="eyebrow text-ivory/70!">{page.facts.city}</p>
      {page.note && !/test upload/i.test(page.note) && (
        <p className="eyebrow mt-3 inline-flex items-center gap-2.5 rounded-full bg-rose/10 px-3 py-1.5 text-rose! ring-1 ring-rose/30">
          {page.note}
        </p>
      )}
      <h1 className="mt-4 max-w-4xl text-balance font-serif text-4xl leading-[1.04] sm:text-6xl">{page.title}</h1>
      <p className="mt-6 font-mono text-sm text-ivory/80">{factLine(page.facts)}</p>
      <div className="mt-6 flex flex-wrap items-center gap-x-8 gap-y-3">
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
      <div className="mt-10">
        <EnterResidence id={id} page={page} />
      </div>
    </>
  );

  return (
    <div>
      <SiteHeader />

      {page.video ? (
        <section className="relative overflow-hidden">
          {backdrop && (
            <img
              src={media(backdrop)}
              alt=""
              aria-hidden
              className="absolute inset-0 h-full w-full scale-110 object-cover opacity-30 blur-3xl"
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-b from-night/40 via-night/70 to-night" />
          <div
            className={`page-x relative mx-auto grid min-h-dvh max-w-7xl grid-cols-1 items-center gap-12 pb-16 pt-28 sm:pt-32 ${portrait ? "lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:gap-20" : ""}`}
          >
            <Walkthrough page={page} rooms={timed} />
            <div>{details}</div>
          </div>
        </section>
      ) : (
        <section className="relative min-h-[88dvh] overflow-hidden">
          {heroSrc && <img src={media(heroSrc)} alt="" className="absolute inset-0 h-full w-full object-cover" />}
          <div className="absolute inset-0 bg-gradient-to-t from-night via-night/55 to-night/10" />
          <div className="absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-night/55 to-transparent" />
          <div className="page-x relative mx-auto flex min-h-[88dvh] max-w-7xl flex-col justify-end pb-16 pt-28">{details}</div>
        </section>
      )}

      <main className="page-x mx-auto max-w-7xl space-y-16 pb-[calc(8rem+env(safe-area-inset-bottom))] pt-12 sm:space-y-24">
        <section className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div>
            <h2 className="eyebrow mb-5">The residence</h2>
            {page.description ? (
              <p className="whitespace-pre-line text-lg font-light leading-relaxed text-ivory/90 sm:text-xl">{page.description}</p>
            ) : (
              <p className="text-ash">{page.facts.address}</p>
            )}
          </div>
          {page.highlights.length > 0 && (
            <div className="lg:border-l lg:border-ivory/10 lg:pl-12">
            <h2 className="eyebrow mb-5">Highlights</h2>
            <ul className="space-y-3">
              {page.highlights.map((h) => (
                <li key={h.text} className="flex items-center gap-4 text-lg font-light">
                  <span className="h-1 w-1 shrink-0 rounded-full bg-champagne" />
                  {h.text}
                </li>
              ))}
            </ul>
            </div>
          )}
        </section>

        <CompsTable comps={page.comps} />

        {rooms.length > 0 &&
          (page.video ? (
            <details>
              <summary className="eyebrow disclosure w-fit hover:text-ivory!">
                AI-staged stills · {rooms.length} {rooms.length === 1 ? "room" : "rooms"}
              </summary>
              <div className={`mt-6 grid gap-4 ${rooms.length === 1 ? "max-w-4xl" : rooms.length === 2 ? "sm:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-3"}`}>
                {rooms.map((room) => (
                  <BeforeAfter key={room.id} room={room} />
                ))}
              </div>
            </details>
          ) : (
            <section aria-labelledby="rooms-heading">
              <h2 id="rooms-heading" className="eyebrow">
                Rooms
              </h2>
              <div className={`mt-6 grid gap-6 ${rooms.length === 1 ? "max-w-4xl" : "md:grid-cols-2"}`}>
                {rooms.map((room) => (
                  <BeforeAfter key={room.id} room={room} />
                ))}
              </div>
            </section>
          ))}

        <p className="eyebrow">Published {shortDate(page.published_at)}</p>
      </main>
    </div>
  );
}
