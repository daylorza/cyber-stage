# Submission audit

Audited the public repo `daylorza/virtual-real-estate` at `main`
`d19de0017c3cffbb7f8e5a6b0bfa0175143310e6` (merge of PR #2,
2026-10-29 21:31 EDT). This file is the only change on
`cursor-submission-audit`. Nothing here was merged, and nothing
was pushed to `main`.

The test run below is from a clean checkout of that commit.
The 88 tests use a fake Meta client. They do not prove a live
call to `api.meta.ai`.

## Models called at runtime

Every product model call goes through `backend/meta_client.py`.
The client talks to `https://api.meta.ai/v1`. The four defaults
are the allowed set:

| Role | Default id | Methods |
| --- | --- | --- |
| Copy | `muse-spark-1.3` | `spark_copy` |
| Classify / claim check | `muse-wonder-1.0` | `wonder_classify`, `wonder_verify_claim` |
| Staging | `muse-image-1.0` | `image_stage` |
| Masks | `sam-3.1` | `sam_segment`, `sam_masks` |

No other model id is hardcoded. No embedder. No Kling, Veo,
Runway, Sora, Hunyuan, Tripo, or Meshy call.

Flags, left as flags:

- The four ids can be replaced at runtime with
  `META_SPARK_MODEL`, `META_WONDER_MODEL`, `META_IMAGE_MODEL`,
  and `META_SAM_MODEL`. There is no allowlist. A non-Meta id
  in the environment would be sent. The committed defaults are
  the four Meta ids above. This audit did not change that.
- The HTTP library is the `openai` Python package (`openai==3.35.1`
  in the lock resolution). `MetaClient` constructs `OpenAI(...)`
  with `base_url` set to the Meta API. That is the client
  library, not an OpenAI model. No OpenAI model id is in the
  source.
- `ffmpeg` extracts frames and re-encodes the published
  walkthrough (audio removed). Pillow blurs, compares geometry,
  and cuts cascade pieces. Both are local pixel tools. Neither
  is a video-generation model.
- `meta-sam-parser` is imported only inside `backend/prototype/assets.py`
  to decode SAM mask bits during `make prototype`. It is not in
  `pyproject.toml` dependencies and it is not a model.

## What is in git

19 commits. First is `8f50215` on 2026-10-26 17:26 EDT
("Create README.md"). Last on this branch is `d19de00` on
2026-10-29 21:31 EDT. That span is inside the hackathon
(kickoff Oct 26, 1:00 PM ET). There is no earlier commit.
This history check cannot prove a snippet was not copied in
from somewhere else before the first commit.

Not in git history: `.env`, any video (`.mp4`, `.mov`, `.webm`),
any texture, any private key file. `.env.example` is tracked
and its `META_API_KEY` line is empty. `backend/assets/` and
`frontend/public/prototype/` are gitignored. A redaction test
uses a fake `sk-test-…` string; it is not a live key, and a
search of `docs/` found no key and no email address.

Committed images, which the tracker on the other branch says
should stay off git:

- 3 home heroes: `frontend/public/residences/miami.png`,
  `los-angeles.png`, `new-york.png`. No text baked in. The
  repo does not include a generation receipt next to the files.
- 24 screenshots under `docs/screenshots/` (stage-1, stage-2,
  export-logs).
- `docs/export-logs/sample-export-not-a-real-listing.txt`,
  labeled not a real listing, supplied facts blank.

`docs/screenshots/stage-2/01-published-page-enter-residence.jpg`
shows seed copy for "The Ocean Residence" with the line
"Placeholder facts until hero footage lands. Not a real listing."
The photo is a furnished room. The sentence under it talks
about a wood-paneled ceiling that is not what that photo shows.
Seed rows in `seed/listings.json` and `seed/comps.json` are
labeled placeholder / demo. `seed_new_york` has `baths: null`.

`backend/pyproject.toml` sets `exclude-newer` to
`2026-10-19T00:00:00Z`. That is a package-date cutoff, seven
days before kickoff. It is not application code from before
the event.

`main` is not the latest public work. Branch
`next-stage-rug-shadow-hover` is 4 commits ahead and 0 behind
(`7d4631e`, 2026-10-30 13:45 EDT). Those commits are not on
this branch. This audit did not merge them.

## Tests, typecheck, build

Run on the clean checkout, 2026-10-30.

Backend: `uv sync` then `uv run pytest -q`.
Python 3.14.7, pytest 9.1.1.

```
88 passed in 43.49s
```

0 failed. 0 skipped.

Frontend: `npm ci` (59 packages, 0 vulnerabilities), then
`npm run typecheck` (`tsc --noEmit`, exit 0, no errors), then
`npm run build` (that script runs `tsc --noEmit` again, then
Vite 8.3.4). Build succeeded in 205ms.

