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

# SPRINT 2.5 — DONE ✅ (Funnel Polish & Manual Override)

> Every AI surface now has a human override. Nothing is ever lost. 
> The funnel is production-ready.

## Completed tasks
- [x] 2.5.1 Idea control — Refine & Expand, 🤖 AI refine (creates v2), 🔒 Lock (is_current=1), ✏️ inline manual edit.
- [x] 2.5.2 Title control — 10-title accumulation preserved, 📥 Own-title door, ✏️ inline edit, 🎲 "3 variants of this one", ✂️ AI shorten (>70 chars), exclusive race-free lock.
- [x] 2.5.3 Outline persistence — Saved to DB + file mirror (`outline_v1.md`), manual edit (add/reorder/remove sections), 🤖 AI refine (creates v2), Σ budget tracker.
- [x] 2.5.4 Pass 3 punch-up — Select "##" section -> free-text note -> AI rewrite -> side-by-side diff preview -> Apply (unlocks) / Discard.
- [x] 2.5.5 Pass 4 sanity check — 🩺 One-click audit (names, timeline, tone drift, repetition, hook strength) rendered as a color-coded card.
- [x] 2.5.6 Import door — Paste/drop .txt/.md -> instant word/duration math -> source='imported' -> gets every tool.
- [x] 2.5.7 Editor polish — VersionPill (revert/delete versions), Hook strip (first 75 words highlighted), Pacing strip (color-coded per section), Breakdown (actual/target per row), ⚖ Rebalance button.
- [x] 2.5.8 S02/S03 Extras — 📥 Shelf toggle (hide good-but-not-now ideas), Skip Doors (Fast Lane jump buttons).
- [x] 2.5.9 Draft-length recipe tightening — Forced AI to hit ±5% word targets via rich expansion instructions.
- [x] 2.5.10 Git sync + Commit.

## Architecture & UX Lessons Learned
- **Race conditions in single-selects:** "Lock" must unlock all others first (last-click-wins). Fixed in titles.
- **AI Copy-Paste Failure:** LLMs are terrible at "copy this text exactly" (Auto-Section). Removed in favor of manual `## Heading` typing. 
- **Fail-Loud vs Fail-Silent:** Added `safeJson` in frontend to catch raw 500 text errors and show them as readable alerts instead of silent crashes.
- **The Golden Rule:** Editing a locked state = unlocking a new version. Never mutate history.

## Next up: Sprint 3 — The Brain
- P09 Cast Board (Character extraction + mentions)
- P10 Variant Timelines (Costume/age changes)
- P11 Scout Board (Environment extraction)
- P12 World Desk (Real-world assets, maps, memes)

# SPRINT 3 — DONE ✅ (The Brain reads the script)

> The app stopped just generating text and started reading the locked
> script like a production manager: cast, costumes, locations, real-world
> assets — all extracted, ID-minted by the app, file-mirrored, reviewable.

## Completed tasks
- [x] 3.1 Models + 4 extraction recipes + defensive sharding (§4.6)
- [x] 3.2 Characters backend — C## minting, dual-row RW## for fetched persons (P-03), mention map, diff/merge re-extraction, 04_cast mirrors
- [x] 3.3 S05 Cast Board UI — cards, significance dropdown, drawn↔fetched toggle, edit, stale section
- [x] 3.4 Variants backend — V## IDs, spans, confidence, rare/one-off flag, delete
- [x] 3.5 S06 Variant Timelines UI — vertical life-timeline per character
- [x] 3.6 Environments backend — E##/EV## minting, green_conflict flags, 05_world mirror
- [x] 3.7 S07 Scout Board UI — location cards, green banner, presence sections
- [x] 3.8 World backend — RW##/MT## scan (brands, persons, memes, map triggers with templates), approve/dismiss/edit
- [x] 3.9 S08 World Desk UI — grouped cards, counters, bulk select (approve/dismiss/delete), Select All
- [x] 3.10 Ripple v1 — script text change flags characters/environments/world stale; unchanged-lock guard; re-extract refreshes

