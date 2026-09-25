# SCENES-MP4 — Build Plan & Implementer Handoff

**Read this file first. Implement one ticket at a time: `read plan → implement P1-T01 → report → next`.**
**Status ledger lives in §9 — update it with every report. Nothing is "done" without its acceptance test passing.**

---

## 1. What the product is

Pixel-platformer is a localhost web app (FastAPI backend + React/Vite frontend) that plans
animated YouTube explainer videos. Today it ends at prompt cards + editor handoff: pictures are
made outside, video assembled outside.

**This project adds, inside the app:** per-beat AI scene planning → asset planning → library
reuse on hits → AI-generated SVG for misses (one by one, validated, retried, user-improvable) →
human approve/fix on everything → server-composited previews → final MP4 rendered in-app,
timed by AI narration.

**Locked intent (confirmed with owner, explicit yes — do not re-litigate):**

- Outcome: upload-ready MP4 out of the app — every scene approved, every asset on-model,
  narration in sync.
- User: Wasiq, solo. AI assembles, he approves/fixes — every scene, every asset.
- Why now: quality currently leaks outside the app (external images, external edit).
- Success: one MP4 whose duration equals Σ beat narration audio, every frame traceable to an
  approved scene.
- Constraint: owner's review time. The common path per beat must be ONE click (approve);
  full attention only for unsure/clashing beats.
- Out of scope: no hand-drawing tools (AI makes art, user only judges); no editor-handoff
  upgrades (stays as-is, byproduct only); no motion/tween engine in v1 (stills cut on
  narration boundaries); no voice-provider swap (Gemini TTS stays); no skill-pack export.

---

## 2. Architecture context (what exists — do NOT rebuild)

- Backend entry `backend/main.py`; every router in `backend/api/*.py` mounted under `/api/v1`.
  Frontend `frontend/src/App.jsx` routes via `activeNode` state (no router lib); screens in
  `frontend/src/screens/S##_*.jsx`; API via relative `fetch('/api/v1/...')` (Vite proxies
  `/api` → 8100).
- **Already built — reuse:** per-beat narration WAVs + measured `duration_sec` on `beats`
  (`backend/api/voiceover.py` → `08_export/voiceover/B###.wav`); beat→asset placements
  (`beat_elements`: asset_ref, layer, framing, prompt, editor_note); generation queue +
  `library` + channel vault (`backend/api/generation.py`, kinds `master`/`pose`, default
  provider `manual`); background pattern (`asyncio.create_task` + status endpoint, see
  `generation.py:158`, `voiceover.py:97`); pixel background check at checkpoint (P17).
- **LLM chain — never bypass:** all AI calls go through `backend/core/llm_client.py`
  `dispatch()` (JSON-mode-with-fallback → Pydantic validate → one repair retry →
  auto-escalate cheap tier to high → log every call to `job_log`). SVG code is text: same
  chain, new schema (XML parse + viewBox check). New jobs MUST be added to `JOB_MAP`
  (tier/temp/stream) + a `backend/recipes/{job}_v1.txt` file. `load_recipe()` resolves the
  latest version; Prompt Library edits write new versions, never edit in place.
- **DB:** `data/app.db` (global) + `data/projects/{channel_id}_{project_id}/project.db`
  (per-project; folder stable, slug display-only). `get_project_db()` auto-runs
  `init_project_db()` (idempotent heal). **New columns go via `_ensure_column()` in
  `backend/db/migrations.py`, never just `CREATE TABLE IF NOT EXISTS`.** Every connection:
  WAL + FK pragmas (handled in `connection.py`), `row_factory = Row`, **always
  `await db.close()`**.
- **Invariants (locked):** manual-always-valid (every AI output editable/overridable);
  never overwrite (new versions, revert anytime); free navigation + stale flags (never
  block/delete downstream — except the Phase 3 checkpoint render gate, which blocks render
  only); script edits call `flag_downstream_stale()` (sets `stale=1`; variants hide behind
  characters — do not touch variants directly).
- **Rate limits:** semaphore max 2 + exponential backoff 2s→16s, 3 retries, on all LLM
  calls. Long scripts: `sharded_extract()` (>4000 words / 300 overlap) in
  `backend/core/sharding.py`.

---

## 3. Run & verify (no test suite, no CI — this is how you prove things work)

