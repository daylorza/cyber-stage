# Frontend notes

## Verify
- `npm run build` (tsc --noEmit && vite build) must pass.
- Dev: `npm run dev` (Vite on :5173, proxies `/api` to the backend on :8000).

## Design system (src/index.css)
- Colours, type sizes and shadows are `@theme` tokens. Use `text-micro|label|caption|data|ui`, `shadow-glow`, and colour tokens; do not hardcode hex or `text-[11px]`. Add a token if one is missing.
- Inventory's light theme uses `parchment / ink / umber / clay / taupe / sand / linen / bark / verdant`.
- Shared classes: `eyebrow`, `data-label`, `glass`, `field`, `nav-orb`, `nav-tick`, `segmented` + `segment` (state via `aria-pressed`), `disclosure` (for `<summary>`), `btn`, `btn-primary`, `btn-glass`, `btn-ghost`, `btn-enter` + `btn-enter-dot`.
- Layout: page edges use `page-x`; fixed chrome uses `hud-top / hud-left / hud-right / hud-pt` (shared gutter + safe-area insets). Content containers are `mx-auto max-w-7xl page-x`.
- Grids that only gain columns at a breakpoint need `grid-cols-1` at the base, otherwise wide children (tables) overflow on phones.
- Touch: interactive elements need 44px targets. Use `hit-area` for small text buttons, or `pointer-coarse:min-h-11`.
- Text on `night`/`smoke` must stay at `ivory/55` or above, and `ash` at full opacity, to meet AA.

## Live-In on phones
- Under 640px LiveTour renders a title strip (top) and one bottom sheet (`sheet` in LiveTour.tsx): docked `GuidePanel` (`docked` prop), style pills, Reserve + next/continue. The room image is centred in the band between them (`useHeight`). Desktop keeps the floating title card and separate controls.