## Proof points (real runs)
- Napoleon script: 19 characters + 80 mentions (aliases resolved with confidence 0.6-1.0); 12 variants = full life timeline (parchment boy → coronation robes → green-walled exile).
- Spice script: 18 cast (1 named core: da Gama; rest generic groups — correct for collective history); 0 variants (honest: nobody changes costume); 14 environments with 7 green_conflict foliage flags; 11 world records incl. 3 map triggers (region_highlight / split / flag_fill).
- Re-extraction never duplicates: diff/merge keeps IDs stable.

## Bugs found & lessons learned
- AI returns objects where strings expected → field_validator normalizers (environment variations).
- Free gateways sometimes return EMPTY bodies → 3x retry loops on backend + safeJson on frontend; friendly "wait 30s" messages instead of cryptic JSON errors.
- "Expecting value: line 1 column 1" was always a masked backend error — now fail-loud everywhere.
- Variants hide behind stale characters via SQL join — no separate variant ripple needed.

## Deferred (by design)
- Full ripple to sheets/beats (Sprint 5/6).
- Download Desk P22 consumes search_query/era_hint (Sprint 5/6).
- Meme-mode toggle UI (scan already detects memes).
- Library asset linking (Sprint 4).

# SPRINT 4 — DONE ✅ (The Look: P13–P16)

> The pipeline crossed the bridge from TEXT to PICTURES.
> Script → Beats (storyboard) → Sheets (artist briefs) → Library (real asset slots).

## Completed tasks
- [x] 4.0 Schema check — beats + beat_elements confirmed (internal FK kept).
- [x] 4.1 Beats backend (P13) — beat_breakdown recipe; B##/BE## minting; verbatim beat text;
      SVO action lines; overlay_text; text_only flags; elements linked to C/E/MT/RW with
      layer (background/midground/insert) + framing (wide/medium/close); 07_beats/beats.md mirror.
- [x] 4.2 Beat Board UI (S09) — stats bar (beats/seconds/elements), section-grouped timeline,
      TEXT-ONLY + overlay badges, color-coded element chips, per-beat delete.
- [x] 4.3 Sheets backend (P14/P15) — 06_assets sheets for every active character & environment;
      STYLE KIT descriptor header; beat-presence counts; variant lists; green-conflict warnings;
      deterministic 3x3 grid prompts (9 consistency panels; foliage-safe variant for green locations).
- [x] 4.4 Sheets UI (S10) — grouped list + preview, 🟢 markers, 📋 Copy 3x3 Prompt (clipboard),
      Regenerate Sheets.