- Backend (repo root, `.venv` python only): `.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --reload-dir backend --port 8100`
- Frontend: `cd frontend; npm run dev` (port 3000). Or `start.bat` / `start.sh` for both.
- Frontend lint: `cd frontend; npm run lint` (oxlint). No backend lint/typecheck.
- `data/` is gitignored — **never commit it** (API keys + generated content). Never hardcode keys.
- Verify per ticket with: both servers booted, API calls against `/api/v1/...`, and
  direct SQL checks on `project.db`. Paste command + output as evidence in your report (§8).

---

## 4. Implementer rules (violations = ticket rejected)

1. One ticket = one change. Ticket order is dependency order; do not skip ahead.
2. Every ticket has an acceptance test (§5–§7). Quote the evidence (commands + outputs) in
   your report. No acceptance = not done.
3. Additive only: extend tables via `_ensure_column`, extend screens via new buttons/sections.
   No renames, no dropped tables, no deleted screens, no redesign of locked pipeline phases
   (`LOCKED_DECISIONS.md` — all 25 phases locked; changing one needs an explicit owner unlock).
4. Every AI output needs a Pydantic schema with a **non-empty `reasoning` field** (reasoning is
   how the owner reviews 400 beats fast). No prompt text hardcoded in Python — recipes only.
5. New file? Prefer editing existing files. New backend table? Add to `PROJECT_SCHEMA` (fresh
   DBs) AND ensure old DBs heal via the idempotent path.
6. Report after EVERY ticket using the template in §8, and flip its ledger row in §9 to
   ✅ (+ commit hash). If blocked, flip to 🛑 with the blocker — do not silently continue.

---

## 5. PHASE 1 — Scene planning (API + DB + AI, no UI)

Exit gate: P1-T08 passes. No frontend work in this phase.

**P1-T01 — `scenes` table.**
Add to `PROJECT_SCHEMA` (`backend/db/migrations.py`):
`scenes(beat_id TEXT PRIMARY KEY REFERENCES beats(id), place_asset_ref TEXT, shot TEXT,
reasoning TEXT, status TEXT NOT NULL DEFAULT 'draft', stale BOOLEAN NOT NULL DEFAULT 0,
created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`.
(`reasoning` added in P1-T05 — review UI reads it off the row; T02 `_ensure_column` precedent.)
*Acceptance: delete `project.db`, boot, table exists; boot again, no error, data intact.
Evidence: `.schema scenes` output before/after.*

**P1-T02 — Placement columns on `beat_elements`.**
`_ensure_column` ×3 in `init_project_db`: `x REAL`, `y REAL`, `scale REAL` (0–1 fractions,
all nullable). NULL = fall back to existing `framing` text; old projects must behave
byte-identically.
*Acceptance: old DB gains columns on boot; existing rows read NULL; no other change.
Evidence: `PRAGMA table_info(beat_elements)` + one old-row SELECT.*

**P1-T03 — `scene_plan` + `asset_plan` jobs.**
`JOB_MAP`: `scene_plan` {high, 0.5, no-stream}, `asset_plan` {medium, 0.3, no-stream}.
Recipes `backend/recipes/scene_plan_v1.txt`, `asset_plan_v1.txt`. Context packs (follow
P20 precedent): scene_plan ← beat text + neighboring beats + full script + approved-sheet
registry + style descriptor/avoid-list; asset_plan ← scene + library index (IDs + tags only,
never export prefixes).
*Acceptance: both load via `load_recipe()`; unknown-job error path untouched.
Evidence: loader output + one `dispatch()` smoke call logged to `job_log`.*

**P1-T04 — Pydantic schemas.**
New `backend/models/scene.py`: `ScenePlan(place_ref: str|None, shot: str, reasoning: str
non-empty)`, `AssetNeed(name, kind[character|prop|place|photo], search_query, reasoning
non-empty)`. Empty reasoning must FAIL validation.
*Acceptance: malformed output (missing reasoning) fails validation and triggers the
repair-retry path in a live `dispatch()` call. Evidence: job_log row showing retry.*

