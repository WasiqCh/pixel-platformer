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