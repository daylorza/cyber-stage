# UI direction (PRO-UX)

Where the UI has gone since the original brief in [`ui-pass-prompt.md`](./ui-pass-prompt.md), and the rules to keep following.

## From "alignment pass" to "redesign within the language"

The brief asked for a visual/structural pass only: no layout changes, no new patterns. That proved too strict. The direction now:

- **Keep the language:** dark `night`/`smoke` surfaces, ivory text, champagne and ice accents, Newsreader for display, Albert Sans for UI, IBM Plex Mono for eyebrows and data. Quiet luxury, cyber-editorial. Inventory keeps its light parchment theme.
- **Change layouts when they don't work:** phones get their own layouts (bottom sheets, list rows, sticky filters), not shrunken desktop ones. Desktop uses the width and keeps columns balanced.
- **Every control should look like it belongs to one family:** glass pills of the same height, the same hover glow and the same motion everywhere.

## System (frontend/src/index.css)

- **Tokens:** colors, type scale (`text-micro / label / caption / data / ui`) and `shadow-glow` live in `@theme`. No raw hex or `text-[11px]` in components. Inventory has its own tokens (`parchment, ink, umber, clay, taupe, sand, linen, bark, verdant, brick`).
- **Shared classes:** `btn`, `btn-primary`, `btn-glass`, `btn-ghost`, `btn-enter` + `btn-enter-dot`, `nav-orb`, `segmented`/`segment`, `disclosure`, `data-label`, `field`, `check`, `hit-area`.
- **Gutters:** `page-x` for page edges. `hud-top / hud-left / hud-right / hud-pt` for fixed chrome, with notch and home-indicator insets (`viewport-fit=cover`).
- **The shared header** (`SiteHeader`) aligns to the `max-w-7xl` content column. Once the page scrolls, the wordmark gets a dark pill and the menu orb darkens. It is not a sticky bar.

## Interaction rules

1. **Touch targets** are at least 44px. Use `hit-area` for small text buttons, or `pointer-coarse:min-h-11`.
2. **Inputs** use 16px text on phones, so iOS doesn't zoom in.
3. **Contrast:** text on dark surfaces stays at `ivory/55` or above, and `ash` at full opacity, to meet WCAG AA.
4. **Glow on hover** only on hover-capable devices (`[@media(hover:hover)]`): a soft ice glow on pills, a warm umber glow on Inventory cards.
5. **Motion** is editorial, not bouncy. Easing is `cubic-bezier(0.22, 0.7, 0.12, 1)` or `(0.6, 0, 0.2, 1)`, over 300–700ms, and the global rule honors `prefers-reduced-motion`.
6. **Status** is shown only when it says something. "Published" on every public card is noise.
7. **Grids** that only gain columns at a breakpoint need `grid-cols-1` at the base, otherwise wide children (tables) make phones scroll sideways.

## Page decisions

### Live-In (`/p/:id/live`)
- **Phones:** a title strip at the top with the floor plan on the right. The room image is centered in the space between the strip and one bottom sheet (`useHeight`). The sheet holds the AI Live-In Guide row, the style picker, Reserve, and Next/Continue. While the video walk plays, it holds the timeline, Pause and "Choose furniture".
- **Menu:** only "Leave". Styles, the map and moments live on the page, never twice.
- **Floor plan:** its own card on the right on desktop, labelled "Floor plan · Estimate · not to scale".
- **Style picker** (`StylePicker.tsx`): one component for desktop and phone. A highlight slides to the selected style, and on desktop it is the same height as Finish (52px).
- **AI Live-In Guide:** a glass pill level with Finish, with the chat card opening above it. The credit "Powered by Muse Spark 1.3" uses the official Muse logo (`src/assets/muse-logo.svg`).
- **Reserve (desktop):** no popup. The circle slides to the right end of the pill and uncovers "Hold requested · No payment taken · Ref" behind it.
- **Welcome card:** sits above the style bar with a hairline pointing to it, then flies into the guide pill. Hovering it keeps it open; it leaves when the pointer does.

### Listing console (`/listings/:id`)
- The copy panel stays in view (sticky, scrolling on its own) so the columns stay balanced.
- The action bar aligns to the content edge. On phones it spans the screen bottom, with compact buttons on one row.
- Diagnostics use the `disclosure` summary. Nested glass panels read as insets, not cards inside cards.
- Comparable sales become stacked cards on phones.

### Published listing (`/p/:id`)
- A top scrim under the header, matching section headings ("The residence", "Highlights") with a hairline divider between them, and a single-room still capped at `max-w-4xl`.

### Inventory (`/inventory`)
- **Matches `new-inventory-page.png`:** a brown-ring menu orb with a cream dropdown, a radar labelled Space, Bedrooms, Walkability and Location (shown at 1280px and up), and toolbar dividers.
- **Uniform cards:** one-line title, price on the right, one fact line, and notes as a tag on the photo. The grid is 3 columns at `xl`, with 16:10 photos.
- **Phones:** a compact hero, a sticky city + sort bar under a parchment header band, and photo-left list rows.

### New walkthrough (`/new`)
- **Form:** one list, kept deliberately.
- **Upload area:** filming tips; previews with the first frame, duration and size; a dashed "drop more" area. The box stretches to the form's height.
- **Staging styles:** image cards using the same room in each style (`public/styles/*.jpg`).
- **Sticky summary bar:** file count, city, beds and style next to Process walkthrough, with an upload progress line and inline errors.

## Still open
- The "Opening residence" loader keeps its older light grid look.
- The Home and Published pages have not had a dedicated phone redesign.
- The desktop Live-In menu no longer lists rooms; navigation is Next room, the timeline and swipe.