**P1-T05 — Scene-plan endpoint.**
`POST /projects/{project_id}/scenes/plan` (new file `backend/api/scenes.py`, register router
in `main.py` under `/api/v1`): batch over beats (sharded via `sharded_extract` thresholds
for long scripts), writes `scenes` rows as `draft`. Never overwrites a row with
`status='approved'` (skip it). Manual row write (PUT) always allowed.
*Acceptance: 30 beats plan in one call; every row has non-empty shot + reasoning; re-run
skips approved rows. Evidence: row counts + 2 sample rows.*

**P1-T06 — Asset-plan + library match.**
`POST /projects/{project_id}/scenes/assets/plan`: `asset_plan` per scene → local match vs
`library` + channel vault (name/tag match) → each need ends as EXACTLY ONE of
`library_ref` set / `generate` flag set (never neither, never both). Misses create
`generations` rows with `kind='svg'`, status `pending`, linked to beat + scene.
*Acceptance: on 30 beats, every need resolves to one branch; zero silent drops.
Evidence: counts query (needs = matched + to-generate), 2 sample `generations` rows.*

**P1-T07 — Ripple + stale.**
Extend `flag_downstream_stale()` (`backend/core/ripple.py`) to include `scenes`. Scene edits
do NOT cascade further (scenes are leaves until Phase 3).
*Acceptance: locked-script edit → all scenes `stale=1`, count equals beat count;
mark-reviewed clears; existing banner picks them up with zero frontend change.
Evidence: stale counts before/after.*

**P1-T08 — Phase gate (audit).**
After T05+T06 on a test project: (a) every beat has ≥1 scene job row in `job_log` with
tokens/tier/ok-fail; (b) every `kind='svg'` generation row traces beat → scene → need.
*Acceptance: one SQL query per check, both return zero gaps. Phase 1 is done ONLY when
this passes. Evidence: both queries + outputs.*

Order: T01 → T02 → T04 → T03 → T05 → T06 → T07 → T08. (T03+T04 may pair in one sitting.)

---

## 6. PHASE 2 — SVG generation (the core new loop)

Depends on: Phase 1 gate ✅. Raster spike DONE 2026-09-25 → Inkscape headless
(see `docs/scenes-mp4/DECISION_RASTER.md`). P2-T06 may proceed without waiting for Phase 1.

**P2-T01 — Raster spike (tooling decision, one sitting).**
Candidates in order: `cairosvg` (pip, no binary) → Inkscape headless (probe path at
runtime, honor `INKSCAPE_PATH`, NEVER hard-code — MSIX path is version-pinned) → Chromium
screenshot. Rasterize the same 20 test SVGs (flat fills, thick outlines, text) with each
available tool; compare fidelity + determinism (same input twice → byte-identical PNG).
*Acceptance: written decision in `docs/scenes-mp4/DECISION_RASTER.md` (tool + why +
exact version/command). Everything visual depends on this — no P2-T06 before it.*

**P2-T02 — `generations` accepts `kind='svg'`.**
Extend `backend/api/generation.py`: svg rows carry `svg_path` (new nullable column via
`_ensure_column`), `file_path` holds the rastered PNG once available. Storage:
`06_sheets/svg/<asset>_vN.svg` (versioned, never overwrite).
*Acceptance: insert + list round-trip of an svg row; PNG absent until P2-T06.
Evidence: row SELECT.*

**P2-T03 — `svg_gen` job + recipe + schema.**
`JOB_MAP`: `svg_gen` {high, 0.5, no-stream}. Recipe `backend/recipes/svg_gen_v1.txt`:
global style context (kit descriptor + palette + outline rule: outlines constant in pixels,
1.5–2.0% of head height) + asset description + (retry/improve: previous SVG code + user
fix-note). Schema: raw SVG text; server validation = XML parses + `viewBox`/`width`/`height`
present + no `<script>`/external refs. Repair-retry once, escalate on failure (existing chain).
*Acceptance: valid SVG passes; script-tagged SVG rejected; logged to `job_log`.
Evidence: 3 dispatch trials (good / bad / repair).*

**P2-T04 — Single generation endpoint.**
`POST /projects/{id}/generate/svg/{gen_id}`: dispatch → validate → write versioned
`_vN.svg` → status `generated`. Failure → status `error` + message, retry re-runs (new
version, never overwrite).
*Acceptance: miss → generated file on disk + DB row; forced failure → error status, retry
creates next version. Evidence: files + rows.*

