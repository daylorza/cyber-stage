# Cyber Stage

**Staging software for real estate and brokers. A phone walkthrough video in, a staged, broker-approved listing out.**

Cyber Stage is an entry for the Meta Global AI Developer Hackathon, Team Bliss, solo, Indie track.

## What Cyber Stage is

Cyber Stage is staging software, built for real estate agents and brokers. It does not replace the broker, the listing, or the showing. It stages the room the broker already filmed, so a buyer can feel the home before they ever walk in.

A buyer cannot feel an empty room from a phone video. An agent already has the one thing that shows the real room: the phone video they shot on site. Cyber Stage stages that exact room — same walls, same windows, same doors, same camera — writes copy grounded in what the camera actually saw, lets a broker approve and publish it, and lets a buyer walk the staged room in first person and switch styles on the same room.

Right now, Cyber Stage just does staging — one room, done convincingly, end to end. Not a whole virtual world, not a full-house pipeline.

## Initial primer — the initial build

Keep these three generated listings as the initial primer, the initial build:

1. **Miami** — the original hero residence.
2. **Los Angeles** — a second residence, with its own rooms, separated out of the Miami listing.
3. **London** — a third residence, with its own page.

These three are generated / placeholder listings, not real listings, not real client properties. They are the primer that shows what the software does, so a broker can see it working before uploading anything of their own.

Going forward, brokers bring their own videos and their own listings. The primer stays as the starting example. It does not replace a broker's own work, and it must never be presented as a real listing.

## What Cyber Stage DOES

- **Takes a broker's own phone walkthrough video (or photos) + listing facts, and stages it.** This is the core product, and the future direction: your videos, your listings, staged by Cyber Stage.
- **Stages the exact room filmed.** Same walls, same windows, same doors, same camera. Staging changes furniture and decor only — it does not move architecture.
- **Stages in multiple styles on the same room.** Modern Luxury, Coastal, Minimal — the same room dressed different ways, so a buyer can see options without a reshoot.
- **Writes listing copy grounded in evidence.** Spark writes copy only from Wonder's visual observations + supplied facts. No invented features, no invented square footage, no invented amenities.
- **Checks its own work independently.** A separate checker, with its own model calls, re-checks geometry, doors/windows, and furniture presence before publish. Results are recorded, even when they do not block (see Disclaimer).
- **Puts a broker in control.** A broker reviews, edits, approves, unpublishes, and publishes. Nothing publishes without broker approval. Title and copy edits on a published listing trigger unpublish, so a changed listing is not left live as if it were still approved.
- **Lets a buyer enter the residence.** First-person staged walk, style picker, and a simulated hold — no payment taken.
- **Shows a separate concept style, Cyberpunk - 2142.** The same room reimagined 120 years in the future: retractable translucent laser-gate doors with no doorknobs (door frames still visible), a levitating halo climate ring instead of a ceiling fan, exactly one flying car in the skyline view, and a 2142 skyline outside the same window frames. Clearly labeled as a concept, not as a broker-verified staged photo.
- **Blurs what should not be shown.** Faces and personal items are blurred into publishable frames. Raw frames are never served. Published walkthrough audio is removed.

## What Cyber Stage does NOT do

- **It does not create real listings, and it does not replace a broker.** The primer listings (Miami, Los Angeles, London) are generated examples. A real listing comes from a broker, with a broker's own video and facts.
- **It does not use live MLS data.** Comps are seeded demo data, labeled as demo. There is no live MLS feed, no live pricing feed, and no live availability.
- **It does not sell a room that does not exist.** If staging moves a wall, window, or door, the checker records it. Cyberpunk - 2142 is the only style allowed to reimagine the room, and only as a labeled concept.
- **It does not do whole-home generation.** One room, done well, is the scope. A full-house pipeline, a Blender rebuild, and deeper broker-console features are out of scope for this submission.
- **It does not take payment.** The hold/reserve action is simulated. No payment is taken, no deposit is taken.
- **It does not use non-Meta AI models at runtime.** Every model called at runtime is a Meta model. Non-model tools — React, Vite, Tailwind, FastAPI, ffmpeg, Pillow, Three.js — are scaffolding, not models.
- **It does not show a style with nothing to show.** A style with no detected sofa/table to stage cannot be shown as staged. Missing furniture disables a style; a failed glass check does not (see Disclaimer).
- **It does not present an inconclusive check as a pass.** Where a check did not pass, the recorded result stands. It is not rewritten as a pass, even when it does not block the demo.

## Demo — 3 minutes

1. **0:00–0:15 — Problem + raw phone footage.** An empty room on a phone video.
2. **0:15–0:50 — Generated listing + before/after.** The same room, staged.
3. **0:50–1:15 — One grounded claim, demo comps, broker approval.** Copy tied to visual evidence, comps labeled demo, broker approves and publishes.
4. **1:15–2:15 — Enter the residence.** First-person staged walk of the room you just saw filmed empty.
5. **2:15–2:40 — Change style, if it works convincingly.** Modern Luxury, Coastal, Minimal — the same room dressed different ways. Plus Cyberpunk - 2142, labeled concept.
6. **2:40–3:00 — Return to the published listing, close.**

