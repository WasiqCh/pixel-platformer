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
DEFERRED (post-P4 candidate, owner request 2026-09-26): visual improve — send the approved
raster PNG + fix-note to a vision-capable model on improve (plumbing exists:
`dispatch_vision` in `llm_client.py`; local vision models available). Today's loop sends
previous SVG *code* + text note only. Needs its own ticket when scheduled.

### DEFERRED BATCH (post-P4, owner request 2026-09-26 — each needs its own ticket, none disturb P4)

- **D1 per-asset targeting.** Fix-note/regen act on the beat's first SVG asset only
  (P3-T02 shortcut). Every asset gets its own Fix/Regen buttons.
- **D2 Assets page.** All assets in one place: provenance badges (generated / library /
  pasted); copy-prompt (exact svg_gen prompt to clipboard for external AI use);
  paste-code (external SVG validated like AI output, saved versioned, revertable);
  per-asset "bring my own" (skip generation, paste instead — manual-always-valid);
  SVG playground (paste code → preview PNG → download PNG, same raster engine).
- **D3 per-beat voice upload.** B##.wav-style uploads from any external source; each
  file IS its beat's duration, so timing stays intact with zero alignment.
- **D4 local Kokoro voice.** Free in-app narration, per beat, automatic timing. The
  default answer for cloud cost + laziness. Ticketed below as D4-T01 → T02
  (owner priority 2026-09-26 — implement before D1–D3/D5–D7).
- **D5 Setup screen.** Green ticks + one-click install for EVERYTHING a fresh machine
  needs — Inkscape/ffmpeg (winget) AND Kokoro (pip packages + weights download +
  espeak check, per D4-T01 findings) — runtime probing already in code for
  Inkscape/ffmpeg; add the same probe-then-install discipline for voice deps.
  Never ask a layman to type a path or pip-install anything. For teammate
  onboarding (fresh `data/` per machine is expected — gitignored by design).
- **D6 whole-audio align.** One uploaded audio file → Whisper word timestamps →
  force-align against the locked script (port `force_align_script` from
  `E:\Youtube\Editing Automation\audio_prep_engine 2.0.py`, lines ~18–123; GUI stays
  behind) → per-beat times → slice per-beat WAVs → normal render. Accepts any source
  (Kokoro whole-audio, external TTS) with zero manual splitting. Cost: torch/whisper
  weight + CPU minutes; ffmpeg already mandatory.
- **D7 quality re-gen pass.** Entire asset base is stand-in quality (qwen era); re-run
  generation + approval against real models before any real video. Machinery exists
  (re-plan replace, improve, revert, hash-cache raster).
- **D8 pipeline buttons (owner request 2026-09-27 — highest priority, current pain).**
  Ticketed below as D8-T01 (single frontend-only ticket, DONE).

### D1+D2 — ASSET CONTROL (owner priority 2026-09-27; after D8)

Why: the owner + Dawood judge assets one by one and bring their own code from
external AI. Beats approve whole; assets fix small — per asset, with provenance
visible and paste-in supported. Four tickets, in order.

**D1-T01 — Per-asset Fix/Regen on the beat strip (frontend-only).**
Today Fix-note/Regen hit the beat's first SVG asset (P3-T02 shortcut). Every
asset chip on the scene strip gets its own Fix + Regen buttons wired to the
existing per-generation endpoints (`POST .../generate/svg/{gen_id}/improve
{note}`, `POST .../generate/svg/{gen_id}`); library-matched assets show why
they have no buttons (nothing to redraw — honest inline note, current behavior
kept). No new endpoints, no backend changes.
*Acceptance: on a multi-asset beat, fix-note targets the clicked asset only
(proven by distinct version bumps on two different gens); lint 0 errors.*

**D2-T01 — Assets page (read + badges + copy-prompt).**
New screen in the `S##_` pattern, registered in `App.jsx` `activeNode` (no new
router lib): every project asset in one list — scene needs with provenance
badge (GENERATED: `needs_generate` + gen status / LIBRARY: `library_ref` /
PASTED: generation source flag when D2-T02 lands — badge logic must already
handle it) + status + preview thumbnail (existing image endpoints; labelled box
when no PNG). Copy-prompt button per svg gen copies the exact stored prompt
(the same text P2-T04 sends the model) to clipboard. Read-only ticket: no
writes, no new endpoints (existing list endpoints only).
*Acceptance: page lists all 107 CH03_EP02 needs with correct badges; copy-prompt
output byte-equals the row's stored prompt; lint 0 errors.*

**D2-T02 — Paste-code + bring-my-own (backend + page wiring).**
`POST /projects/{id}/generate/svg/{gen_id}/paste {code}`: validates pasted code
through the real `SvgGen`/`validate_svg_text` path (unsafe code rejected with
the same messages AI output gets), writes versioned `_vN.svg`, moves the newest
pointer (history intact — same semantics as improve). Works on pending rows
(skip-generation: user brings code instead of AI) and on generated rows (new
version). Page wires paste box + per-asset "bring my own" toggle (sets a
`source='pasted'` marker on first paste so the D2-T01 badge reads PASTED).
*Acceptance: paste valid code → new version + pointer; paste `<script>` →
400 with validator message, nothing written; pending row heals via paste;
badge flips to PASTED; old versions + revert intact.*

**D2-T03 — Playground (validate + raster, no project writes).**
`POST /projects/{id}/svg-playground {code}`: validates (same path), rasters via
the P2-T06 Inkscape probe to a temp PNG (hash-named under `%TEMP%`, never into
project dirs), returns the PNG for preview + download. Page section: code box →
Preview button → PNG shown → Download button. Nothing touches scenes/gens/library.
*Acceptance: valid code → 1920×1080 PNG downloads and opens; invalid code →
validator message, no file; two identical pastes → same bytes (cache);
project DB byte-identical before/after (prove with a hash or row counts).*

### D4 — LOCAL KOKORO VOICE (owner priority; implement before D1–D3/D5–D7)

