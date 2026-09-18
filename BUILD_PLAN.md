# BUILD_PLAN.md — Engineering Roadmap

> The build plan for the Pixel Platformer production app.
> Sibling docs (read together):
> - `LOCKED_DECISIONS.md` — WHAT we build and WHY (all 25 phases locked).
> - `HOW_IT_WORKS.md` — the workflow in plain language.
> - `UI_UX.md` — design system + screen inventory (S01–S17, G01–G02).
>
> **Golden rule:** one sprint at a time. A sprint is "done" only when it
> works on screen, not when its code exists.

---

## 1. Stack (locked at P01)

| Layer | Choice |
|---|---|
| Backend (the brain) | Python + FastAPI — all logic lives here |
| Frontend (the face) | React + Vite + Tailwind, "Pixel Platformer" tokens |
| Storage | Files-first (human-readable folders) + SQLite as working index |
| AI | `openai` Python SDK with `base_url` override (any OpenAI-compatible key) |
| Image/voice generation | NONE in-app — external tools; app writes prompts & packages |
| Deployment | localhost now (one-click launcher); cloud later (team login) |

---

## 2. Repository Layout

```text
app/
├── backend/
│   ├── main.py              # FastAPI entry
│   ├── api/                 # endpoints, grouped per sprint
│   ├── core/                # config, secrets, llm_client (P03 dispatcher)
│   ├── db/                  # sqlite connection + migrations
│   ├── models/              # pydantic schemas (JSON validation per job)
│   ├── services/            # one module per phase: p04_ideation.py … p25_overlays.py
│   ├── recipes/             # versioned prompt template files (recipe cards)
│   └── storage/             # file-system manager (channels/, projects/, library/)
├── frontend/
│   ├── src/
│   │   ├── theme/           # Tailwind config = the whole Pixel Platformer skin
│   │   ├── components/      # BlockButton, Card, StatusDot, AssetTag, DiffView…
│   │   ├── screens/         # S01…S17 + G01/G02 (from UI_UX.md)
│   │   └── hooks/           # api calls, streaming, job polling
│   └── vite.config.js       # proxies /api → FastAPI :8100
├── data/                    # USER DATA — gitignored
│   ├── settings.json        # endpoint, models (3 slots), key
│   ├── channels/CH01/       # style_kit/, library/
│   └── projects/…           # per-video folders (01_concept … 07_handoff)
├── start.bat / start.sh     # one-click launcher (boots server + opens app)
├── LOCKED_DECISIONS.md
├── HOW_IT_WORKS.md
├── UI_UX.md
└── BUILD_PLAN.md
```

---

## 3. Data Model

**Principle (P02):** every artifact also lives as a human-readable file
(txt + md mirrors); SQLite is the queryable brain. DB can be rebuilt from files.

| Table | Key columns |
|---|---|
| channels | id CH##, name, kit_version, has_host, overlay_tokens(json), tone_samples |
| projects | id EP##, channel_id, slug (renamable), stage, created/updated |
| idea_cards | project_id, version, content(json: concept/hooks/appeal/tags/scale/rw-watchout), shelf_flag |
| titles | project_id, version, text, angle, style_tag, char_count, locked, shipped |
| scripts | project_id, version, text, word_count, duration_sec, locked, locked_by/at |
| characters | id C##, project_id, kind(named/generic), faction, render(drawn/fetched), names+alias_map(json), appearance(json w/ source notes), green_conflict, library_ref, significance |
| variants | id C##-V#, character_id, span(json), delta(json), evidence, confidence |
| mentions | project_id, section, chunk, mention_text, resolved_to, confidence, context |
| environments | id E##, project_id, elements(json 3–4), green_conflict, library_ref |
| env_variations | id E##-#, environment_id, state, span, evidence |
| world_records | id RW##/MT##, project_id, type(brand/logo/person/meme/map), usage_intent, search_query(1–4 words), era_hint, mode(fetched/in_style_parody), layer, status |
| sheets | id C##-S#/E##-S#, parent_id, kind, grid, poses(json)/boxes(json)+box_map, status(draft_prompted→draft_imported→approved→final), background_color, kit_version, seed, model, prompt_text |
| beats | id B###, project_id, chunk_id K##, text, word_count, duration_sec, text_only, svo(json) |
| beat_elements | id B###-I#, beat_id, asset_ref, layer(actor/insert), framing, prompt_text(nullable = reuse), refs_to_attach(json), editor_note |
| library_assets | id LIB###, channel_id, kind, tags(json), context(json: source episode/situation/use-case), kit_version, usage_count, status(active/retired) |
| lessons | channel_id, observation, evidence, tweak, target_recipe, confidence, status(proposed/active/retired) |
| job_log | project_id, job_type, inputs(json), model, temp, raw_output, parsed(json), tokens, ts |