**P2-T05 — Improve endpoint.**
`POST /projects/{id}/generate/svg/{gen_id}/improve {note}`: context = style + asset desc +
PREVIOUS svg code + user note → new version. Old versions kept, revert = point
`file_path`/`svg_path` back (newest pointer only, history intact).
*Acceptance: improve-with-note yields `_v(N+1).svg` differing from `_vN.svg`; revert
restores. Evidence: diff + rows.*

**P2-T06 — Approve → raster PNG (cache by SVG hash).**
Approve action rasterizes via P2-T01 tool into `06_sheets/raster/`; identical hash = cache
hit, no re-raster. Approval UI shows the PNG, never the SVG source (render is the only
feedback that counts). Status: `generated → approved → final` (follow sheets ladder).
*Acceptance: approve 5 SVGs → 5 PNGs; re-approve unchanged = cache hits; PNGs viewable via
existing file endpoint pattern. Evidence: files + hashes.*

**P2-T07 — Phase gate.** Every `kind='svg'` row from Phase 1 either `final` with PNG on
disk or `error` with message; zero rows stuck in `pending`/`generated` unexamined.
*Acceptance: counts query returns zero gaps. Evidence: query + output.*

---

## 7. PHASE 3 — Scene review UI + PHASE 4 — Render MP4

### Phase 3 — Scene review (owner time is the constraint)

**P3-T01 — Server-side scene preview.**
`GET /projects/{id}/scenes/{beat_id}/preview`: Pillow-composite (already a dependency)
place layer + asset PNGs at x/y/scale (NULL → sensible default from `framing`) at
1920×1080 → cache PNG per scene-hash; missing asset = honest labelled box, NEVER silent
blank (locked rule). No new dependency.
*Acceptance: 10 scenes preview; one with a missing asset shows a labelled box.
Evidence: PNGs + hashes.*

**P3-T02 — Beat-board extension (frontend).**
Extend S09 beat cards (follow `App.jsx` activeNode + `fetch('/api/v1/...')` pattern, run
`npm run lint` after): preview image + 3-button row Approve / Fix-note / Regenerate-one-asset.
One click = common path; full card only for unsure/clashing beats. New screen ONLY if this
gets crowded (decide then, not now).
*Acceptance: approve 10 beats, each ≤2 clicks; lint clean. Evidence: lint output + click
count note.*

**P3-T03 — Checkpoint render gate.**
S13 gains ONE blocking gate: render refused while any scene is unapproved or any beat lacks
audio. Everything else stays advisory (never block downstream work — invariant).
*Acceptance: direct API render call on an unapproved project is rejected with a clear
message; approved project passes. Evidence: both calls + responses.*

**P3-T04 — Phase gate.** 30 consecutive beats approved; median ≤2 clicks; every approval
traceable scene → assets (library_ref or final SVG) → job_log.
*Acceptance: click log + trace query with zero gaps.*

### Phase 4 — Render MP4 (voiceover first, visuals second, mux last)

**P4-T01 — `render_jobs` table + endpoints.**
`render_jobs(project_id, status, progress, current_segment, error, output_path, ...)` in
`PROJECT_SCHEMA` + `POST /projects/{id}/render` (reuses `asyncio.create_task` + status
endpoint pattern from `generation.py`/`voiceover.py`; progress persisted so page reload
doesn't blind the user; cooperative cancel between segments; resume from
`current_segment`).
*Acceptance: start → status shows progress → cancel at segment N → resume continues at N,
not 1. Evidence: status outputs.*

**P4-T02 — Frame builder (Pillow, stills v1).**
Per beat: hold approved scene PNG for `round(duration_sec*30)` frames (durations ALREADY
narration-measured on `beats` — do not recompute). No motion engine in v1. Frames live ONLY
in `07_render/frames`-style temp dir (add to project folders if missing).
*Acceptance: 10-beat project yields exactly Σ frames; frame 1 of beat N equals its approved
preview. Evidence: counts + pixel compare.*

**P4-T03 — ffmpeg probe + mux.**
Probe ffmpeg at runtime (PATH search + env override, e.g. `FFMPEG_PATH`); hard failure =
clear error naming what was tried (same discipline as the Inkscape probe). Per-beat
PNG-loop + per-beat WAV (`08_export/voiceover/B###.wav`) → per-segment MP4 → concat to
final. Never hold all frames at once: encode segment → delete frames → next.
*Acceptance: missing ffmpeg → clear error; present → 10-beat MP4 with audio in sync ±1
frame. Evidence: error output + ffprobe duration.*

