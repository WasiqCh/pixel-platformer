# AGENTS.md — Pixel Platformer

Localhost web app: FastAPI backend (brain) + React/Vite frontend (display only). All logic lives server-side; UI only shows and asks.

## Run

- Backend (port 8100, from repo root, use `.venv` python): `.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --reload-dir backend --port 8100`
- Frontend (port 3000, proxies `/api` → 8100): `cd frontend; npm run dev`
- Or `start.bat` / `start.sh` (boots both, opens browser). No tests, no CI — verify by running both servers.
- Frontend lint only: `cd frontend; npm run lint` (oxlint). No backend lint/typecheck.

## Structure

- `backend/main.py` — app entry, lifespan runs `setup_databases()`; every router in `backend/api/*.py` mounted under `/api/v1`.
- `backend/core/llm_client.py` — all LLM calls go through `dispatch()` / `dispatch_stream()`. `backend/core/sharding.py`, `ripple.py`, `config.py`, `composer.py`, `vault.py`.
- `backend/api/` — one router file per domain (scripts, characters, beats, …). `backend/models/` — Pydantic schemas for LLM-output validation. `backend/recipes/{job}_vN.txt` — prompt templates. `backend/storage/fs_manager.py` — on-disk layout. `backend/db/` — schema + connections.
- `frontend/src/App.jsx` — screen router via `activeNode` state (no router lib); `frontend/src/screens/S01_*…S18_*.jsx` map to pipeline stages; API via relative `fetch('/api/v1/...')` (Vite proxy in `vite.config.js`).

## Data & DB (gitignored `data/` — never commit)

- `data/settings.json` holds endpoint/models/api_key (user-pasted in Settings screen). Never hardcode keys.
- Two DBs: `data/app.db` (channels, projects, job_log, lessons) + `data/projects/{channel_id}_{project_id}/project.db` (per-project artifacts). Folder name is stable `{channel_id}_{project_id}`; slug is display-only.
- `get_project_db()` auto-runs `init_project_db()` (idempotent heal for old DBs). New columns go via `_ensure_column()` in `backend/db/migrations.py`, not just `CREATE TABLE IF NOT EXISTS`.
- Every connection: WAL + FK pragmas, `row_factory = Row`, always `await db.close()`.

## LLM conventions (do not bypass)

- New job types must be added to `JOB_MAP` (tier/temp/stream) in `llm_client.py` + a `backend/recipes/{job}_v1.txt` file. `load_recipe()` resolves latest version — Prompt Library edits write new versions, never edit in place.
- `dispatch()` does JSON-mode-with-fallback → Pydantic validate → one repair retry → auto-escalate cheap tier to high → logs every call to `job_log`. Keep this chain intact.
- Concurrency: semaphore max 2 + exponential backoff (2s→16s, 3 retries) on 429/timeout. Applies to all LLM calls incl. `sharded_extract`.
- Long scripts: `sharded_extract()` splits at >4000 words / 300 overlap, then merges. Streaming jobs (`script_draft`, `ideation`) use `dispatch_stream()` (SSE), which gates on the semaphore but does not backoff-retry mid-stream.
- `_client()` bypasses `HTTP(S)_PROXY` for local endpoints; keep `trust_env=False`.

## Pipeline rules (locked — see `LOCKED_DECISIONS.md`)

- All 25 phases locked; `DECISIONS.md` holds active implementation notes (e.g. rate limiting); `HOW_IT_WORKS.md` is the plain-language flow. Changing a locked decision needs an explicit unlock — don't redesign silently.
- Invariants: manual-always-valid (every AI output editable/skippable), never overwrite (new versions, revert anytime), free navigation + stale flags (never block/delete downstream).
- Script edits call `flag_downstream_stale()` → sets `stale=1` on characters/environments/world_records/beats (variants hide behind characters). Frontend banner offers re-extract/clear.
- Prompt-text rules: repeat character name every pose line (zero pronouns), compositing/editor notes stay in metadata (never sent to image model), box-position maps in metadata only.
- Image generation defaults to `manual` (disabled); no background generation unless explicitly triggered.