---

## 4. Sprint Roadmap

### 🏃 Sprint 1 — Skeleton (P01–P03, P08)
- [ ] Init repo; FastAPI + React/Vite; Tailwind Pixel tokens; fonts wired.
- [ ] S17 Settings: endpoint, 3 model slots + one-model checkbox, key paste, "test connection".
- [ ] `core/llm_client.py`: recipe loading, context packs, JSON validation + repair-retry, job_log.
- [ ] S01 Home: create channel (kit wizard: upload refs → AI descriptor → defaults), create/open/rename project; auto-scan projects dir.
- **DoD:** app boots via launcher; key works; channel with kit exists; theme visible.

### 🏃 Sprint 2 — The Funnel (P04–P07)
- [ ] S02 Idea Studio (cards, refine loop, Surprise me, Shelf, fast-lane).
- [ ] S03 Title Studio (10 candidates, regen-selected, own-title door, lock).
- [ ] S04 Script Studio (slider↔duration, 4 passes, streaming, hook highlight, breakdown, sanity card).
- [ ] P07 lock mechanics + versioning + finalization-learning capture.
- **DoD:** idea → locked script end-to-end; imported scripts get same tools.

### 🏃 Sprint 3 — The Brain (P09–P12)
- [ ] S05 Cast Board (+ drawn/fetched toggle, significance pick, resolution inspector).
- [ ] S06 Variant Timelines · S07 Scout Board · S08 World Desk.
- [ ] World annotations emission; defensive sharding; diff/merge re-extraction.
- **DoD:** locked script → four reviewed registries with IDs minted.

### 🏃 Sprint 4 — The Factory (P13–P17)
- [ ] S09 Choreography Board (lean sheets, suggestions tray).
- [ ] S10 Card View (8-slot anatomy, lint, slot-stable regen, copy prompt+refs).
- [ ] S11 Export Desk (package + checklist + Download Desk rows).
- [ ] S12 Checkpoint Board (auto-match import, pixel background check, 4+1 checklist, bulk triage).
- **DoD:** cards exported → drafts imported → approved → finals recorded with seed/model.

### 🏃 Sprint 5 — The Storyboard (P18–P21)
- [ ] S13 Library (reuse matching, extension sheets, savings counter).
- [ ] P19 chunking (local) + beat splitting (AI) + Beat Board.
- [ ] S14 Beat Studio (reuse-first elements, one-off tray, SVO reveal, pacing visualizer).
- [ ] S15 Storyboard preview + versioned handoff export (alignment table, editor notes, overlays list).
- **DoD:** locked sheets + locked script → exported handoff zip, preflight green.

### 🏃 Sprint 6 — Loop & Extras (P22–P25)
- [ ] Download Desk polish (browser-search buttons, role tags).
- [ ] S16 Channel Intelligence (metrics entry, retention→beat flags, lessons + diff approvals).
- [ ] Shot Type Registry + map redraw cards (P24) · overlay specs (P25).
- [ ] Team/cloud prep: auth stub, deployment notes.
- **DoD:** published video stats → one approved lesson visibly altering a new generation.

---

## 5. Engineering Conventions (from locked decisions)

1. Every AI job = recipe file + context pack + schema validation + repair-retry + job_log entry. No raw prose into the DB.
2. Version everything; never overwrite. Re-extraction/ripple = diff & merge.
3. Manual override affordance on every AI surface.
4. IDs minted by app only; export prefixes at handoff; AI never sees prefixed IDs.
5. Advisories never block (amber notes, lints); generation rules enforce (approved-sheets-only).
6. `data/` never in git; settings local; secrets never hardcoded.

---

## 6. Run Locally (dev)

```bash
# backend
python -m venv .venv && pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
# frontend
cd frontend && npm install && npm run dev   # proxies /api → :8100
```
Launcher (`start.bat`/`start.sh`) wraps both + opens the browser (P01 lock).