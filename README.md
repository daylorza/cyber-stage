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
seed/       hero listings (Miami, Los Angeles, London) and demo comps
```

## Status

Stage 0: upload, job, status polling, broker review, publish, published page.
Comps are seeded demo data and labeled as such; there is no live MLS feed.