Goal: free in-app narration with the identical output contract as Gemini TTS —
per-beat `08_export/voiceover/B###.wav` (24kHz mono 16-bit) + measured
`beats.duration_sec` — so the gate, P4 worker, and mux treat both providers
identically. Provider switch in voice settings; default stays Gemini until D4
passes on this machine.

**D4-T01 — Kokoro spike (tooling decision, one sitting, no app code).**
Settle before anything is wired: (a) can the project `.venv` (Python 3.14.0)
`pip install kokoro-onnx onnxruntime phonemizer` cleanly, or must the venv pin
change — record versions; (b) does phonemization work end-to-end (espeak-ng has
no system install here — only a DLL phonemizer unpacks into %TEMP% — so actually
phonemize a sentence and show output); (c) synthesize one sentence with local
weights to a 24kHz mono WAV that plays. Known weight locations (verify, never
hard-code in app code): `C:\Users\wasiq\Downloads\Kokoro\kokoro-v1.0.onnx`
(311MB) + `voices-v1.0.bin` (27MB).
*Acceptance: `docs/scenes-mp4/DECISION_KOKORO.md` recording venv verdict per
package, espeak path verdict, synth command + WAV proof (ffprobe rate/channels),
and the exact weight paths + voice list available. No D4-T02 before this.*

**D4-T02 — Provider switch + Kokoro per-beat build.**
`voice_settings` gains `provider` (`gemini` default) + `kokoro_voice`; Settings
screen offers the switch (disabled with a clear message when D4-T01 deps are
absent). New `_tts_kokoro(text, voice)` beside `_tts` in `backend/api/voiceover.py`;
`_run` picks by provider but keeps the identical loop (per-beat WAV, duration
measure, `asyncio.create_task` + status endpoint, 1s pacing). Voice names differ
per provider (Gemini `Kore` vs Kokoro voices) — store per-provider, never mix.
*Acceptance: same project voiced twice (once per provider) → both produce 30
WAVs + measured durations, gate passes on either, render works on either;
Gemini path byte-identical behavior to today (no regression).*

### D8 — PIPELINE BUTTONS (owner priority; unblocks the owner + Dawood)

The new pipeline's triggers have no UI (Phase 1 was API-only). One frontend-only
ticket: Beat Board buttons in click order, each calling its EXISTING endpoint
(no new endpoints, no logic changes).

**D8-T01 — Pipeline button row on the Beat Board.**
Add, above the beat list, in this order: ① Plan scenes
(`POST /projects/{id}/scenes/plan`) → ② Plan assets
(`POST /projects/{id}/scenes/assets/plan`) → ③ Generate-all SVGs (loop over the
project's pending `kind='svg'` generations calling existing
`POST /projects/{id}/generate/svg/{gen_id}` sequentially — do NOT route svg rows
through `POST /generate/all`, which is the PNG lane and 400s them) →
④ Render (`POST /projects/{id}/render`, then poll existing
`GET /projects/{id}/render/status` for a live progress bar) + ⑤ Cancel
(`POST /projects/{id}/render/cancel`, visible only while running).
Rules: busy disables the row (no double-fire); every response renders an honest
inline message (counts from the JSON, e.g. "30 planned, 2 failed" — never a bare
"done"); 409 from render shows the gate message verbatim with its fix list;
follow the existing `fetch('/api/v1/...')` + `safeJson` + `BlockButton` pattern.
*Acceptance: on a test project, click ①→④ in order with no console errors and
no terminal/API tools; busy states prevent re-click mid-run; render progress
bar reaches done and names the final MP4; `npm run lint` 0 errors.*

### D7 — QUALITY RE-GEN PASS (owner priority 2026-09-27; after D1+D2)

Why: the entire asset base is stand-in quality (qwen era, crude v1 placeholders).
This pass redraws every SVG against real models and re-approves the project.
Two tickets, in order. Run both against the owner's chosen High model and record
which model in the report (quality evidence, not just structural).

**D7-T01 — Bulk SVG re-generate (backend).**
`POST /projects/{id}/generate/svg/bulk {only: 'non-final'}`: sequential loop
over `kind='svg'` rows not yet final, calling the existing per-row generate
(new version each, never overwrite) with per-row crash isolation (one gen's
failure lands in its error field, never kills the batch — mirrors the PNG-lane
`generate/all` shape but stays in the SVG lane). Returns summary
(regenerated/failed/skipped-final counts + per-row versions). No frontend.
*Acceptance: all non-final svg rows gain exactly one new version from the
recorded model (prove via job_log model field, not just counts); failed rows
carry messages; previously-final rows untouched.*

**D7-T02 — Approval sweep + quality gate (UI-assisted audit).**
Approve every new version (existing Library/Assets approve buttons — human eyes
on all of them, crude ones get improve-with-note instead of approve), then
verify: all svg `final` with PNGs on disk, all 30 previews fresh (hashes differ
from the qwen era), render gate passes, one test MP4 renders clean.
*Acceptance: 107/107 final with real-model job_log rows; previews 30/30 fresh;
render check green; MP4 plays. THIS is the "no more placeholders" stamp.*

### D9 — RICH-SCENE ELEMENTS (owner priority 2026-09-27; after D1+D2)

Why: scenes today are actors on a place — no words, no photos, no maps. No
project becomes a finished explainer video without these. Three tickets, in order.

**D9-T01 — Overlay spec (data + AI propose).**
New `scene_overlays(beat_id, text, role, color, position, created_at)` table
(PROJECT_SCHEMA + heal). `overlay_text` already sits in JOB_MAP — verify its
tier/temp, write `backend/recipes/overlay_text_v1.txt`, and add
`POST /projects/{id}/scenes/overlays/plan`: per scene, AI proposes 0+ overlay
items (name/place/date/number/quote/warning roles with colors) or explicit
none — feasibility is the AI's judgement, human accepts/rejects per item
(manual PUT always allowed). Pydantic schema with non-empty reasoning.
*Acceptance: 30 scenes get a mix (not all-yes, not all-no); every proposal
carries reason + role + color; re-run never duplicates (replace-on-success,
P1-T06 precedent).*

