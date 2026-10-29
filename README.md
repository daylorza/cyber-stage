# virtual-real-estate
# Meta Global Hackathon

Walkthrough to Listing (working name): a phone walkthrough in, a staged, broker-approved listing out.

## Run

Requires `uv`, Node 22+, and `ffmpeg`.

```
make install
make backend    # API on http://127.0.0.1:8000
make frontend   # UI on http://localhost:5173 (HTTPS=1 make frontend for https)
make test       # backend tests + frontend typecheck
make serve      # build the UI and serve everything from :8000
make prototype  # local-only assets for /prototype-testing (needs the POC clip; nothing committed)
```

Product AI runs on the Meta Model API. Copy `.env.example` to `.env` and fill in the values; `.env` is git-ignored.

## Layout

```
backend/    FastAPI, SQLite jobs table, async pipeline worker
  meta_client.py     every Meta Model API call (Spark, Wonder, Image, SAM 3.1)
  pipeline/          frames, rooms, staging, copy, comps
  comps_adapter.py   seeded demo comps behind an adapter interface
frontend/   React + Vite + Tailwind
seed/       hero listings (Miami, Los Angeles, New York) and demo comps
```

## Status

Stage 0: upload, job, status polling, broker review, publish, published page.
Comps are seeded demo data and labeled as such; there is no live MLS feed.

Stage 1: the pipeline calls the Meta Model API via `meta_client.py` — SAM 3.1
privacy/structure masks, face/document blur into publishable frames (raw frames
never served), Wonder room classification, Muse Image staging, Spark copy with
per-claim evidence. A checklist is generated per job and an independent verifier
(`backend/verify/`) re-checks everything with its own model calls; the broker
console must clear every item before approve, and publish re-verifies.

Stage 2 (Live-In-It, Spec v2): the whole video is sampled at 1 fps (no frame cap; a
truncated extraction fails the job), the main living room is the hero room and stages first
(token guard: no main living space, no staging spend), and the published page plays the full
walkthrough video (re-encoded, privacy regions blurred, audio removed). Any published listing
with a main living space can be prepared: `backend/live.py` stages every style preset for the
lived-in rooms (utility rooms are walked past), aligns each generated image to the filmed
frame and cuts a furniture mask (`backend/cascade.py`). `/p/:id/live` walks the video and stops
at each room's hero frame, where the furniture falls from the ceiling; style picker, moments,
drag to look around, floor plan inside the hover nav, and a simulated hold (no payment taken).
Stage 1 data is never changed.
