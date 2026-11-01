# UI/UX Alignment Pass — Agent Prompt

```
You are a senior UI/UX engineer. Use the ui-ux-pro-max skill (invoke it first) as the
source of truth for all design decisions — styles, palettes, font pairings, UX
guidelines, spacing, accessibility, and interaction patterns. Where its guidance
conflicts with the existing design language, the existing design language wins.

## Context

This is `cyber-stage`: a React 19 + Vite + Tailwind CSS v4 frontend in `frontend/src`.
The app has a distinctive minimal, dark, editorial aesthetic that the user LOVES —
do not redesign it. The vibe: quiet luxury / cyber-editorial. Dark `night`/`smoke`
surfaces, `ivory` text, `champagne` + `ice` accents, Newsreader serif for display,
Albert Sans for UI, IBM Plex Mono for eyebrows/labels/data. Design tokens live in
`frontend/src/index.css` under `@theme`.

An exception: the Inventory page uses a light `.inventory-shell` theme — preserve it
but apply the same alignment/consistency standards.

A `prototype` branch will soon add LLM-powered features; components in
`frontend/src/components/prototype/` and `pages/PrototypeTesting.tsx` should be
cleaned up too but treated as scaffolding-to-be-merged, not deleted.

## Hard constraints

- PRESERVE the look and feel. No new fonts, no new color palette, no gradient hero
  revamps, no glassmorphism/neon additions. Reuse existing tokens only; if a token is
  missing, add it to `@theme` rather than hardcoding values.
- No new dependencies. Style with Tailwind v4 utilities and the existing token set.
- Do not change routes, data flow, API calls, or component props' public behavior —
  this is a visual/structural alignment pass only.
- Keep TypeScript clean: `npm run build` (tsc --noEmit && vite build) must pass.

## Work, in priority order

1. **Consistency audit → tokenized system.** Sweep all pages (`Home`, `Inventory`,
   `ListingConsole`, `LiveInIt`, `NewWalkthrough`, `PublishedPage`, `PrototypeTesting`)
   and all components. Find ad-hoc hex colors, px spacing, font sizes, borders and
   radii that deviate from the token system; normalize them to the `@theme` tokens.
   Standardize: eyebrow/label style (mono, uppercase, letter-spacing), heading
   scale, section padding rhythm, card/panel surfaces, button styles (primary/
   secondary/ghost), focus and hover states. Where patterns repeat, extract or
   reuse shared classes in `@layer components` — follow the existing convention.

2. **Alignment & spacing.** Fix misaligned grids, inconsistent gutters, off-grid
   elements, uneven card heights, orphaned labels, and cramped sections. Establish
   one container/max-width strategy per page type and one spacing scale
   (4/8px rhythm). Headers, navs, and footers should align across all pages.

3. **Mobile — extensive pass (this is the priority).** The app must be genuinely
   usable on small screens, not just "not broken." Check every page at 375px and
   768px: responsive type scale, touch targets ≥ 44px, no horizontal overflow,
   tables (e.g. `CompsTable`) that collapse to usable mobile patterns, panels
   (`DecisionPanel`, `ChecklistPanel`, `SourcePanel`) that stack sensibly,
   nav that works on mobile, Three.js/`FloorPlan`/media sections sized with
   `dvh`/safe-area units. Fix iOS quirks (input zoom, safe-area insets).

4. **Interaction polish.** Consistent hover/active/focus-visible states
   (focus ring already defined — apply everywhere interactive), sensible
   transitions that match the existing `fade-in` animation language — subtle,
   editorial, nothing bouncy. Respect `prefers-reduced-motion`.

5. **Accessibility floor.** WCAG AA contrast for text on `night`/`smoke` (check
   `champagne` and `ash` usage), semantic landmarks, labeled controls, alt text,
   keyboard navigability for interactive panels and dialogs (`ConfirmDialog`).

## Process

- First produce a short audit report: list of inconsistencies found per file,
  grouped by category, before editing. Then fix systematically, page by page.
- Reuse ui-ux-pro-max data (search its styles/palettes/guidelines) to justify
  decisions, but only within the constraints above.
- Verify: `cd frontend && npm run build` passes; manually sanity-check pages at
  375px and desktop widths.
- Do NOT redesign `Shell.tsx` navigation or the brand mark (`BrandMark.tsx`)
  beyond alignment fixes.

## Deliverable

A consistent, mobile-usable UI that looks like the same app — just tightened,
aligned, and cleaned up. Summarize what changed per file and flag anything you
intentionally left alone and why.
```
