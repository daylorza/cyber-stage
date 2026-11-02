import { money, type Comps } from "../api";

export default function CompsTable({ comps }: { comps: Comps }) {
  const range = comps.suggested_range;
  return (
    <section aria-labelledby="comps-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="comps-heading" className="eyebrow">Comparable sales</h2>
        {comps.source === "demo" && <span className="eyebrow text-ice/80!">Demo data</span>}
      </div>
      <p className="mt-2 text-xs text-ash">{comps.label}</p>

      {range && (
        <div className="mt-6">
          <p className="text-balance font-serif text-2xl text-ivory sm:text-3xl">
            {money(range.low, range.currency)} – {money(range.high, range.currency)}
          </p>
          <p className="mt-1 text-xs text-ash">Suggested range. {range.basis}.</p>
        </div>
      )}

      {comps.items.length === 0 ? (
        <p className="mt-6 text-sm text-ash">No comparable sales are seeded for this city yet.</p>
      ) : (
        <>
          <ul className="mt-6 space-y-2 sm:hidden">
            {comps.items.map((c) => (
              <li key={c.label} className="rounded-xl bg-ivory/[0.025] px-4 py-3.5">
                <div className="flex items-baseline justify-between gap-4">
                  <p className="min-w-0 text-sm text-ivory">
                    {c.label}
                    <span className="block text-xs text-ash">{c.area}</span>
                  </p>
                  <p className="shrink-0 font-mono text-data tabular-nums text-champagne">{money(c.price, c.currency)}</p>
                </div>
                <dl className="mt-3 grid grid-cols-3 gap-x-4 gap-y-2 font-mono text-xs tabular-nums text-ivory/80">
                  {[
                    ["Beds", c.beds],
                    ["Baths", c.baths],
                    ["Sq ft", c.sqft.toLocaleString("en-US")],
                    ["Per sq ft", money(c.price / c.sqft, c.currency)],
                    ["Sold", c.date],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="eyebrow">{label}</dt>
                      <dd className="mt-0.5">{value}</dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ul>
          <div className="mt-6 hidden overflow-x-auto sm:block">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead>
                <tr className="eyebrow">
                  {["Sale", "Area", "Beds", "Baths", "Sq ft", "Price", "Per sq ft", "Sold"].map((h) => (
                    <th key={h} scope="col" className="px-3 pb-3 font-normal">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="font-mono text-data tabular-nums text-ivory/80">
                {comps.items.map((c) => (
                  <tr key={c.label} className="odd:bg-ivory/[0.025]">
                    <td className="rounded-l-lg px-3 py-2.5 font-sans text-ivory">{c.label}</td>
                    <td className="px-3 py-2.5 font-sans">{c.area}</td>
                    <td className="px-3 py-2.5">{c.beds}</td>
                    <td className="px-3 py-2.5">{c.baths}</td>
                    <td className="px-3 py-2.5">{c.sqft.toLocaleString("en-US")}</td>
                    <td className="px-3 py-2.5 text-champagne">{money(c.price, c.currency)}</td>
                    <td className="px-3 py-2.5">{money(c.price / c.sqft, c.currency)}</td>
                    <td className="rounded-r-lg px-3 py-2.5">{c.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
