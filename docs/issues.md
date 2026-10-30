# Issues Tracker

Prototype Testing and related product issues, updated as issues pile up.
Public file — do NOT put private data, real listing facts, API keys,
or Mac-only evidence paths in here. Screenshots / video / textures
stay Mac-only and git-ignored, never committed.

Status: Open | In progress | Fixed | Won't fix (v2)
Priority: P0 = blocks demo, P1 = demo rough edge, P2 = polish / v2

## Open

### PT-05 — Rug still reads a little yellow [P2, Open]
Reported: Oct 29, 2026, Devin report.
Rug colour reads a little yellow vs the staged image.
Fix: colour-match rug closer to staged image, while still
sitting in the filmed room's light.

### PT-06 — Falling pieces are flat cards, not tracked [P2, Open]
Reported: Oct 29, 2026, Devin report.
While falling, each piece is a flat card, so high in the
fall, seen from below, it reads somewhat flat. Lens
distortion is not modelled, furniture does not reflect in
the glossy floor, and furniture is placed for this one
frame only — it is not tracked when the camera moves, so
it lifts away before the clip plays on.
Fix (v2 unless it directly serves visual superiority):
model distortion / reflection, or track pieces to the
camera, or accept the one-frame placement and label it.

### PT-07 — Headless screenshot limit for playing 4K video [P2, Open]
Reported: Oct 29, 2026, Devin report.
Headless Chrome could not screenshot a playing 4K video.
Walking / real-time shots were captured from inside the
page at 1x resolution.
Fix: find a 4K capture route for the demo video, or record
the live page at full resolution for submission.

## Next stage — post-Stage 2 polish + generalisation (NOT Stage 3)
Stage 3 originally = Idea 4 stretch, Nov 1 gate, not started.
This next stage is the main goal now: visual superiority,
cascading from an uploaded video. Devin, Opus 5.5 Extra High,
Oct 29, 21:40 EDT, Muse agrees (details in AGENTS.md).
Next, in order:
1. Rug / shadow fixes PT-01/03/04 — FIXED Oct 30, 2026,
   commit 14092c0, branch next-stage-rug-shadow-hover.
2. Hover glitch PT-02 — FIXED Oct 30, 2026, commit 14092c0.
3. Cascade from uploaded video, not only POC — IN PROGRESS
   Oct 30, 2026: generalised builder + page support landed
   (commit 14092c0, guards tested); end-to-end non-POC run
   NOT verified — hero footage due Oct 29 is still open and
   no clean non-POC clip was available. Do not claim it
   works until a clean clip runs end to end.
4. Submission video capture plan PT-07 — plan DELIVERED
   Oct 30, 2026, docs/submission-video-plan.md, awaiting
   Day's approval; final video is Nov 4 only.
5. P2 PT-05/06 (warmer rug, flat cards, one-frame placement)
   — left until 1–3 done unless blocks demo.
Housekeeping: new work on fresh branch off main (not old
PR #2 branch), this tracker committed on that branch with
the first fix, Day merges. Main is Stage 2 merged, merge
commit d19de00, including Prototype Testing (not Stage 1).
Timeline: freeze Tue Nov 3 evening, submission Wed Nov 4,
9 PM ET. Do NOT start Idea 4 now — it would blow the timeline.

## In progress
- Work 3 generalisation end-to-end verification — blocked on
  clean empty-room footage (hero footage due Oct 29, still
  open Oct 30). Branch next-stage-rug-shadow-hover. Builder
  and guards are in; a non-POC cascade run is not claimed.

## Fixed
- PT-01 — Shadow already on the rug during cascade [P1].
  Fixed Oct 30, 2026, commit 14092c0 (branch
  next-stage-rug-shadow-hover): each piece's footprint on
  the rug (its floor-contact line, end to end) shows plain
  rug weave sampled from the rug's clean front area until
  that piece settles; the only darkening under a falling
  piece is its own dynamic shadow. Check: mid-cascade
  screenshots (Mac-only evidence) — rug falling plain,
  first piece falling with its own shadow, landed frame
  unchanged (cut landed diff 7.46/255, as before).
- PT-02 — Hover glitch on disabled styles [P1]. Fixed
  Oct 30, 2026, commit 14092c0: the full reason is now an
  overlay tooltip, never in flow (in-flow text grew the
  footer, shrank the stage and moved the button under the
  cursor; the native title tooltip duplicated it and is
  gone). Check: hover Coastal OFF / Minimal OFF shows the
  full reason, stage box unchanged (153x80x1294x728 in
  headless Chrome before and after hover), neither style
  enabled, Modern Luxury still works.
- PT-03 — Rug under table / sofa is a filled-in guess [P1].
  Fixed Oct 30, 2026, commit 14092c0, with PT-01: the
  footprint is not revealed until the piece lands.
- PT-04 — Thin grey line on rug where sofa base will land
  [P1]. Fixed Oct 30, 2026, commit 14092c0, with PT-01:
  the footprint band follows the base line itself, so the
  line cannot show before the sofa arrives.

## Won't fix / Version 2
- Broker console enhancements — moved to v2, Oct 29, 2026.
  Broker console is overkill for the demo; main goal is
  visual superiority and cascading from an uploaded video.
- Comps depth, grounded-copy deep dive, publish-flow depth,
  deposit, swipe (Miami → Los Angeles → New York only) —
  all secondary / v2, Oct 29, 2026.
- Sketch-to-finished as a standalone stage — v2, unless it
  directly serves visual superiority in the cascade.

## How to update this tracker
- Add a new issue at the top of Open, with the next PT number,
  date, reporter, page / route, what happens vs what should
  happen, and a fix check (screenshot / log that proves it).
- When work starts, move it to In progress with the branch.
- When fixed, move it to Fixed with the commit hash and date.
- Never add private data, real listing facts, keys, or
  Mac-only file paths. Keep evidence Mac-only, link nothing
  private from this public file.

## Prototype Testing — interim acceptance
Accepted interim Oct 29, 2026, by Day. Very rough, but better
than what we had before. Commit c9eebe5, PR #2 MERGED into
main Oct 29, 2026, merge commit d19de00. Main now includes
Prototype Testing, not Stage 1 only.