- [x] 4.5 Library (LIB##) — library table via schema auto-heal; Scaffold creates one slot per
      active asset and sets characters/environments.library_ref; file upload → status READY +
      file mirrored to 06_assets/library/; production-readiness progress bar; safe unlink on delete.
- [x] 4.6 Doc + commit.

## Proof points (real runs — spice script)
- 63 beats / 94 elements / 0 unmapped. B05 text-only; B19 "Pepper = Currency" + RW04 coin insert;
  B37 C01 + MT02; B47 VOC logo; B63 closes on "You are eating history."
- 25 sheets written in the channel's real style voice; 6 environments carry the
  "AVOID chroma green" instruction inside their prompts.
- Library scaffolded 25 slots; upload flips READY and the C01↔LIB01 link is queryable.

## Bugs found & lessons learned
- dispatch returns PLAIN DICTS (model_dump) → dot-access crashes; bracket access everywhere now.
- Plain-text 500 = unhandled crash → inner-function + try/except wrapper pattern makes every
  endpoint fail-loud with a readable message.
- AI encoding artifacts (â€¢) normalized in the UI layer.
- Per-module plumbing checklist: file → main.py wire → JOB_MAP line → recipe file.

## Deferred (by design)
- Download Desk P22 (auto search + download into Library) → Sprint 5/6.
- Beat editor_note / improv_note UI (columns exist).
- Channel-level shared library (cross-episode reuse).
- Grid-prompt double-period polish.

# SPRINT 5 — DONE ✅ (The Build: P22 + assembly + export)

> The pipeline crossed from "knowing" to "having".
> Every beat can now answer: which images does this shot need, and are they ready?

## Completed tasks
- [x] 5.1 Download Desk — Library gained world slots (RW/MT); 🔎 opens the exact
      Google-Images search built from search_query + era_hint; uploading a found image
      records provenance on the world record (P-03 honesty).
- [x] 5.2 Shot Kit assembly — GET /beats/{id}/assets resolves the full chain
      beat → asset_ref → library slot → real file; 📦 panel on every beat shows
      READY/MISSING per layer+framing.
- [x] 5.3 Export / Handoff — one click writes 09_handoff/episode_package.json +
      episode_package.md: script, style kit, 63 beats with shot kits (✅/❌), cast with
      variants, environments with green flags, world assets with provenance, readiness %.
- [x] 5.4 Doc + commit.

## Proof points (real runs — spice project)
- B37 shot kit: C01 (midground/medium) + MT02 (background/wide) — after uploading one
  image in Library, the kit flipped to 1/2 READY everywhere (beat panel + package).
- episode_package.md reads like a professional episode bible, grouped by section.
- Readiness bar = the production metric: 0% → 100% is "ready to animate".

## Architecture lessons
- Library = single source of truth: one asset file serves every beat that references it,
  this episode and the next (consistency by construction).
- Scaffold pattern: Brain output auto-creates the artist checklist — nothing forgotten.
- Manual 🔎 + 📤 is the SAFE v1 of downloading (no copyright-unsafe auto-scraping);
  provenance always recorded.

## Deferred
- Headless auto-download (safety/copyright review first).
- Channel-level shared library (cross-episode reuse).
- Render-tool integration (the package is the integration point).

# PIXEL PLATFORMER — MVP DONE 🏁

> One wall of text in → one shootable episode package out.
> Idea → Title → Script → Brain → Look → Build → Ship.

## The seven sprints
- **S1 Foundation** — FastAPI + per-project SQLite + file mirrors (01–09), tiered LLM
  dispatcher, defensive sharding, app-minted IDs, pixel-platformer UI theme.
- **S2 Funnel** — Idea Studio, Title Studio, 4-pass Script Studio with streaming.
- **S2.5 Polish** — human override on every AI surface, punch-up diff preview,
  sanity check, script import, versions, shelf, skip doors.
- **S3 Brain** — Cast (C##/RW## dual rows), Variants (V##), Environments (E## + green
  flags), World (RW##/MT## map triggers), ripple v1 stale-flagging.
- **S4 Look** — Beats (B##/BE##, SVO, overlays, text-only), Sheets with 3×3 grid prompts
  in channel style voice, Library (LIB##) slots.
- **S5 Build** — Download Desk (🔎 search + provenance), Shot Kit assembly (📦),
  episode_package.json/.md with readiness %.
- **S6 Ship** — Checkpoint DoD gate (required vs recommended), Handoff sign-off →
  HANDOFF.md + stage handed_off.

## Proof (two real episodes processed end-to-end)
- **Napoleon bio:** 19 cast + 80 mentions, 12-variant life timeline, honest 0-variance
  where nothing changes.
- **Spice trade:** 18 cast / 14 locations / 11 world records / 63 beats / 94 elements /
  0 unmapped; 25 sheets; episode package + signed handoff.

## Principles that held
1. The app mints every ID — the AI never assigns identity.
2. Every AI surface has a human override; editing a locked thing = new version.
3. Fail-loud everywhere: safeJson, 3× retry loops, crash wrappers, readable alerts.
4. DB + file mirrors: everything survives as plain markdown/json on disk.
5. Stale = "needs review", never silent deletion.
6. Real-world assets carry provenance (P-03).

## Post-MVP backlog (when you return)
- Render-tool integration consuming episode_package.
- Channel-level shared library (cross-episode reuse).
- Auto-download with copyright safety review.
- Beat editor_note/improv_note UI; meme-mode toggle; grid-prompt polish.

## 60-second demo script
Home → pick project → Script (locked) → Cast Board → Variants → Locations →
World Desk → Beats (📦 B37) → Sheets (📋 copy prompt) → Library (readiness bar) →
Export (package) → Checkpoint (advance) → Handoff (🚀 sign-off). Done.