Bundle, from the Vite report:

| File | Size | Gzip |
| --- | --- | --- |
| `dist/index.html` | 0.45 kB | 0.29 kB |
| `dist/assets/index-AXndy9FK.css` | 68.43 kB | 11.53 kB |
| `dist/assets/index-LCr0HBn2.js` | 432.49 kB | 132.76 kB |
| `dist/assets/PrototypeTesting-BOEPRyHa.js` | 546.16 kB | 138.86 kB |

Vite warned that `PrototypeTesting-BOEPRyHa.js` is over 500 kB
after minification. Font files are separate `.woff` / `.woff2`
assets (about 5–32 kB each) and are not in the JS totals.

### Three.js

Source: the only `from "three"` import is
`frontend/src/components/prototype/CascadeScene.ts`.
The only importer of that file is
`frontend/src/pages/PrototypeTesting.tsx`.
`frontend/src/main.tsx` loads that page with `lazy()` on the
route `prototype-testing`. Live-In-It (`frontend/src/components/live/stage.ts`)
does not import Three.js.

Build proof, not a browser network capture: `WebGLRenderer`
occurs 0 times in `index-LCr0HBn2.js` and 38 times in
`PrototypeTesting-BOEPRyHa.js`. The index chunk names
`PrototypeTesting-BOEPRyHa.js` as a separate file, so the
Three.js bytes are not in the initial JS bundle. This audit
did not open the app and watch the network panel.

## PT-05 and PT-06

`docs/issues.md` and `docs/submission-video-plan.md` are **not
on this branch** and not on `main`. A GitHub contents check
returns 404 for both files on `main`, `export-logs`,
`stage-1-meta-pipeline`, and `stage-2-live-in-it`. Both files
exist only on the unmerged branch `next-stage-rug-shadow-hover`.
Status below is quoted from that branch's `docs/issues.md`,
not from this checkout.

- **PT-05 — Rug still reads a little yellow.** Priority P2.
  Status **Open**. Reported Oct 29, 2026. The rug colour
  reads a little yellow compared with the staged image.
  The written fix is to colour-match the rug while keeping
  the filmed room's light. Not done.
- **PT-06 — Falling pieces are flat cards, not tracked.**
  Priority P2. Status **Open**. Reported Oct 29, 2026.
  Each falling piece is a flat card, so from below it reads
  flat. Lens distortion is not modelled. Furniture does not
  reflect in the glossy floor. Placement is for one frame
  only, so the pieces are not tracked when the camera moves
  and they lift away before the clip plays on. The written
  fix is marked v2 unless it serves the demo directly.
  Not done.

The same file's "Next stage" list says PT-05 and PT-06 were
left until the rug/shadow, hover, and uploaded-video cascade
items were done. Those three items are marked fixed or
verified on that branch (commits `14092c0` and `7d4631e`).
They are not on `main`.

Also still open there: **PT-07** (P2) — headless Chrome could
not screenshot a playing 4K video. `docs/submission-video-plan.md`
on that branch is a plan only. It says the final video is
recorded Nov 4, after the Nov 3 evening freeze, as a screen
recording of the live page, and that Day still has to approve
the plan.

## Still rough

Said plainly, from `main` plus that unmerged tracker:

- Prototype Testing was accepted on Oct 29 as interim and
  "very rough" (`c9eebe5`, now inside `d19de00`). On `main`,
  PT-01 through PT-04 are not fixed. The fixes sit on the
  unmerged branch.
- PT-05 and PT-06 are still open. Pieces are flat cards on
  one frame. The rug colour is still off. The Work 3 note
  on that branch also says a filmed object can stay visible
  after staging removed it, and a staged floor lamp is not
  a falling piece.
- `/prototype-testing` on a fresh clone has no clip and no
  textures. The page shows "The prototype assets are not
  built on this computer." The clip path it prints is outside
  this repo and is gitignored on purpose.
- Default config does not block publish. `blocking_checks`
  in `backend/config.py` is on only when `VRE_BLOCKING_CHECKS`
  is `1`. Otherwise an open check is a warning
  (`WARNING_RESOLUTION` in `backend/verify/__init__.py`):
  the broker can still approve and publish.
- The committed stage-2 published-page shot puts placeholder
  Miami facts on a furnished photo, and the copy sentence
  does not match that photo.
- There are two cascades. Live-In-It is DOM layout, not
  Three.js. The Three.js drop exists only on
  `/prototype-testing`. The video plan's second-act step
  names Live-In-It and then points at `/prototype-testing`.
- `baths` for the New York seed is null. Home heroes have
  no in-repo proof of how they were made.