Before this week: a phone walkthrough video and listing facts. Built this week: everything you are about to see.

## Meta models used

| Model | What it does in Cyber Stage |
|---|---|
| Muse Wonder 1.0 | Classifies rooms, orders rooms, observes features and condition, independently verifies claims. It does NOT generate images and does NOT segment. |
| Muse Image 1.0 | Stages the room. One generated image per style, geometry-checked, broker-approved before it is shown as staged. |
| Muse Spark 1.3 | Writes listing copy, grounded only in Wonder's visual evidence + supplied facts. |
| SAM 3.1 | Segmentation: cuts furniture pieces, finds doors/windows for the checker, blurs faces and personal items for privacy. |

In the demo, each model is named at the moment it acts: Wonder identifies the room and observations, Image stages it, Spark writes copy from those observations, SAM cuts the pieces and the checker verifies doors/windows.

## Run

Requires `uv`, Node 22+, and `ffmpeg`.

```sh
make install
make backend    # API on http://127.0.0.1:8000
make frontend   # UI on http://localhost:5173 (HTTPS=1 make frontend for https)
make test       # backend tests + frontend typecheck
make serve      # build the UI and serve everything from :8000
make prototype  # local-only assets for /prototype-testing (needs the POC clip; nothing committed)
```

Product AI runs on the Meta Model API. Copy `.env.example` to `.env` and fill in the values; `.env` is git-ignored.

```sh
META_API_KEY=
META_API_BASE_URL=https://api.meta.ai/v1
# Optional model overrides (defaults shown):
# META_SPARK_MODEL=muse-spark-1.3
# META_WONDER_MODEL=muse-wonder-1.0
# META_IMAGE_MODEL=muse-image-1.0
# META_SAM_MODEL=sam-3.1
# Max Meta Model API calls per listing job:
# VRE_META_MAX_CALLS=400
```

## Layout

```
backend/    FastAPI, SQLite jobs table, async pipeline worker
  meta_client.py     every Meta Model API call (Spark, Wonder, Image, SAM 3.1)
  pipeline/          frames, rooms, staging, copy, comps
  verify/            independent checker, with its own model calls
  live.py            Live-In-It preparation: staged styles per lived-in room, aligned images, furniture masks, moments
  cascade.py         furniture masks and alignment for the staged images
frontend/   React + Vite + Tailwind
```

Comps are seeded demo data and labeled as such; there is no live MLS feed.

Stage 1 data is never changed by Live-In-It preparation. Live-In-It only ever writes the listing's `live` data.

## What was built during the event

Repo history starts October 26, 2026, the start of the event. Built during the event: the entire pipeline, checker, broker approval, publish page, Live-In-It, style picker, prototype-testing page, and the Cyberpunk - 2142 concept work.

Pre-existing, before this week: a phone walkthrough video and listing facts. Test and placeholder facts only — no real client data, no real listing facts.

## Limitations, honestly

- One room, done well, is the scope. Whole-home generation, a Blender rebuild, and deeper broker-console features are out of scope for this submission.
- Styles are only shown when there is furniture to show. A style with no detected sofa/table to stage cannot be shown as staged.
- SAM does not reliably segment floor-to-ceiling glass. Glass-wall comparisons can come back inconclusive even when the room itself is preserved — see the disclaimer below.
- The hold/reserve action is simulated. No payment is taken.
- Any audio in a published walkthrough video is removed, and privacy regions are blurred at the frame where they were found.

---

## Disclaimer

**Verification in this demo is loosened on purpose, so it does not halt progress.** Checks still run and their results are recorded, but — in the default demo mode — they do not block attach, show, or publish. In particular:

- A glass-wall comparison that fails or is inconclusive does **not** block a style from being shown. Glass is the least reliable thing for SAM to segment, and a glass result alone should not hide an otherwise preserved room.
- Geometry, structure, and framing checks likewise record their result but do not block demo styles. Only missing furniture itself disables a style, because there is nothing to show.
- A style shown under these loosened checks is **not** presented as independently verified unless every check actually passed. Where a check did not pass, the recorded result stands — it is not rewritten as a pass.
- Cyberpunk - 2142 is a fantasy concept style, not a verified staged photo of the filmed room. Its geometry and structure gates are loosened by design for that style only, and that loosening is recorded in the check reason.
- This is a demo, not a production listing tool. Listings, facts, and comps shown here are test / placeholder / seeded demo data, labeled as such where they appear. There is no live MLS feed, no real payment, and no real client data in this submission.

To run with strict blocking instead, set `VRE_BLOCKING_CHECKS=1` in `.env` — then open checks block Approve/Publish. Default (unset/0) is demo mode: checks still run and flag, but uploads can be approved and published with open flags.
