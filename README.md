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

Stage 2 (core, one property: The Ocean Residence, Miami): Live-In-It opens only for a
published listing. `backend/live.py` pre-processes it as a job — every style preset per
room (geometry + window/door checks, one stricter retry), SAM furniture pieces for the
cascade, an AI-emptied plate when the filmed room is furnished, and coffee/sit/view moments.
`/p/:id/live` plays it: cascade room by room, style picker, moments, floor plan inside the
hover nav, and a simulated hold (no payment taken, no provider). Stage 1 data is never changed.
