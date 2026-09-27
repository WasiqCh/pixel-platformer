# OPERATOR RUNBOOK — driving the Pixel Platformer pipeline (human or agent)

Owner-approved 2026-09-27. You are driving a RUNNING app: backend `:8100`,
frontend `:3000`. Every call below is `http://127.0.0.1:8100/api/v1/...`.
All writes are project-scoped — always use the right `{project_id}`.

## 0. Setup (once per machine)

1. Pull, `start.bat` (backend 8100 + frontend 3000).
2. Open the app → Setup node (🛠️, first in sidebar, auto-opens if red).
   Fix every red item with its Fix button. All green to proceed.
3. Settings → voice provider: **Kokoro** (free) or Gemini (needs key).
   Settings → LLM endpoint/models for planning calls.

## 1. New project

Home → new channel (pick a style preset or write the descriptor) → new project
(pick canvas background or keep channel chroma) → paste/lock script.
Record the `project_id` (e.g. `CH04_EP01`) — every call below needs it.

## 2. Pipeline order (each step's DONE criteria)

| # | Do | DONE when |
|---|---|---|
| 1 | Beat Board → Break beats | beats listed, counts look right |
| 2 | Narrate & Retime | every beat has a WAV + measured duration |
| 3 | ① Plan scenes | every beat has a scene row with shot + reasoning |
| 4 | ② Plan assets | every need is library-hit OR pending gen (counts balance) |
| 5 | ③ Generate SVGs (loop) | every gen `generated` (then Approve → raster PNG → Finalize) |
| 6 | Approve scenes (1-click or batch) | scenes all approved |
| 7 | Check overlays (auto-proposed per scene) | plates read right, ≤1 plate + 1 badge |
| 8 | Checkpoint green → Render | MP4 in My Video, plays + downloads |

Key endpoints (all `POST` unless noted):
- `GET /projects/{id}/scenes/coverage` — thin beats (re-plan those first)
- `POST /projects/{id}/scenes/plan`, `POST .../scenes/assets/plan`
- `POST /projects/{id}/generate/svg/{gen}` (per row), `.../bulk {only,limit}`
- `POST .../generate/svg/{gen}/approve`, `.../finalize`, `.../improve {note}`,
  `.../revert {version}`, `.../paste {code}`
- `PUT /projects/{id}/scenes/{beat} {status:'approved'}`
- `POST /projects/{id}/voiceover/build`, `GET .../voiceover/status`
- `GET /projects/{id}/render/check` (gate: 409-shaped JSON when blocked),
  `POST /projects/{id}/render`, `GET .../render/status`,
  `POST .../render/cancel`
- `GET /projects/{id}/render/finals`, `GET .../render/file/{name}` (download)

## 3. State checks (read-only, use freely)

- `GET .../scenes` → per-beat status/stale. `GET .../scenes/assets` → needs.
- `GET .../generations` → gen queue with statuses.
- `GET .../render/status` → persisted job progress (survives reload).
- Previews: `GET .../scenes/{beat}/preview` (red boxes = named missing assets).

## 4. Errors + recovery

| Symptom | Meaning | Recovery |
|---|---|---|
| 409 on render | gate lists unapproved scenes / missing audio | approve scenes, build voiceover, retry |
| gen `error` with message | that asset failed (LLM/model) | improve-with-note, regen, or paste code |
| calls crawl/timeout | model too heavy or gateway down | smaller model, or wait + resume (never rewinds) |
| cancelled render | cooperative stop | POST render resumes same job at N |
| stale flags after script edit | downstream needs re-review | re-plan flagged items, or mark reviewed |

## 5. Rules (locked)

- Manual always wins: user paste/approve overrides anything.
- Never overwrite: versions only, revert anytime.
- Approved rows are skipped by re-runs (re-plan replaces drafts, keeps approvals).
- Dawood's machine is independent: fresh `data/`, his own settings, same runbook.
