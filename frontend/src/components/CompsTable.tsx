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
          <p className="font-serif text-3xl text-ivory">
            {money(range.low, range.currency)} – {money(range.high, range.currency)}
          </p>
          <p className="mt-1 text-xs text-ash">Suggested range. {range.basis}.</p>
        </div>
      )}

      {comps.items.length === 0 ? (
        <p className="mt-6 text-sm text-ash">No comparable sales are seeded for this city yet.</p>
      ) : (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead>
              <tr className="eyebrow">
                {["Sale", "Area", "Beds", "Baths", "Sq ft", "Price", "Per sq ft", "Sold"].map((h) => (
                  <th key={h} scope="col" className="px-3 pb-3 font-normal first:pl-0">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono text-[13px] tabular-nums text-ivory/80">
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
      )}
    </section>
  );
}
