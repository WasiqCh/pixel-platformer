# SPRINT 1 — DONE ✅ (all verified on real hardware)

> Skeleton: app boots via launcher, brain talks to the LLM, theme lives,
> channel + style kit exist, projects create real folders + DBs.

## Verified tasks
- [x] 1.0 Environment — private GitHub repo; Python 3.14 venv; Vite+React; Tailwind v3; frontend on :3000.
- [x] 1.1 Boot — FastAPI :8000 + React :3000 connected; Pixel Platformer theme renders.
- [x] 1.2 Fonts — Press Start 2P / Pixelify Sans / Nunito loading (CDN for dev; self-host at packaging).
- [x] 1.3 Component shell — Sidebar pipeline map, TopBar, Card, BlockButton, StatusDot.
- [x] 1.4 Database — global app.db (6 tables) + per-project project.db (12 tables); WAL enabled.
- [x] 1.5 Core utilities — fs_manager (stable CH##_EP## paths, 07_beats/), id_generator (CH/EP/C/E/B/K/LIB + shared RW/MT counter).
- [x] 1.6 LLM dispatcher — recipes, 3 tiers, JSON validation + repair-retry, job_log; live test returned 5 validated titles through local gateway (cl/ models).
- [x] 1.7 S17 Settings UI — endpoint, 3 model slots + one-model checkbox, masked key, test-connection.
- [x] 1.8 S01 Home — channel create (CH01), project create (folders + project.db on disk), 3 entry doors, TopBar session.
- [x] 1.9 Launcher — start.bat boots both servers + opens browser automatically.
- [x] 1.10 Style Kit — reference images uploaded → AI vision descriptor drafted → saved (descriptor.md + avoid_list.md, kit_version bumped).

## Proof points (seen with our own eyes)
- POST /llm/test → 5 titles, job_log row clean (model, temp, tokens, duration).
- data/channels/CH01/style_kit/descriptor.md exists with real AI-drafted text.
- data/projects/CH01_EP01/ full 9-folder tree + project.db exists.
- start.bat → two server windows + browser auto-open; batch window exits cleanly.

## File inventory (Sprint 1)
- backend: main.py · core/{config,llm_client,id_generator}.py · db/{connection,migrations}.py · storage/fs_manager.py · api/{settings,llm,channels,projects}.py · models/title.py · recipes/{ideation,title_gen,style_descriptor}_v1.txt
- frontend: App.jsx · index.css · vite.config.js · tailwind.config.js · components/{Sidebar,TopBar,Card,BlockButton,StatusDot,KitWizard}.jsx · screens/{S01_Home,S17_Settings}.jsx
- root: start.bat · start.sh · requirements.txt · .gitignore · spec docs

## Intentional deferrals (not forgotten)
- Font self-hosting → at production packaging.
- Full ripple engine → Sprint 3 (stale flags exist in schema).
- Transparency drawer UI → Sprint 6 (job_log already records everything).

# SPRINT 2 — DONE ✅ (The Funnel: idea → locked script)

## Completed tasks
- [x] 2.1 Models + recipes — idea/title/script Pydantic schemas; recipes: surprise_me, script_outline, script_draft, script_punchup, script_check.
- [x] 2.2 Streaming infra — backend `dispatch_stream` (SSE) + frontend `useStream` hook (fetch+ReadableStream, Option B per §16.4); Stream Lab proved word-by-word pouring + Stop.
- [x] 2.3 S02 Idea Studio — Refine & Expand, Surprise Me (6 concepts), idea cards persisted to project.db, RW watchout + scale estimates shown.
- [x] 2.4 S03 Title Studio — 10 candidates with angle/style_tag/char-count, >70 amber warning, Lock → stage 'title'.
- [x] 2.5/2.6 S04 Script Studio — slider↔duration (@150wpm), Pass 1 outline (sums exactly to target), Pass 2 streamed draft, manual edit, Lock → scripts table + 03_script/locked_v1.md + stage 'script'.
- [x] 2.7 Lock mechanics — version insert, duration math, file mirror, stage advance.
- [x] 2.8 Git commit pushed.
- [x] 2.9 Home polish — rename (slug-only, P-01), fork (copies idea/title/script), delete (DB row + folder), Rescan (reconciles ghosts/orphans).

## Bugs found & lessons learned
- **BlockButton ignored `disabled`** → "Stream Full Draft" clickable with no outline → body `null` → 422. Fixed globally; all screens now safe from double-clicks.
- **Cross-database foreign keys are impossible in SQLite** → `REFERENCES projects(id)` inside project.db crashed ("no such table: main.projects") and left a locked connection. Removed cross-DB FKs; app logic enforces integrity.
- **Ghost state / orphaned records** — manually deleting a folder left a DB row; UI showed a ghost that 500'd. Terminology learned: orphaned record, ghost state, fail-loud. Rescan endpoint now auto-heals both directions.
- **Port collision** with another local project → backend moved to :8100 (frontend :3000; other project keeps :8000).
- **Catch-all route swallowed screens** → App.jsx now uses a `routed` list; unknown nodes get the placeholder, known nodes always render.
- **A11y console warnings** → all form fields got name attributes.

## Proof points (seen on screen)
- Constantinople idea card generated (8C/6E, RW watchout ⚠).
- Titles generated + one locked.
- Outline budgets summed exactly to 1400 and 1200 targets.
- Drafts streamed live (1019 & 808 words — free models under-deliver length; recipe tuning deferred).
- locked_v1.md on disk; rename kept folder stable; Rescan removed ghost rows.

## Deferred to polish (intentional)
- Pass 3 punch-up + Pass 4 check UI (recipes exist, UI later).
- Script import door, hook highlight, pacing strip, breakdown sidebar, VersionPill UI.
- Draft-length recipe tightening for free-tier models.
- (Fixed right after Sprint 2 close: script now loads back on revisit — GET /script + load-on-mount + editing-unlocks.)

## File inventory added in Sprint 2
- backend: api/{ideation,titles,scripts}.py · models/{idea,title,script}.py · recipes/{surprise_me,script_outline,script_draft,script_punchup,script_check}_v1.txt
- frontend: hooks/useStream.js · components/{StreamLab,SliderWithBadge}.jsx · screens/{S02_IdeaStudio,S03_TitleStudio,S04_ScriptStudio}.jsx