**P4-T04 — Final output + cleanup.**
Output `08_handoff/<project>_final.mp4` (+ version `_vN` on re-render, never overwrite).
Post-render assert temp frames dir empty.
*Acceptance: file exists and plays; frames dir empty; re-render makes `_v2` with prior
intact. Evidence: listing + sizes.*

**P4-T05 — PROJECT gate (the definition of done).**
Full pass on a real project: script → voiceover → scenes → approved → MP4. Duration equals
Σ beat audio (±1s); every frame traceable to an approved scene; zero gaps in job_log.
*Acceptance: the three checks above, evidenced. THIS is "perfect video".*

### Parked (do NOT build): hand-drawing tools, motion/tween engine, skill-pack export,
voice-provider swap, handoff upgrades, text-overlay timing changes.

---

## 8. Report template (paste this filled after EVERY ticket)

```
Ticket: P_-T__
Commit: <hash>  Files: <paths>
Did: <2 lines max>
Acceptance evidence:
  <command 1 + output>
  <command 2 + output>
Gaps/blockers: <none | description>
Ledger: flipped P_-T__ → ✅/🛑
```

---

## 9. Status ledger (implementer updates this — one row per ticket)

| Ticket | Status | Commit | Notes |
|---|---|---|---|
| P1-T01 | ✅ | 200228f | scenes table in PROJECT_SCHEMA; heals old DBs via init_project_db |
| P1-T02 | ✅ | uncommitted | x/y/scale REAL nullable on beat_elements; PROJECT_SCHEMA + _ensure_column heal |
| P1-T03 | ✅ | uncommitted | scene_plan {high,0.5} + asset_plan {medium,0.3} in JOB_MAP; recipes scene_plan_v1/asset_plan_v1; smoke ok (job_log 107/108) |
| P1-T04 | ✅ | uncommitted | ScenePlan + AssetNeed in backend/models/scene.py; non-empty reasoning enforced, repair-retry proven (job_log id 104) |
| P1-T05 | ✅ | uncommitted | POST /projects/{id}/scenes/plan + PUT manual + GET list (backend/api/scenes.py); reasoning TEXT on scenes (PROJECT_SCHEMA + heal); 30/30 beats planned, re-run skips approved |
| P1-T06 | ✅ | uncommitted | POST /projects/{id}/scenes/assets/plan + GET list (scenes.py); scene_assets table w/ XOR CHECK; AssetPlan wrapper; 30/30 scenes, 107 needs = 14 matched + 93 svg-pending, 0 failed (CH03_EP02; gateway 20128 down so Ollama qwen2.5:7b stood in — see report) |
| P1-T07 | ✅ | uncommitted | flag_downstream_stale() flags scenes 30/30 via beats join; stale counts/clear/total include scenes (banner, zero frontend change); scene edits are leaves, no cascade |
| P1-T08 | ✅ | uncommitted | Phase 1 gate PASS (audit-only, no code change): CH03_EP02 30/30 beats ≥1 qualified scene_plan row (58 rows, 58 ok, temp 0.5=high); 93/93 svg gens trace beat→scene→need, 107 needs = 14 matched + 93 svg, 0 gaps |
| P2-T01 | ✅ | architect spike 2026-09-25 | Inkscape headless — `docs/scenes-mp4/DECISION_RASTER.md` |
| P2-T02 | ⬜ | | |
| P2-T03 | ⬜ | | |
| P2-T04 | ⬜ | | |
| P2-T05 | ⬜ | | |
| P2-T06 | ⬜ | | Needs P2-T01 first |
| P2-T07 | ⬜ | | Phase 2 gate |
| P3-T01 | ⬜ | | |
| P3-T02 | ⬜ | | |
| P3-T03 | ⬜ | | |
| P3-T04 | ⬜ | | Phase 3 gate |
| P4-T01 | ⬜ | | |
| P4-T02 | ⬜ | | |
| P4-T03 | ⬜ | | |
| P4-T04 | ⬜ | | |
| P4-T05 | ⬜ | | PROJECT gate = perfect video |

`⬜` todo · `🟡` in progress (max one) · `✅` done (acceptance evidenced) · `🛑` blocked (note why).