**D9-T02 — Overlay render (Pillow text, no image model).**
Compositor (`scene_preview` + P4 frame path — one shared helper, never two
text renderers): draw each approved overlay as filled plate + bold text +
outline at its box; role colors from the item, font from a configured TTF
with a loud fallback (never PIL's bitmap default silently). Cache keys gain
overlay content (stale art on text change is a bug).
*Acceptance: preview shows plates pixel-crisp at 1920×1080; changing one
letter busts the cache; frames match previews; missing font fails loud.*

**D9-T03 — World Desk as asset source (+ map honesty).**
Asset planning also matches `world_records` (photo/logo/meme kinds with files
from the Download Desk) as `photo`/`insert`-layer assets; compositor pastes
them like any asset. Map-trigger (MT) records resolve to an honest labelled
"map coming" box — never a silent blank, never a faked map.
*Acceptance: a beat citing RW01 renders the real file; a beat citing MT01
renders the honesty box; trace query covers world-sourced assets.*

### D5+D10 — DAWOOD ONBOARDING (owner priority 2026-09-27; combined ticket)

Why: a layman teammate must walk the true road with zero installs by hand and
zero wrong turns. Sidebar regroup + Setup screen + plain-words render + My Video
output. Three tickets, in order. Nothing deleted, nothing renamed underneath —
old flows keep working.

**D5+D10-T01 — Sidebar regroup + purpose hints (frontend-only).**
Reorder nav to the real flow (Script → Cast/Locations/World → Beats → Assets →
Library → Checkpoint → My Video); Variants/Sheets/Export move under a "classic
(external art)" divider; one-line purpose hint under every entry
("Cast — who exists, feeds scenes" / "Sheets — external art only"); new
'My Video' node. No route logic changes, no deletions.
*Acceptance: top-to-bottom click order equals the real pipeline; legacy items
visually grouped; lint 0 errors.*

**D5+D10-T02 — Setup screen (first-run green ticks + one-click fix).**
New screen auto-opening when anything is missing. Probes (never typed paths):
Python packages, Inkscape (existing probe), ffmpeg (existing probe), Kokoro
deps + weights (D4-T01 findings), Ollama connection. Each missing item gets one
Fix button (winget for binaries, pip for packages, download for weights to the
D4-T01 paths or KOKORO_MODEL override). Re-probe after fix, all green to proceed.
*Acceptance: on a machine missing Inkscape, one click installs it and the tick
flips green; same for each item; nothing asks for a path.*

**D5+D10-T03 — Plain-words render + My Video output (frontend).**
Render progress component: "Making your video… 12 of 30 scenes", layman errors
with the fix attached ("Stopped at scene 14 — [name] failed. Fix it or press
Resume"), Resume where it stopped (existing cancel/resume endpoints). My Video
screen: versioned finals list reading `08_handoff/`, click-to-play + Download
per MP4 (existing file serving pattern). Reuses existing endpoints only.
*Acceptance: render speaks no jargon; a failed render names its scene + fix;
finished MP4 plays and downloads from My Video; lint 0 errors.*

### API BATCH — CALL ROBUSTNESS + MODEL CONTROL (owner priority 2026-09-27; deferred)

Why: free routed models are slow (SDK timeout is 600s, so hung calls haunt the
2-slot queue); button states live in the tab only (reload = amnesia); model
switches strand old-model queues with no windows and no cancel. Six tickets.

**API-T01 — Timeout knob.** Settings-level LLM timeout (default ~120s): slow
models get room, hung calls die with a clear error instead of blocking the
semaphore for 10 minutes. Thread through `_client`/`_chat` (all jobs share it).
*Acceptance: a call exceeding the knob fails with a timeout error naming the
job; normal calls unaffected; knob editable in Settings.*

**API-T02 — Per-project cancel switch.** Backend tracks live LLM tasks per
project; a "stop everything" endpoint drops queued + running tasks for that
project (cooperative checks at dispatch boundaries). Button on the pipeline
card next to the queue count.
*Acceptance: 10 queued calls → cancel → all marked cancelled within seconds,
semaphore free, no partial writes (validation-gated writes only).*

**API-T03 — Sticky buttons + queue count.** Button/disabled states derived from
server truth on load (running 5/30 survives reload); a visible "N calls waiting"
count from semaphore depth exposed via a status endpoint. Frontend only reads.
*Acceptance: reload mid-run restores exact states; queue count matches live
in-flight + waiting calls.*

**API-T04 — Run scoping.** Every batch stamped with a run id; responses from a
pre-switch/pre-cancel run can't overwrite post-switch results (stale responses
dropped with a log line, never applied).
*Acceptance: switch models mid-run → old-model latecomers dropped, new-model
results applied; job_log shows the drops, not silent overwrites.*

**API-T05 — Per-job model override.** Settings map job → model (e.g. coder for
`svg_gen`, fast one for the rest); resolution order job-map > tier > single.
*Acceptance: svg_gen runs on the coder while scene_plan runs on the chat model
in the same batch (prove via job_log model fields).*

**API-T06 — Palette wiring.** Channel kit palette flows into the svg_gen
`palette` context (today hardcoded `[]`, so models freestyle colors).
*Acceptance: palette set on kit → svg context carries it (prove via job_log
context_pack); generated fills stay inside the palette.*

### F1–F3 — FEEL + SPEED (owner priority 2026-09-27; after D5+D10-T03)

**F1-T01 — Style presets (data + dropdown, tiny).**
Ship 3 one-click channel presets (Wobbly from `docs/scenes-mp4/STYLE_WOBBLY_SKETCH.md`
+ Flat-toon + Paper-cut, owner words them) as versioned style-kit presets; picking
one fills the descriptor (+ palette when API-T06 lands). Dawood never faces a
blank descriptor again.
*Acceptance: 3 presets listed; picking Wobbly byte-fills the descriptor; custom
edits still allowed; new channel can start from a preset.*

**F1-T02 — Project background color (wheel, small).**
Project-level canvas background: color-wheel input on the project (default =
channel chroma, green auto-white logic untouched as the default); saved per
project; compositor + previews + frames read it; preview/frame cache keys gain
the color (stale art on bg change is a bug); recorded in handoff for editor
keying context.
*Acceptance: pick red → previews + frames red; back to default → chroma;
cache busts on change; fresh projects default correctly.*

**F2-T01 — Batch approve (frontend + existing endpoints, small).**
"Approve all clean beats" on the Beat Board: beats with zero missing + zero
clashes approve in one click (existing PUT per beat, sequential, per-beat errors
collected not thrown); human time goes only to the flagged remainder, listed
with reasons.
*Acceptance: 30-beat board with 6 problem beats → 24 approve, 6 listed with
reasons; no silent skips; lint 0 errors.*

**F3-T01 — ffmpeg motion by role, cheap filters only (backend render worker,
medium, isolated). Owner ruling 2026-09-27: NO xfade, NO zoompan (force
re-encode, slow). Allowed vocabulary only: pop-in (`fade in`, assets/plates),
slide in/out/up/down (animated crop window, plates + inserts), fade-out on the
final beat. Mapping by beat role/framing, subtle by default with an intensity
setting. Never touches planning/approval; worker-only change.
*Acceptance: rendered MP4 shows fades on pop-ins + slides on plates (prove via
frame diffs, not eyes); cuts stay cuts everywhere else (concat path untouched,
no re-encode); render time ≈ baseline.*

### SCATTER BATCH — STEIN-QUALITY SCENES (owner priority 2026-09-27)

Why: the default lines assets up like soldiers; Stein scatters. No asset cap
(verified: none exists — keep it that way). Placement logic lives in-app
(`_default_box` + compositor). Four tickets, in order. NOTE (owner ruling):
no max_tokens changes — 256k-context models read big; output caps are a
separate knob, untouched.

**S-T01 — Scatter placement (compositor default).**
Replace bottom-row `_default_box` with seeded scatter: per-beat seed (stable
across re-renders), region-weighted positions, mixed scales, overlap allowed,
nothing fully off-canvas, nothing fully covering another asset's face zone.
Explicit x/y/scale always wins (scatter is the default, never the boss).
*Acceptance: 10 previews show scattered, non-row layouts; same beat re-renders
byte-identical (seed stability); explicit placements untouched.*

**S-T02 — Coverage lint + per-beat re-plan (backend + strip hook).**
After asset planning, a local check (no AI): entities named in the beat vs
assets planned; thin beats amber-flagged with the reason ("mentions 4 things,
planned 1"); one-click per-beat re-plan from the flag. Never blocks.
*Acceptance: a deliberately thin beat flags with a correct reason; re-plan
from the flag fills it; rich beats stay silent.*

**S-T03 — Overlay recipe guidance (recipe-only).**
`overlay_text` recipe gains: max 1 plate + 1 badge per beat; muted world +
1–2 saturated accents palette discipline. No code.
*Acceptance: 30-scene propose pass obeys the caps; accents sparing on review.*

**S-T04 — Per-asset web-fetch + image upload (backend + Assets page).**
Every asset gets: regen / retry / paste-code (exists) + NEW fetch-through-web
(Wikimedia search → pick → attach file, license recorded) + NEW upload image
(PNG/JPG accepted beside SVG — an asset is not necessarily vector). Manual
always wins: user file beats AI output, no questions.
*Acceptance: fetch attaches a licensed file; upload accepts PNG + SVG;
replaced asset keeps version history; preview shows the real file.*

### IDENTITY CHAIN — SAME CHARACTER EVERY BEAT (owner priority 2026-09-27)

Why (owner catch, verified in code): the draw call receives name + one
description paragraph — never the extracted appearance, never a sheet image.
Same character across beats can drift into cousins. Three tickets, in order.

**I-T01 — Identity text into draw calls (backend, small).**
For needs matched to a character/environment, append its extracted identity
(appearance slots / elements) into `asset_description` server-side inside
`_svg_asset_info` — no recipe change (description key already exists), no new
endpoints. Unmatched/generic needs byte-identical context.
*Acceptance: a C-matched gen's context_pack in job_log carries the appearance
text; a generic prop's context unchanged; two beats, same character, visibly
closer (human eyes) or at least textually anchored (job_log).*

**I-T02 — Cast consistency check (backend endpoint, small, no AI).**
`GET /projects/{id}/cast-consistency`: per character across beats, palette hash
+ silhouette hash of approved PNGs; outliers listed with distances. Report only,
never blocks.
*Acceptance: a deliberately-off asset flags with the largest distance; uniform
cast stays silent.*

**I-T03 — Local recolor (backend + Assets page, small, zero AI).**
`POST .../generate/svg/{gen_id}/recolor {mapping}`: fill-swap transform on the
SVG text (parse fills, map old→new, write new version, history intact). Page:
click a fill swatch → wheel → preview updates. Layman-safe (no code visible).
*Acceptance: recolor round-trips (red→blue→red byte-equal); invalid color 400;
revert intact.*

### ST-T01 — PROJECT STATUS ENDPOINT (owner priority 2026-09-27; small)

Why: runbook/agents/UIs ask six queries to learn project state. One call
answers all. Read-only aggregate, no writes, no new tables.

**ST-T01 — `GET /projects/{id}/status`.**
Single JSON: beats total/stale, voice WAVs present/missing, scenes
approved/unapproved/stale, assets matched/pending, gens by status, overlays
count, gate (`can_render` + blocker lists, reuse `render_gate`), latest render
job (status/progress/output). Compose existing queries only — no new logic.
*Acceptance: one call on CH03_EP02 returns correct counts matching the six
individual endpoints; unknown project 404; zero DB writes (prove read-only).*

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
| P2-T02 | ✅ | uncommitted | svg_path TEXT on generations (PROJECT_SCHEMA + _ensure_column heal); 06_sheets/svg dir; svg guard in _generate_row; 93/93 svg rows round-trip, PNG absent |
| P2-T03 | ✅ | uncommitted | svg_gen {high,0.5,no-stream} in JOB_MAP; recipe svg_gen_v1 (style+palette+outline 1.5-2.0% rule, prev_svg+fix_note); SvgGen schema (XML+viewBox/width/height, no script/ext-refs, reasoning non-empty); 3 dispatch trials live-gateway good ok (job_log 206) + bad rejected (207) + repair ok (208) |
| P2-T04 | ✅ | 1104486 | POST /projects/{id}/generate/svg/{gen_id} (generation.py): live svg_gen dispatch → SvgGen validate → 06_sheets/svg/<asset>_vN.svg, status generated; failure → error+message, retry mints next version, never overwrites; svg_gen max_tokens 2000 (gateway free-route 256-cap proven via captest, T1 256/finish:length vs T2 997/finish:stop); CH03_EP02 live: gen97 v1+v2 (job_log 212/213), gen43 error→v1 (214), gen98 malformed-XML rejected (215), 90 rows untouched pending |
| P2-T05 | ✅ | 86ff88e | POST .../svg/{gen_id}/improve {note} (shared _build_svg_context: style+asset desc+previous_svg+fix_note → _v(N+1), never overwrite) + POST .../revert {version} (pointer only, history intact) + GET versions; CH03_EP02 live via :20128: gen43 v1→v2 (job_log 217 ok) hashes differ, revert→v1 both files intact; guards 400 empty-note/no-prior, 404 unknown version |
| P2-T06 | ✅ | 75ad48d | POST .../svg/{gen_id}/approve (Inkscape probe INKSCAPE_PATH→PATH→MSIX glob/appx, never hard-coded; 06_sheets/raster/<base>_<hash12>.png; identical hash = cache hit, no re-raster; file_path = PNG so existing image endpoint serves render) + POST .../finalize (approved→final) ; UI shows PNG never SVG (S11_Library img via image endpoint + ✓/★ buttons); CH03_EP02 live: 5 PNGs (43v1/v2, 97v1/v2, 44v1), re-approve cached:true, image endpoint 200 image/png |
| P2-T07 | ✅ | uncommitted | Phase 2 gate PASS (audit-only, no code change): CH03_EP02 93 svg (approved 2 + final 1 PNGs on disk 3/3, error 4/4 with message, generated stuck 0, pending 86 untouched sampling); structural gaps 0 (dangling 0, stranded 0, XOR 0, beat-missing 0); 86 pending = coverage not stranding (gateway :20128 flaky), structural scope per owner, not quality review |
| P3-T01 | ✅ | uncommitted | GET /projects/{id}/scenes/{beat_id}/preview (scenes.py): Pillow 1920x1080 place+needs composite, x/y/scale-or-framing default, fit/letterbox never stretch, missing=labelled box, hash cache 07_beats/previews/; CH03_EP02 B01-B10 all 1920x1080, B01 missing 2/4 edge_px 30232, re-fetch cached:true |
| P3-T02 | ✅ | uncommitted | S09 beat cards: preview <img> (GET scenes/{beat}/preview, lazy, onError fallback) + 3-button row (approve=PUT status real, fix-note→svg improve {note} real via beat's first gen asset, regen=POST svg/{gen} real; beats with no SVG asset get honest inline msg — no scene-level AI endpoint exists); CH03_EP02 B01-B10 approved 1 click each; lint 0 errors (24 pre-existing warnings, 0 from S09) |
| P3-T03 | ✅ | uncommitted | POST /projects/{id}/render gate-only (409 while any scene unapproved/stale or any beat lacks wav; 200 ready when 30/30 approved + audio) + GET .../render/check + additive render_gate on checkpoint (required gates untouched); CH03_EP02 live: reject 409 (20 unapproved + 30 no-wav) AND pass 200 (temp approve-all + 30 silent WAVs), state reverted 10/20 + no voiceover dir; no frontend |
| P3-T04 | ✅ | uncommitted | Phase 3 gate PASS (audit + backlog grind, no code change): CH03_EP02 30/30 scenes approved (clicks.log median 1); 107 needs = 0 library_ref + 107 final SVG (93 Phase-2 backlog + 14 LIB01-dangling rematch gens 136-149), trace query 0 gaps (final + SVG/PNG on disk + ok svg_gen job_log per title); gateway :20128 think-tag-flaky all day (job_log 219-224 + smoke gen48) so Ollama stand-in (7b grind + 14b for 128/141, P1-T06 precedent; settings restored to :20128 after); previews 30/30 fresh, missing=1 (honest place box only); art = crude v1 placeholders, improve loop available |
| P4-T01 | ✅ | uncommitted | render_jobs in PROJECT_SCHEMA (heals old DBs via init_project_db) + worker/status/cancel in render.py (asyncio.create_task, DB-persisted progress, between-segments cancel, resume same row at N); stale-beats own gate message (total==0 + mixed branches); CH03_EP02 live: start 0/30 → 2/30 → cancel N=2 → resume 2 (job 1) → done 30/30; job_log 0 rows in render window (no LLM) |
| P4-T02 | ✅ | uncommitted | Frame builder in P4-T01 worker shape (render.py: _FPS=30, _frames_for_duration=max(1,round(dur*30)), _write_beat_frames byte-copy via to_thread, fresh wipes frame_*.png / resume overwrites idempotently) + 07_render/frames in fs_manager; previews reused via scenes.scene_preview (zero Pillow duplication, no ffmpeg, no LLM); CH03_EP02 live: start 0/30 → 6/30 → cancel N=6 (1548 frames = 7 beats incl. in-flight, resume overwrote same range) → resume 6 → done 30/30 (job 2, job 1 history intact); 6000/6000 frames = Σ, B01-B10 2160/2160, 30/30 frame-1 byte+pixels match approved preview 1920x1080 + full-beat hold identical, sequence 1..6000 contiguous, job_log +0; temp 30 silent WAVs reverted (no voiceover dir), frames remain for T03 |
| P4-T03 | ✅ | uncommitted | ffmpeg probe (FFMPEG_PATH→PATH, tried-list error like Inkscape) + per-beat PNG-loop+WAV→seg_###.mp4→concat to versioned 08_handoff/<proj>_final[_vN].mp4 + frames-empty assert (render.py; 07_render/segments in fs_manager); CH03_EP02 live: jobs 4/5/6 done 30/30, ffprobe 200.04s vs Σ narration 200.0s, frames 0 segs 0, _v1/_v2/_v3 intact, cancel@6→resume@6 same row, job_log +0 (no LLM); temp silent WAVs reverted, stale-server job 3 (frames-only, pre-T03 code) left as history |
| P4-T04 | ✅ | uncommitted | Final-output verification (no code change): CH03_EP02 job 7 done 30/30 → _v4 (ffprobe h264 1920x1080 30fps 200.0s + aac 200.04s, full decode clean); frames 0, segs 0; _final/_v2/_v3 hashes identical pre/post; job_log +0 (no LLM); temp silent WAVs reverted, gate re-blocks |
| P4-T05 | ✅ | uncommitted | PROJECT gate PASS (audit-only, no code change): CH03_EP02 full pass script→scenes→approved→MP4; (a) ffprobe _v4 h264 1920x1080 30fps video 200.0s / aac 200.042667s vs SUM(beats.duration_sec) 200.0s (diff 0.04s ≤1s), nb_read_frames 6000 = SUM(round(dur*30)), full decode clean; (b) 30/30 scenes approved stale 0, 30/30 beats have preview (1920x1080, B01 94347B), 107/107 needs final SVG with PNG+SVG on disk, XOR/dangling/stranded 0, job 7 done 30/30 → _v4, frames 0 segs 0, 4 finals identical SHA 771A25; (c) job_log 250 rows (58 scene_plan ok, 37 asset_plan ok +1 logged err, 109 svg_gen ok +30 logged err, all errs carry error text, null-token/empty-raw 2/2 both logged errs), render +0 rows by design; temp silent WAVs reverted so render/check re-blocks (30 missing audio) — _v4 remains the pass artifact |
| D4-T01 | ✅ | b38e0aa | Kokoro spike GO on project .venv py3.14.0, no pin change (kokoro-onnx 0.4.7, onnxruntime 1.30.0 cp314 wheel, espeak-ng DLL via espeakng-loader + Tokenizer phonemize proven, af_heart 24kHz mono WAV proof) — `docs/scenes-mp4/DECISION_KOKORO.md` |
| D4-T02 | ✅ | 050bd60 | Provider switch (gemini default; kokoro gated on clean deps import) + Kokoro per-beat build reusing exact voiceover loop (same WAV contract, same status endpoint); CH03_EP02 30/30 kokoro WAVs (af_heart, Σ 203.2s), gate passes, gemini _tts byte-identical + mock loop 30/30 |
| D8-T01 | ✅ | uncommitted | Pipeline button row on Beat Board (S09_BeatBoard.jsx +157, frontend-only): ① plan scenes → ② plan assets → ③ per-row POST generate/svg/{gen_id} loop (never generate/all) → ④ render + poll status progress bar → ⑤ cancel while running; busy disables row, counts inline, 409 verbatim; lint 0 errors, build clean |
| D1-T01 | ✅ | uncommitted | Per-asset Fix/Regen on beat strip (S09_BeatBoard.jsx frontend-only): assetKey beat:id per-chip Fix+Regen wired to POST generate/svg/{gen_id}/improve {note} + POST generate/svg/{gen_id}; library assets honest inline note, no buttons; replaces P3-T02 first-asset shortcut; CH03_EP02 B01 3 assets gens 43/44/45 distinct targeting + lint 0 errors |
| D2-T01 | ✅ | uncommitted | Assets page read-only (new S15_Assets.jsx + App.jsx assets route + Sidebar Assets node; no backend, no new endpoints): CH03_EP02 107/107 needs list via existing GET scenes/assets+generations+library; badges GENERATED 107 / LIBRARY 0 / PASTED 0 with gen.source==='pasted' guard for D2-T02; thumbs via existing GET generations/{id}/image (gen43 200 image/png 21036B) + NO-PNG labelled box; copy-prompt writeText(gen.prompt) verbatim, DB==API byte-equals gen43 len 293 True; lint 0 errors (24 warnings baseline, 0 new) |
| D2-T02 | ✅ | uncommitted | POST .../generate/svg/{gen_id}/paste {code} via real validate_svg_text (same <script> message AI gets), versioned _vN + pointer move + source='pasted' (generations.source via PROJECT_SCHEMA + _ensure_column heal); S15 paste box + per-asset bring-my-own (pending label vs new-version label, badge flips in place); S09 micro-fix: scene strip INSTEAD of 📦 box where scene row exists (both gated on !scenes[b.id], frontend-only); CH03_EP02 live: TEST gen150 pending→v1 generated/pasted, <script> 400 nothing written, →v2 (186B vs 174B differ), revert→v1, API source='pasted', cleanup 107/107 final seq 149; lint 0 errors (24 warnings baseline, 0 new) |
| D2-T03 | ✅ | uncommitted | POST .../svg-playground {code} via real validate_svg_text (same <script> message AI gets), P2-T06 Inkscape probe → hash-named %TEMP% svg_playground_<hash12>.png (never into project dirs), PNG bytes back + X-Playground-Cached/X-Svg-Hash headers; S15 playground card (code box → Preview PNG → PNG shown → Download, blob URL, no scenes/gens/library state); CH03_EP02 live: valid → 1920x1080 RGBA PNG 29690B, POST1 fresh→POST2 cached:true byte-identical sha 88fb3f, <script> 400 nothing written, project.db sha 06a27a2e identical before/after (counts 149/107/30/30, 365 files inventory identical); lint 0 errors (24 warnings baseline, 0 new) |
| D7-T01 | 🟡 | uncommitted | Bulk POST .../generate/svg/bulk {only:'non-final', limit?} (generation.py, registered before /{gen_id} so 'bulk' never parses as gen_id; sequential await, per-row try/except-continue, summary regenerated/failed/skipped_final + per-row versions); CH01_EP08 live limit=2: processed 2 regenerated 2 failed 0 (gens 32/33 pending→generated v1, job_log 406/407 model qwen2.5:7b temp 0.5 ok); guards 400 bad-only/bad-limit, 404 unknown project; 61 non-final remain — full bulk NOT run per instruction, needs owner go-ahead |
| D7-T02 | ⬜ | — | Approval sweep + quality gate (not started; needs D7-T01 full bulk first, then human approve-all + previews + render gate + test MP4) |
| D9-T01 | ✅ | uncommitted | Overlay spec data+AI (scene_overlays in PROJECT_SCHEMA, heals old DBs; overlay_text {medium,0.5} verified + overlay_text_v1 recipe; POST .../overlays/plan replace-on-success + GET list + PUT/DELETE manual; OverlayItem/OverlayPlan non-empty reasoning; CH03_EP02 live: 30/30 planned 49 overlays 29-with/1-without mix, 0 empty reason/role/color, re-run 49→49 dupes 0, PUT round-trip, job_log 30/30 ok qwen2.5:7b) |
| D9-T02 | ✅ | uncommitted | Overlay render (scenes.py shared _draw_overlays via _probe_overlay_font/_overlay_font TTF bold-first + _parse_plate_color from item + zone stacking; render.py single-renderer comment, no second text path; cache key gains overlays[] content; missing/label boxes + beat tag moved to same TTF; X-Overlays-Total header; CH03_EP02 live: B02 1920x1080 110510B plates #4DC3FF/#B8B8C0 sampled, 1-letter July 1497→1498 busts d4c58d→5ab289 cached:false bytes differ, revert restores d4c58d, 3/3 frames byte-match preview, probe fail loud FileNotFoundError tried-list, 0 load_default() calls) |
| D9-T03 | ✅ | uncommitted | World Desk as asset source + map honesty (scenes.py only, no schema, no AI job, no frontend): BE-driven photo injection (_ensure_beat_world_assets: MT always honesty row, RW only with Download Desk file, kind=photo insert-default, idempotent insert-if-missing) + MT guard on LLM-need path (MT match → honesty row, never SVG faked map) + POST .../assets/world-sync backfill (no LLM, safe on 107 finals) + compositor pastes world files like any asset (_draw_map_coming_box via shared TTF, X-Map-Count/X-World-Total, cache key gains is_map/world_id); CH03_EP02 live: world-sync 10 MT + 6 RW = 16 photo rows (123 total = 107 final SVG untouched, XOR 0, MT-with-gen 0), B02 RW01 real file (LIB20 green 40770px) + MT01 honesty box (mapfill 329692px) headers Map:1 World:2 Missing:2 Assets:7, re-fetch cached:true same hash, re-sync 0 dupes; RW01 file is synthetic green test PNG (provenance test cc0) — real Download Desk portrait replaces it |
| D5+D10-T01 | ✅ | uncommitted | Sidebar regroup + purpose hints (frontend-only): nav reordered to real flow script→cast→locations→world→beats→assets→library→checkpoint→myvideo (Sidebar.jsx, ids+labels unchanged); variants/sheets/export under "classic (external art)" divider; hint under every entry (cast "who exists, feeds scenes", sheets "external art only"); new My Video node (S16_MyVideo.jsx placeholder, App.jsx routed+render, full output in T03); backend diff empty; lint 0 errors, build clean |
| D5+D10-T02 | ✅ | uncommitted | Setup screen (new backend/api/setup.py + S19_Setup.jsx, App.jsx auto-open-once + routed, Sidebar Setup node first): GET /setup/status reuses Inkscape/ffmpeg/Kokoro probes + fresh-import packages + Ollama /api/tags; POST /setup/fix/{id} one button per item (pip/winget/weights-download, PATH refresh, re-probe same probe); live: all-green 5/5, real missing→fix→green loop on packages (sse-starlette uninstall→pip reinstall 3.4.11), other 4 already-ok re-probed green, S19 zero inputs; lint 0 errors (25 warnings: 24 baseline + 1 same-pattern) |
| D5+D10-T03 | ✅ | uncommitted | Plain-words RenderProgress (scene counts, named-scene errors + Resume) shared by S09 + S16 My Video; GET .../render/finals + GET .../render/file/{name} in render.py (read-only FileResponse pattern); CH03_EP02 4/4 finals play+download byte-identical, layman mapping proven, lint 0 errors, build clean |
| F1-T01 | ✅ | uncommitted | Style presets (channels.py GET /channels/kit/presets + KitWizard dropdown): 3 listed (wobbly ready v1, flat-toon + paper-cut pending-owner-words stubs with null body, zero invented text); Wobbly served byte-identical from STYLE_WOBBLY_SKETCH.md paragraph (sha 32d06dc9 both sides); picking fills descriptor textarea, Save Kit bumps kit_version, textarea stays editable; new channel CH04 preset→PUT→GET byte-equal, custom edit kept, reverted; lint 0 errors (25 warnings = post-T02 baseline, 0 new) |
| F1-T02 | ✅ | uncommitted | Project background wheel (projects.py GET/PUT .../background {color} NULL=resets, resolve_project_background NULL→channel chroma; scenes.py _resolve_canvas_bg + bg in hash + X-Background-Color + canvas fill; render frames inherit via scene_preview byte-copy; handoff canvas_background JSON+MD; S09 wheel+reset; asset green auto-white untouched); CH03_EP02 live: red #FF0000 corners (255,0,0) 4257 samples, default #00FF00 corners (0,255,0) 4257, hashes f8d2b8→40a04a bust cached:false→true, bad-color 422, fresh CH03_EP03 default, handoff JSON+MD recorded; lint 0 errors (25 warnings baseline, 0 new) |
| S-T03 | 🟡 | uncommitted | Overlay recipe caps (overlay_text_v1 only, no code): 1-plate+1-badge hard caps (plate=name\|place\|quote, badge=date\|number\|warning, FORBIDDEN pairs + count-and-repair checklist, quote costs the plate slot) + muted-world/≤2-sat-accents palette + position MUST closed-set; CH03_EP02 30-scene probe (job_log 535-564, qwen2.5:7b, 0 err): 30/30 planned 0 failed, ≤2/beat 30/30 (was 3×3s), sat ≤1 30/30 (16×0/13×1 sparing), mix 29/1, schema valid, plate-subcap 27/30 — residuals B19/B21/B25 (2-plate pairs) on stand-in 7b; needs High-model re-probe for ✅; test data reverted (sha 8b1fab668f99, 49/29/30) |
| S-T01 | ✅ | uncommitted | Seeded scatter default (scenes.py only, compositor): _scatter_default per-beat seed (sha256 beat_id ^ idx) + region weights 30/20/20/15/15 + scale jitter 0.85-1.2x + _scatter_deconflict face-guard (explicit never moves, overlap-ok); _default_box kept legacy; frames inherit via scene_preview byte-copy; CH03_EP02 live: B01-B10 scattered non-row (xspread>0.05, mixed scales, old row-cache busted cached:false→true), B01/B03 re-render byte-identical, B02 explicit MT01/RW01 override (hash 29b827→727f63) stable + revert restores baseline byte-equal, 10/10 on-canvas + 0 full-face covers |
| S-T02 | ✅ | uncommitted | Coverage lint + per-beat re-plan (scenes.py GET .../scenes/coverage no-AI thin=planned< named + POST .../assets/plan?beat_id= filter on existing AI loop, beat_id echoed; S09 amber flag + one-click Re-plan this beat, per-beat busy, never blocks); CH03_EP02 live: baseline 0/30 thin, staged B10 thin "mentions 3 things, planned 1" 29 silent, approve-while-thin 200 + unknown-beat 404, re-plan B10 1/1 5 needs=1 matched+4 to-generate job_log 566 qwen2.5:7b stand-in (AM/... 404, settings restored) → 0/30 thin B10 5v3 silent; lint 0 errors (25 warnings baseline, 0 new) |
| S-T04 | ✅ | uncommitted | Per-asset web-fetch (GET fetch-search Wikimedia + POST fetch attach: versioned 06_sheets/fetch/<base>_vN.ext, license+source_url recorded, source='fetched') + image upload (POST upload multipart .svg/.png/.jpg/.jpeg, source='uploaded', SVG supersedes stale fetch pointer, approve keeps fetch/ user file) + S15 per-asset Fetch/Upload UI (FETCHED/UPLOADED badges, license line, file_path-keyed thumbs); CH03_EP02 TEST-row proof: fetch v1 licensed sha-match + image 200 + jpg v2 (v1 intact) + bad-upload 400/0-files + svg→approve raster + fetch-only approve user_file keep + versions both lanes + B01 preview assets+1/missing-same + png upload 200; Wikimedia search live-502 here (egress-IP robot-policy 403 ×3 hosts, code = download_desk license-filter shape); TEST rows/files cleaned (153/125); lint 0 errors (25 warnings baseline, 0 new) |
| F2-T01 | ✅ | uncommitted | Batch approve (S09 frontend-only +137, existing endpoints, compositor/placement/approval untouched — S-T01 owns): "Approve all clean beats" — clean = scene present + not stale + ≥1 asset + all svg gens final + no FLASH/HOLD/CROSSFADE (library/world incl. MT honesty count present; systemic place-missing non-blocking per P3-T04 semantics); sequential PUTs, per-beat errors collected not thrown, flagged listed with reasons, buckets sum to total; CH03_EP02 staged-6 proof: 24 approved (24× PUT 200) + 6 flagged (B01 stale+gen43 pending, B30 no-scene, B13 FLASH 3.0s, B15 CROSSFADE, B17 HOLD 11.5s, B24 HOLD 11.2s), 0 failed 0 skipped, sum 30, restored 30/30 approved stale 0 + 107 finals; lint 0 errors (25 warnings baseline, 0 from S09) |
| F3-T01 | ✅ | uncommitted | ffmpeg motion by role, cheap filters only (render.py worker-only, planning/approval untouched): _motion_settings (SCENES_MOTION=off/PX/FADE_IN/FADE_OUT env, subtle default 12px/0.2s in/0.5s out) + _motion_direction (overlay position→4-dir, else framing, else chunk keyword, else idx%4) + _motion_vf (pad+animated crop+fade only, 1920x1080 out) + _encode_segment vf passthrough; concat -c copy untouched, xfade/zoompan in comments only, zero filter usage; CH03_EP02 job 8 → _v5: fade-in luma 0.0→84.7 over n0–6, slide d(n10,n40)=4.31 vs 0.08 floor, cut d(179,180)=76.2 single-frame + beat2 fade ramp, fade-out 76.1→9.9 over last 15f, ffprobe h264 1920x1080 30fps 6068f/202.68s vs Σ203.2s, wall 49.7s inside baseline 43.9–60.6s, bench vf 0.82s vs no-vf 0.70–1.12s + 181/181 frames |
| ST-T01 | ✅ | uncommitted | GET /projects/{id}/status (dashboard.py only, no new file/table): beats 30/0, voice 30/0, scenes 30 appr, assets 125=17+108, gens 153 final107/pending46, overlays 49, gate can_render true (reused render_gate verbatim), job 8 done → _v5; CH03_EP02 all-match True ×11, unknown 404, project.db+app.db sha identical + counts identical across calls |
| I-T01 | ✅ | uncommitted | Identity text into draw calls (generation.py _svg_asset_info only, no recipe, no endpoints): character→appearance / place→elements appended to asset_description server-side (mirrors scenes._entry_matches); CH03_EP02 live: gen136 Vasco 382→675 appearance-anchored, gen44 Cape 332→556 elements-anchored, gens 43/45/46 generic byte-identical True; job_log 567 matched Identity-present vs 568 generic absent |

`⬜` todo · `🟡` in progress (max one) · `✅` done (acceptance evidenced) · `🛑` blocked (note why).
