# 🏗️ PIXEL PLATFORMER — Complete Engineering Blueprint

> **Purpose of this document:** This is the single-source-of-truth masterplan for an AI agent to implement the entire application. Every section is explicit — no guessing, no "figure it out." Read top-to-bottom before writing a single line of code.

---

## 0. What This App IS (and ISN'T)

**IS:** A localhost web app that serves as a **production office for animated YouTube videos**. It plans, writes, tracks characters/environments/assets, assembles prompt cards for external image generation, splits narration into beats, and packages everything into editor-ready handoffs. After publishing, it ingests video performance stats and learns from them.

**IS NOT:** An image generator. A video editor. A drawing tool. Those happen in external tools. The app writes the *prompts* and *packages the references* — the human takes those to Midjourney/DALL·E/ComfyUI/whatever and brings the images back. This separation is **permanent and by design**.

---

## 1. Tech Stack (Non-Negotiable)

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Backend** | Python 3.11+ · FastAPI | ALL business logic lives here. The UI is a dumb display layer. |
| **Frontend** | React 18+ · Vite · Tailwind CSS | "Pixel Platformer" theme. Optional shadcn/ui later. |
| **Database** | SQLite (single `project.db` per project) | Queryable index. Can be rebuilt from files. |
| **File Storage** | Filesystem-first | Every artifact has a human-readable file (`.txt`/`.md`). The DB mirrors it. |
| **LLM** | `openai` Python SDK with `base_url` override | Works with any OpenAI-compatible endpoint (OpenAI, Anthropic via proxy, local LLMs, etc.) |
| **Image/Voice Gen** | NONE in-app | App writes prompts + packages references. Human generates externally. |
| **Deployment** | Localhost (dev) → Cloud later (team) | One-click launcher (`start.bat`/`start.sh`) boots both servers + opens browser. |

### Dev Setup
- Vite dev server proxies `/api` → FastAPI on `:8000`
- Backend: `uvicorn backend.main:app --reload --port 8000`
- Frontend: `npm run dev` (Vite default port)
- Launcher wraps both + opens browser automatically

---

## 2. Repository Structure (Exact)

```
app/
├── backend/
│   ├── main.py                    # FastAPI entry point, CORS, lifespan
│   ├── api/                       # Route files, grouped per sprint
│   │   ├── __init__.py
│   │   ├── settings.py            # P01: endpoint/key/model config
│   │   ├── channels.py            # P02/P08: channel CRUD, kit wizard
│   │   ├── projects.py            # P02: project CRUD, auto-scan
│   │   ├── ideation.py            # P04: idea cards, surprise me, shelf
│   │   ├── titles.py              # P05: title generation, lock
│   │   ├── scripts.py             # P06/P07: script gen, import, lock
│   │   ├── characters.py          # P09: extraction, cast board
│   │   ├── variants.py            # P10: variant timelines
│   │   ├── environments.py        # P11: extraction, scout board
│   │   ├── world.py               # P12: world scan, world desk
│   │   ├── choreography.py        # P13: pose inference
│   │   ├── prompts.py             # P14/P15: sheet prompt assembly
│   │   ├── export.py              # P16: prompt export package
│   │   ├── checkpoint.py          # P17: import, quality gate
│   │   ├── library.py             # P18: cross-episode library
│   │   ├── beats.py               # P19/P20: chunk/beat splitting, per-beat prompts
│   │   ├── handoff.py             # P21: editor handoff export
│   │   ├── download_desk.py       # P22: real-world asset fetcher
│   │   ├── intelligence.py        # P23: channel intelligence
│   │   ├── shot_types.py          # P24: special shots & inserts
│   │   └── overlays.py            # P25: text-only beats & overlay spec
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Settings loader (reads data/settings.json)
│   │   ├── llm_client.py          # THE dispatcher: recipe loading, context packs,
│   │   │                          #   JSON validation, repair-retry, job_log, streaming
│   │   ├── id_generator.py        # App-owned ID minting (C##, E##, B###, etc.)
│   │   └── ripple.py              # Stale-flagging engine for upstream changes
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py          # SQLite connection manager
│   │   ├── migrations.py          # Schema creation & versioned migrations
│   │   └── rebuild.py             # Rebuild DB from files (repair button)
│   ├── models/                    # Pydantic schemas (request/response + DB validation)
│   │   ├── __init__.py
│   │   ├── channel.py
│   │   ├── project.py
│   │   ├── idea.py
│   │   ├── title.py
│   │   ├── script.py
│   │   ├── character.py
│   │   ├── variant.py
│   │   ├── environment.py
│   │   ├── world_record.py
│   │   ├── sheet.py
│   │   ├── beat.py
│   │   ├── library_asset.py
│   │   ├── lesson.py
│   │   └── job_log.py
│   ├── services/                  # One module per phase — business logic
│   │   ├── __init__.py
│   │   ├── p04_ideation.py
│   │   ├── p05_titles.py
│   │   ├── p06_script_gen.py
│   │   ├── p07_script_lock.py
│   │   ├── p08_style_kit.py
│   │   ├── p09_characters.py
│   │   ├── p10_variants.py
│   │   ├── p11_environments.py
│   │   ├── p12_world_scan.py
│   │   ├── p13_choreography.py
│   │   ├── p14_char_prompts.py
│   │   ├── p15_env_prompts.py
│   │   ├── p16_export.py
│   │   ├── p17_checkpoint.py
│   │   ├── p18_library.py
│   │   ├── p19_chunking.py
│   │   ├── p20_beat_prompts.py
│   │   ├── p21_handoff.py
│   │   ├── p22_download_desk.py
│   │   ├── p23_intelligence.py
│   │   ├── p24_shot_types.py
│   │   └── p25_overlays.py
│   ├── recipes/                   # Versioned prompt templates (plain text files)
│   │   ├── ideation_v1.txt
│   │   ├── title_gen_v1.txt
│   │   ├── script_outline_v1.txt
│   │   ├── script_draft_v1.txt
│   │   ├── script_punchup_v1.txt
│   │   ├── script_check_v1.txt
│   │   ├── character_extract_v1.txt
│   │   ├── variant_extract_v1.txt
│   │   ├── environment_extract_v1.txt
│   │   ├── world_scan_v1.txt
│   │   ├── pose_inference_v1.txt
│   │   ├── char_prompt_v1.txt
│   │   ├── env_prompt_v1.txt
│   │   ├── beat_split_v1.txt
│   │   ├── beat_prompt_v1.txt
│   │   ├── retention_analysis_v1.txt
│   │   ├── lesson_proposal_v1.txt
│   │   ├── overlay_text_v1.txt
│   │   └── style_descriptor_v1.txt
│   └── storage/
│       ├── __init__.py
│       └── fs_manager.py          # File-system operations (channels/, projects/, library/)
├── frontend/
│   ├── public/
│   │   └── fonts/                 # Press Start 2P, Pixelify Sans, Nunito (self-hosted)
│   ├── src/
│   │   ├── main.jsx               # React entry
│   │   ├── App.jsx                # Router + layout shell
│   │   ├── theme/
│   │   │   ├── tailwind.config.js # ALL Pixel Platformer tokens (colors, fonts, shadows)
│   │   │   ├── globals.css        # CSS variables, pixel-cloud bg, font-face declarations
│   │   │   └── animations.css     # coin-pop, block-pop, bounce, reduced-motion queries
│   │   ├── components/            # Reusable UI primitives (see §7)
│   │   │   ├── BlockButton.jsx
│   │   │   ├── IconChip.jsx
│   │   │   ├── StatusDot.jsx      # green/amber/red — semantic SACRED
│   │   │   ├── AssetTag.jsx       # id + layer badge (actor|insert)
│   │   │   ├── Card.jsx           # panel + hard shadow
│   │   │   ├── BoardGrid.jsx
│   │   │   ├── DiffView.jsx
│   │   │   ├── VersionPill.jsx
│   │   │   ├── SliderWithBadge.jsx # words↔duration bidirectional
│   │   │   ├── ToggleRow.jsx
│   │   │   ├── Toast.jsx          # block-pop animation
│   │   │   ├── EmptyState.jsx     # brick strip + pixel mascot
│   │   │   ├── Checklist.jsx      # 4+1 point checklist
│   │   │   ├── SuggestionsTray.jsx
│   │   │   ├── Sidebar.jsx        # Pipeline MAP (free navigation)
│   │   │   ├── TopBar.jsx         # Channel/project switcher, model status, user
│   │   │   ├── TransparencyDrawer.jsx  # Right drawer — scoped per beat
│   │   │   └── Modal.jsx
│   │   ├── screens/               # One per screen in the inventory (see §8)
│   │   │   ├── S01_Home.jsx
│   │   │   ├── S02_IdeaStudio.jsx
│   │   │   ├── S03_TitleStudio.jsx
│   │   │   ├── S04_ScriptStudio.jsx
│   │   │   ├── S05_CastBoard.jsx
│   │   │   ├── S06_VariantTimelines.jsx
│   │   │   ├── S07_ScoutBoard.jsx
│   │   │   ├── S08_WorldDesk.jsx
│   │   │   ├── S09_ChoreographyBoard.jsx
│   │   │   ├── S10_CardView.jsx
│   │   │   ├── S11_ExportDesk.jsx
│   │   │   ├── S12_CheckpointBoard.jsx
│   │   │   ├── S13_Library.jsx
│   │   │   ├── S14_BeatStudio.jsx
│   │   │   ├── S15_StoryboardHandoff.jsx
│   │   │   ├── S16_ChannelIntelligence.jsx
│   │   │   ├── S17_Settings.jsx
│   │   │   ├── G01_RippleReview.jsx
│   │   │   └── G02_TransparencyDrawer.jsx
│   │   └── hooks/                 # Custom React hooks
│   │       ├── useApi.js          # Fetch wrapper for /api calls
│   │       ├── useStream.js       # SSE/streaming for long-form jobs
│   │       ├── useJobPoll.js      # FIFO job queue polling
│   │       └── useRipple.js       # Stale-dot state management
│   └── vite.config.js             # Proxy /api → FastAPI :8000
├── data/                          # USER DATA — .gitignored
│   ├── settings.json              # endpoint, models (3 slots), key
│   ├── channels/
│   │   └── CH01/
│   │       ├── style_kit/         # Reference images, descriptor, avoid-list, tone samples
│   │       │   ├── refs/          # 2–4 uploaded style reference images
│   │       │   ├── descriptor.md  # AI-drafted + human-edited style text
│   │       │   ├── avoid_list.md  # 5 default rules + custom
│   │       │   ├── tone_samples.md
│   │       │   └── overlay_tokens.json # font, color, stroke, placement
│   │       └── library/           # Cross-episode reusable assets
│   └── projects/
│       └── CH01_EP01/             # ⚠️ P-01: stable path = {channel}_{EP##}; NEVER changes
│           │                      #   date + slug are display metadata in DB only
│           ├── README.txt         # Auto-generated layout explanation
│           ├── project.db         # SQLite working index (WAL mode enabled)
│           ├── 01_concept/        # Idea cards (versioned JSON + .md mirrors)
│           ├── 02_title/          # Title candidates + locked title
│           ├── 03_script/         # Script versions (drafts, locked, diffs)
│           ├── 04_cast/           # Character registry, mention map
│           ├── 05_world/          # Environments, variants, RW records, MT records
│           ├── 06_sheets/         # Prompt cards (.txt/.md), generated assets
│           │   ├── prompts/
│           │   ├── references/
│           │   ├── drafts/
│           │   ├── finals/
│           │   └── editor_notes/
│           ├── 07_beats/          # ⚠️ P-02: beat artifacts on disk (files-first)
│           │   ├── chunks.json    # chunked sentences
│           │   ├── beats.json     # beat records
│           │   ├── prompts/       # per-beat prompt .txt/.md mirrors
│           │   └── one_offs/      # one-off pose prompts
│           ├── 08_handoff/        # Versioned export packages
│           └── 09_intelligence/   # Stats, retention data, lessons
├── start.bat                      # Windows launcher
├── start.sh                       # Unix launcher
├── requirements.txt               # Python dependencies (pinned — see §16)
├── package.json                   # (root, if monorepo scripts needed)
├── .gitignore                     # data/ excluded
├── LOCKED_DECISIONS.md
├── HOW_IT_WORKS.md
├── UIUX.md
└── BUILD_PLAN.md
```

> [!IMPORTANT]
> **P-01 — Stable folder paths:** Project folder names are `{channel}_{EP##}` and **never change**.
> Renaming a project only updates `projects.slug` in the DB. Paths must never break.
>
> **P-02 — Beats folder:** `07_beats/` stores all beat artifacts on disk per the files-first
> principle (P02 lock). Without this, chunks/beats/one-off prompts have no file mirror.

---

## 3. Database Schema (SQLite — Complete)

Every table below must be created. Column types are SQLite-compatible. JSON columns store serialized JSON strings. All tables include `created_at` and `updated_at` timestamps.

### 3.1 `channels`
```sql
CREATE TABLE channels (
    id              TEXT PRIMARY KEY,          -- "CH01", "CH02", ...
    name            TEXT NOT NULL,
    kit_version     INTEGER NOT NULL DEFAULT 1,
    has_host        BOOLEAN NOT NULL DEFAULT 0,
    overlay_tokens  TEXT,                      -- JSON: {font, color, stroke, placement, punctuation_policy}
    tone_samples    TEXT,                      -- raw text (2-3 paragraphs)
    descriptor      TEXT,                      -- AI-drafted style text description
    avoid_list      TEXT,                      -- checklist text
    bg_default_hex  TEXT NOT NULL DEFAULT '#00FF00', -- chroma green
    env_resolution  TEXT NOT NULL DEFAULT '1920x1080',
    char_resolution TEXT NOT NULL DEFAULT '3:4',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.2 `projects`
```sql
CREATE TABLE projects (
    id              TEXT PRIMARY KEY,          -- "EP01", "EP02", ...
    channel_id      TEXT NOT NULL REFERENCES channels(id),
    slug            TEXT NOT NULL,             -- human-readable, renamable (display only; folder path is stable)
    folder_name     TEXT NOT NULL,             -- P-01: stable "{channel}_{EP##}" — NEVER changes after creation
    stage           TEXT NOT NULL DEFAULT 'idea', -- idea|title|script|analysis|sheets|beats|handoff|published
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.3 `idea_cards`
```sql
CREATE TABLE idea_cards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT REFERENCES projects(id),
    channel_id      TEXT NOT NULL REFERENCES channels(id), -- for shelf items without project
    version         INTEGER NOT NULL DEFAULT 1,
    content         TEXT NOT NULL,             -- JSON: {concept, hooks[], appeal, tags[], scale_estimate, rw_watchout}
    shelf_flag      BOOLEAN NOT NULL DEFAULT 0,
    is_current      BOOLEAN NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.4 `titles`
```sql
CREATE TABLE titles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    version         INTEGER NOT NULL DEFAULT 1,
    text            TEXT NOT NULL,
    angle           TEXT,                      -- one-line "why this works"
    style_tag       TEXT,
    char_count      INTEGER NOT NULL,
    locked          BOOLEAN NOT NULL DEFAULT 0,
    shipped         BOOLEAN NOT NULL DEFAULT 0, -- P-08: marked at handoff for P23
    is_alternate    BOOLEAN NOT NULL DEFAULT 0, -- A/B testing
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL               -- P-09: was missing per "all tables" rule
);
```

### 3.5 `scripts`
```sql
CREATE TABLE scripts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    version         INTEGER NOT NULL DEFAULT 1,
    text            TEXT NOT NULL,             -- full script text
    sections        TEXT,                      -- JSON: [{heading, summary, word_count, hook_placement}]
    word_count      INTEGER NOT NULL,
    duration_sec    REAL NOT NULL,             -- word_count / 150 * 60
    locked          BOOLEAN NOT NULL DEFAULT 0,
    locked_by       TEXT,
    locked_at       TEXT,
    source          TEXT NOT NULL DEFAULT 'ai', -- ai|imported|manual
    edit_diff       TEXT,                      -- JSON: diff from AI draft to final (for P23 learning)
    is_current      BOOLEAN NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);
```

### 3.6 `characters`

> [!IMPORTANT]
> **P-03 — RW ID collision fix:** A single `RW##` / `MT##` counter runs per project.
> A fetched person mints ONE `RW##` id. That id creates:
> 1. A `characters` row (render='fetched', `world_record_ref` pointing to the same id)
> 2. A `world_records` row (type='real_person', same id)
>
> This eliminates the collision risk of two separate RW sequences.

```sql
CREATE TABLE characters (
    id              TEXT PRIMARY KEY,          -- "C01" if drawn, "RW01" if fetched
    project_id      TEXT NOT NULL REFERENCES projects(id),
    kind            TEXT NOT NULL,             -- named|generic
    faction         TEXT,
    render          TEXT NOT NULL DEFAULT 'drawn', -- drawn|fetched
    names           TEXT NOT NULL,             -- JSON: primary name + alias list
    appearance      TEXT,                      -- JSON: {slots with source_notes}
    significance    TEXT NOT NULL DEFAULT 'supporting', -- core|supporting|minor
    presence        TEXT,                      -- JSON: [{section, chunks}]
    green_conflict  BOOLEAN NOT NULL DEFAULT 0,
    library_ref     TEXT,                      -- LIB### if reusing library asset
    world_record_ref TEXT,                     -- P-03: if fetched, points to world_records.id (same RW## id)
    stale           BOOLEAN NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.7 `variants`
```sql
CREATE TABLE variants (
    id              TEXT PRIMARY KEY,          -- "C01-V1", "C01-V2"
    character_id    TEXT NOT NULL REFERENCES characters(id),
    span            TEXT NOT NULL,             -- JSON: {from_chunk, to_chunk}
    delta           TEXT NOT NULL,             -- JSON: what changed vs master
    evidence        TEXT,
    confidence      REAL NOT NULL DEFAULT 0.8,
    rejected_changes TEXT,                     -- JSON: [{considered, verdict}]
    stale           BOOLEAN NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL               -- P-09: was missing per "all tables" rule
);
```

### 3.8 `mentions`
```sql
CREATE TABLE mentions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    section         TEXT,
    chunk           TEXT,
    mention_text    TEXT NOT NULL,
    resolved_to     TEXT,                      -- character ID
    confidence      REAL NOT NULL DEFAULT 0.8,
    context         TEXT,
    created_at      TEXT NOT NULL
);
```

### 3.9 `environments`
```sql
CREATE TABLE environments (
    id              TEXT PRIMARY KEY,          -- "E01", "E02"
    project_id      TEXT NOT NULL REFERENCES projects(id),
    name            TEXT NOT NULL,
    elements        TEXT NOT NULL,             -- JSON: 3-4 structured elements
    green_conflict  BOOLEAN NOT NULL DEFAULT 0,
    presence        TEXT,                      -- JSON: [{section, chunks}]
    library_ref     TEXT,
    stale           BOOLEAN NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.10 `env_variations`
```sql
CREATE TABLE env_variations (
    id              TEXT PRIMARY KEY,          -- "E01-1", "E01-2"
    environment_id  TEXT NOT NULL REFERENCES environments(id),
    state           TEXT NOT NULL,             -- "dawn", "battle", "aftermath"
    span            TEXT NOT NULL,             -- JSON: {from_chunk, to_chunk}
    evidence        TEXT,
    stale           BOOLEAN NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
```

### 3.11 `world_records`
```sql
CREATE TABLE world_records (
    id              TEXT PRIMARY KEY,          -- "RW01" for real-world, "MT01" for map triggers
    project_id      TEXT NOT NULL REFERENCES projects(id),
    type            TEXT NOT NULL,             -- brand_logo|trademark|real_person|meme|map_trigger
    text            TEXT NOT NULL,             -- entity name/description
    script_context  TEXT,                      -- where in script it appears
    usage_intent    TEXT NOT NULL DEFAULT 'on_screen_insert', -- on_screen_insert|background_prop|text_only
    search_query    TEXT,                      -- 1-4 words for browser search
    era_hint        TEXT,                      -- "1980s", "medieval", etc.
    mode            TEXT,                      -- fetched_template|in_style_parody (memes only)
    layer           TEXT NOT NULL DEFAULT 'insert', -- actor|insert
    map_template    TEXT,                      -- flag_fill|region_highlight|paper|split (MT only)
    status          TEXT NOT NULL DEFAULT 'pending', -- pending|approved|dismissed|fetched|generated
    provenance      TEXT,                      -- fetched_final|generated_in_style
    role_tag        TEXT,                      -- final_insert|generation_reference
    stale           BOOLEAN NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.12 `sheets`
```sql
CREATE TABLE sheets (
    id              TEXT PRIMARY KEY,          -- "C01-S1", "E02-S1"
    parent_id       TEXT NOT NULL,             -- character_id or environment_id
    parent_type     TEXT NOT NULL,             -- character|environment
    kind            TEXT NOT NULL,             -- master|variant|extension|action|reaction|environment
    grid            TEXT,                      -- "2x3", "3x2", etc.
    poses           TEXT,                      -- JSON: [{id, type, name, evidence, priority}] (characters)
    boxes           TEXT,                      -- JSON: [{id, variation_id, position}] (environments)
    box_map         TEXT,                      -- JSON: position↔variation_id mapping (metadata only)
    status          TEXT NOT NULL DEFAULT 'draft_prompted',
                                               -- draft_prompted|draft_imported|approved|final
    background_color TEXT,                     -- actual hex used
    kit_version     INTEGER,
    seed            TEXT,                      -- captured at import
    model           TEXT,                      -- captured at import
    prompt_text     TEXT NOT NULL,             -- the assembled prompt card
    references_list TEXT,                      -- JSON: [file paths to attach]
    editor_notes    TEXT,                      -- compositing notes (NEVER in prompt)
    reject_reason   TEXT,                      -- if rejected: style_drift|wrong_bg|proportions|extra_elements|other
    stale           BOOLEAN NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.13 `beats`
```sql
CREATE TABLE beats (
    id              TEXT PRIMARY KEY,          -- "B001", "B002", ...
    project_id      TEXT NOT NULL REFERENCES projects(id),
    chunk_id        TEXT NOT NULL,             -- "K01", "K02" — the parent sentence
    chunk_text      TEXT NOT NULL,             -- full sentence text
    text            TEXT NOT NULL,             -- beat text (6-14 words)
    word_count      INTEGER NOT NULL,
    duration_sec    REAL NOT NULL,             -- word_count / 150 * 60
    text_only       BOOLEAN NOT NULL DEFAULT 0,
    svo             TEXT,                      -- JSON: {subject, verb, object} — hidden by default
    overlay_text    TEXT,                      -- shortened readable fragment (text-only beats)
    overlay_spec    TEXT,                      -- JSON: {text, style_tokens, placement, duration, readability_lint}
    sort_order      INTEGER NOT NULL,
    stale           BOOLEAN NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.14 `beat_elements`
```sql
CREATE TABLE beat_elements (
    id              TEXT PRIMARY KEY,          -- "B001-I1", "B001-I2"
    beat_id         TEXT NOT NULL REFERENCES beats(id),
    asset_ref       TEXT NOT NULL,             -- C01-S1 pose 3, E02-S1 box 2, RW01, etc.
    layer           TEXT NOT NULL,             -- actor|insert
    framing         TEXT,                      -- "medium shot", "close-up", etc.
    prompt_text     TEXT,                      -- NULL if reusing existing pose; text if one-off
    refs_to_attach  TEXT,                      -- JSON: [file paths]
    editor_note     TEXT,                      -- compositing guidance for human editor
    improv_note     TEXT,                      -- one-off description (if applicable)
    is_one_off      BOOLEAN NOT NULL DEFAULT 0,
    sort_order      INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL               -- P-09: was missing per "all tables" rule
);
```

### 3.15 `library_assets`
```sql
CREATE TABLE library_assets (
    id              TEXT PRIMARY KEY,          -- "LIB001", "LIB002"
    channel_id      TEXT NOT NULL REFERENCES channels(id),
    kind            TEXT NOT NULL,             -- character|environment|host|generic|extension
    tags            TEXT NOT NULL,             -- JSON: [searchable tags]
    context         TEXT,                      -- JSON: {source_episode, situation_tags[], use_case_line}
    sheet_ref       TEXT,                      -- reference to original sheet
    kit_version     INTEGER NOT NULL,
    usage_count     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active', -- active|retired
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.16 `lessons`
```sql
CREATE TABLE lessons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id      TEXT NOT NULL REFERENCES channels(id),
    observation     TEXT NOT NULL,
    evidence        TEXT NOT NULL,
    tweak           TEXT NOT NULL,             -- proposed recipe change
    target_recipe   TEXT NOT NULL,             -- which recipe file to modify
    confidence      REAL NOT NULL DEFAULT 0.5,
    status          TEXT NOT NULL DEFAULT 'proposed', -- proposed|active|retired
    diff_text       TEXT,                      -- before/after diff for approval UI
    approved_by     TEXT,
    approved_at     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### 3.17 `job_log`
```sql
CREATE TABLE job_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT,
    channel_id      TEXT,
    job_type        TEXT NOT NULL,             -- ideation|title_gen|script_outline|script_draft|...
    inputs          TEXT NOT NULL,             -- JSON: what was sent
    context_pack    TEXT,                      -- JSON: what context was assembled
    model           TEXT NOT NULL,
    temperature     REAL NOT NULL,
    raw_output      TEXT NOT NULL,
    parsed_output   TEXT,                      -- JSON: validated result
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    duration_ms     INTEGER,
    error           TEXT,                      -- NULL if success
    created_at      TEXT NOT NULL
);
```

### 3.18 `video_stats` *(P-04: was missing — P23 raw metrics had no home)*
```sql
CREATE TABLE video_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    channel_id      TEXT NOT NULL REFERENCES channels(id),
    title_shipped   TEXT,                      -- the title that was actually published
    description     TEXT,
    tags            TEXT,                      -- JSON: [tag strings]
    thumbnail_path  TEXT,                      -- relative path to uploaded thumbnail
    views           INTEGER,
    impressions     INTEGER,
    ctr             REAL,                      -- click-through rate
    avd_seconds     REAL,                      -- average view duration in seconds
    retention_curve TEXT,                      -- JSON: [{timestamp_sec, retention_pct}]
    dropoff_points  TEXT,                      -- JSON: [{timestamp_sec, severity, mapped_beat_id}]
    published_at    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

---

## 4. LLM Orchestration Core (`core/llm_client.py`)

This is the heart of the backend. Every AI call in the entire app goes through this single module.

### 4.1 Architecture

```
Recipe File (.txt) + Context Pack (assembled per job) + Schema (Pydantic)
    ↓
llm_client.dispatch(job_type, context, schema, stream=False)
    ↓
openai.ChatCompletion.create(
    base_url=settings.endpoint,
    api_key=settings.key,
    model=settings.models[tier],     # Light|Medium|High
    temperature=tier_default,
    response_format={"type": "json_object"}  # if available
)
    ↓
Validate output against Pydantic schema
    ↓
If invalid → repair-retry ONCE (re-prompt with error + raw output)
    ↓
If still invalid → error badge + manual override available
    ↓
Log everything to job_log table
```

### 4.2 Model Tiers
Users configure 3 model slots in Settings:
- **Light** — cheap, fast (e.g., GPT-4o-mini, Claude Haiku)
- **Medium** — balanced (e.g., GPT-4o, Claude Sonnet)
- **High** — best quality (e.g., GPT-4, Claude Opus)

Plus a "Use one model for everything" checkbox that collapses to a single field.

### 4.3 Job Map (which tier + temperature per job type)

| Job | Tier | Temp | Stream? |
|-----|------|------|---------|
| Ideation (P04) | High | ~0.9 | Yes |
| Surprise Me (P04) | High | ~0.9 | No |
| Title Gen (P05) | High | ~0.9 | No |
| Script Outline (P06 Pass 1) | Medium | ~0.7 | No |
| Script Draft (P06 Pass 2) | High | ~0.8 | **Yes** |
| Script Punch-up (P06 Pass 3) | High | ~0.7 | No |
| Script Consistency Check (P06 Pass 4) | Medium | ~0.2 | No |
| Style Descriptor from images (P08) | High | ~0.5 | No |
| Character Extraction (P09) | Medium | ~0.2 | No |
| Variant Extraction (P10) | Medium | ~0.2 | No |
| Environment Extraction (P11) | Medium | ~0.2 | No |
| World Scan (P12) | Medium | ~0.2 | No |
| Pose Inference (P13) | Medium | ~0.4 | No |
| Character Prompt Assembly (P14) | High | ~0.5 | No |
| Environment Prompt Assembly (P15) | High | ~0.5 | No |
| Beat Splitting (P19) | Medium | ~0.2 | No |
| Per-Beat Prompts (P20) | High | ~0.5 | No |
| Retention Analysis (P23) | High | ~0.5 | No |
| Lesson Proposal (P23) | High | ~0.5 | No |
| Overlay Text (P25) | Medium | ~0.5 | No |

### 4.4 Context Packs (what each job receives)

Every job receives a **context pack** — a structured bundle of relevant data. Here are the exact contents:

| Job | Context Pack Contents |
|-----|----------------------|
| Ideation | Channel tone, past video titles (dedupe), active P23 lessons |
| Title Gen | Idea card, channel tone, past titles, active lessons |
| Script Outline | Idea card, title, channel tone, target word count |
| Script Draft | Idea card, title, tone, approved outline, target word count, tone samples |
| Script Punch-up | Current script, selected section, user's free-text note |
| Consistency Check | Full script |
| Character Extract | Full locked script. If >4000 words OR cast >20: auto-shard |
| Variant Extract | Full script + P09 character registry |
| Environment Extract | Full script + character registry + P09 world annotations + library index |
| World Scan | Full script + P09-P11 world annotations + P09 fetched-person seeds |
| Pose Inference | Full script + character variant record |
| Char Prompt Assembly | Style descriptor + avoid list + character record + poses + variant delta + refs list |
| Env Prompt Assembly | Style descriptor + avoid list + environment record + variation boxes |
| Beat Splitting | Chunk text + 2-3 neighboring sentences |
| Per-Beat Prompts | Full script + approved-sheet registry + established refs rollup + last 2-3 beat prompts + variant timelines + mention map + RW/MT records + descriptor + avoid list + active lessons |
| Retention Analysis | Beat/chunk at drop-off timestamp + surrounding context |
| Overlay Text | Beat line + channel overlay tokens |

### 4.5 Streaming
For streamed jobs (script draft, ideation), use Server-Sent Events (SSE):
- Backend: `StreamingResponse` with `text/event-stream` content type
- Frontend: `useStream` hook consuming `EventSource`

### 4.6 Defensive Sharding
For extraction passes (P09/P11/P12): if script >4,000 words or pre-scan estimates >20 entities, automatically split the script into overlapping segments, run each as a separate call, then merge/deduplicate results.

---

## 5. ID System

### 5.1 Three Registers

| Register | Format | Where Used |
|----------|--------|------------|
| **Internal Short** | `C01`, `E02`, `B047`, `RW01`, `MT01`, `LIB003` | Database, all backend logic, all LLM context |
| **Semantic** | Name-first (e.g., "Napoleon (C03)") | AI-facing context packs, mention maps |
| **Export-Prefixed** | `CH01_EP02_C01`, `CH01_EP02_E02` | File exports and handoff ONLY — NEVER in LLM context |

### 5.2 ID Minting Rules
- IDs are minted **by the app only**, sequentially per project
- **P-03: `RW##` and `MT##` share ONE counter per project** — no collision between characters and world_records
- `C##` — characters (drawn)
- `RW##` — real-world / fetched entities (used in BOTH `characters` and `world_records` tables for fetched persons)
- `E##` — environments
- `B###` — beats (three digits)
- `K##` — chunks (sentences)
- `V#` — variants (suffixed: `C01-V1`)
- `S#` — sheets (suffixed: `C01-S1`, `E02-S1`)
- `I#` — beat elements (suffixed: `B001-I1`)
- `MT##` — map triggers (shares counter with `RW##`)
- `LIB###` — library assets
- Export prefix = `{channel_id}_{project_id}_` — applied at handoff (P21) only

---

## 6. Ripple System (`core/ripple.py`)

When an upstream artifact changes, downstream artifacts are **flagged stale** (amber dot) — never deleted, never silently regenerated.

### 6.1 Dependency Graph
```
Idea Card → Title → Script → [Characters, Environments, World Records]
                                    ↓              ↓              ↓
                              Variants        Variations      (feeds P22/P24)
                                    ↓              ↓
                              Pose Lists      Env Sheets
                                    ↓              ↓
                              Char Sheets     ────────┐
                                    ↓                  ↓
                              [Checkpoint — Approved Sheets]
                                    ↓
                              Beats → Beat Elements → Handoff
                                                  ↑
                                          Library Assets

Style Kit ──→ ALL prompt cards + sheets (via kit_version comparison)
Lessons ──→ context packs for P04/P05/P06/P20
```

### 6.2 Ripple Review Screen (G01)
- Left panel: the change diff (what changed upstream)
- Right panel: list of all affected downstream items with checkboxes
- Per item: **Keep** / **Regenerate** / **Decide Later**
- Regenerate = new version (old preserved)
- "Decide Later" items stay amber-dotted indefinitely
- Batched: ripple review triggered on leave or explicit apply, not popup spam

### 6.3 Per-Beat Regenerate
Every beat card always has its own "Regenerate" button independently of any ripple.

---

## 7. Component Library (Frontend)

Every component must follow the Pixel Platformer design system. Here are the exact specifications:

### 7.1 Design Tokens (CSS Variables / Tailwind Config)

```css
:root {
  /* Colors */
  --color-sky: #5C94FC;
  --color-panel: #FFF8E7;
  --color-ink: #232323;
  --color-brick: #8B5A2B;
  --color-primary: #E7402D;       /* Mario-red — primary actions */
  --color-success: #2FA84F;       /* pipe-green — approved/final/saved */
  --color-warn: #F7B32B;          /* coin-yellow — stale/advisory */
  --color-danger: #C0392B;        /* rejected/error */
  --color-info: #3E7BFA;          /* cloud-blue — links/info/queued */

  /* Fonts */
  --font-display: 'Press Start 2P', monospace;    /* logo, big numbers, tiny labels ONLY */
  --font-heading: 'Pixelify Sans', sans-serif;    /* headings, badges */
  --font-body: 'Nunito', sans-serif;              /* everything else */

  /* Shadows */
  --shadow-block: 4px 4px 0 rgba(35, 35, 35, 0.2);
  --shadow-hover: 5px 5px 0 rgba(35, 35, 35, 0.25);

  /* Borders */
  --border-standard: 2px solid var(--color-ink);
  --border-brick: 2px solid var(--color-brick);
  --radius: 6px;
}
```

### 7.2 Critical Design Rules
1. **Pixel fonts ≤ 20%** of any screen. Everything read for >5 seconds is Nunito.
2. **Texture (pixel clouds) on background ONLY** — panels are FLAT cream.
3. **Brick pattern** only on decorative strips (login, sidebar footer, empty states).
4. **Shadows are hard** — no blur, always offset.
5. **Buttons lift on hover** (-1px, -1px + shadow grows), sink on press.
6. **Semantic colors are SACRED**: green = approved/success, amber/yellow = stale/warning, red = rejected/error. These meanings never change across any screen.
7. **WCAG AA contrast** minimum everywhere.
8. **`prefers-reduced-motion`** must be honored — all animations have fallbacks.

### 7.3 Animations
- `coin-pop`: success feedback (save, approve, lock)
- `block-pop`: toast notifications
- `bounce`: subtle hover lift on interactive elements
- Optional 8-bit SFX toggle (OFF by default) — stored in settings

### 7.4 Component Specs

| Component | Purpose | Key Props |
|-----------|---------|-----------|
| `BlockButton` | Primary action button with lift/sink animation | `variant` (primary/secondary/danger), `icon`, `loading` |
| `IconChip` | Small tag with icon (categories, types) | `icon`, `label`, `color` |
| `StatusDot` | Green/amber/red indicator | `status` (approved/stale/rejected) |
| `AssetTag` | Asset ID + layer badge | `assetId`, `layer` (actor/insert) |
| `Card` | Panel with hard shadow, the universal container | `title`, `actions`, `status` |
| `BoardGrid` | Responsive card grid layout | `columns`, `gap` |
| `DiffView` | Side-by-side or inline diff display | `before`, `after`, `mode` |
| `VersionPill` | Version number badge with revert action | `version`, `onRevert` |
| `SliderWithBadge` | Bidirectional words↔duration | `words`, `onWordsChange`, `wpm` (default 150) |
| `ToggleRow` | Labeled toggle switch | `label`, `value`, `onChange` |
| `Toast` | Block-pop notification | `message`, `type` (success/warning/error) |
| `EmptyState` | Brick strip + pixel mascot for empty screens | `message`, `action` |
| `Checklist` | 4+1 point approval checklist | `items[]`, `onCheck` |
| `SuggestionsTray` | Collapsible tray for AI suggestions | `items[]`, `onAccept`, `onDismiss` |
| `Sidebar` | Pipeline MAP with free navigation | `nodes[]`, `activeNode`, `staleCounts` |
| `TopBar` | Channel/project switchers, model status | `channel`, `project`, `jobQueue` |
| `TransparencyDrawer` | Right drawer — what did the AI see/say | `jobLog`, `scope` |
| `Modal` | Standard modal with overlay | `title`, `children`, `onClose` |

---

## 8. Screen-by-Screen Specifications

### S01 — Home
- **3 entry doors**: "Start with an Idea" → S02, "Start with a Title" → S03, "Start with a Script" → S04
- **Project grid**: card per project with slug, stage badge (StatusDot), last-updated timestamp
- **Actions**: Create channel, create project, open project, rename, duplicate/fork, delete
- **Auto-scan**: on launch, scan `data/projects/` directory and reconcile with DB
- **Channel switcher** in TopBar

### S02 — Idea Studio
- **Input**: one generous textarea (one word to a paragraph)
- **Buttons**: "Refine & Expand" (AI pass), "Surprise Me" (6 fresh concepts)
- **Results**: card grid of idea cards, each showing concept, hooks, appeal, tags, scale estimate, RW watchout
- **Detail view**: full stats + free-form "refine to my liking" loop (text input + regenerate)
- **Shelf tab**: per-channel list of saved-for-later ideas, promotable to project
- **Fast-lane**: if input is rich enough, offer "Skip refinement, straight to titles"
- **Skip doors**: always visible — "I have a title" → S03, "I have a script" → S04
- **Versions**: every refinement creates a new version (VersionPill)

### S03 — Title Studio
- **Generation**: 10 candidates (adjustable 5–20), each as a card with text, angle, style tag, char count
- **Selection UX**: shortlist (checkbox), edit inline, remix, regenerate-selected only, reroll all
- **Own-title door**: text input to type your own, same lock mechanics
- **Platform check**: live char count, >70 chars → amber warning + AI-suggested shortened variant
- **Lock**: select one primary, optional alternates for A/B; lock = version snapshot
- **Ripple**: stale dot if upstream idea card changes

### S04 — Script Studio (P06 + P07 unified)
- **Arrival**: from title (AI draft) OR paste text / drop .txt/.md (imported)
- **Slider**: bidirectional words (500–5,000, 50-step) ↔ duration (@ 150 wpm). Type duration → slider follows.
- **Pass 1 — Outline**: section headings + summaries + hook + turn markers. Reorderable, editable, skippable.
- **Pass 2 — Full Draft**: streamed into editor. Per-section weighted targets, total ±10%.
- **Pass 3 — Punch-up**: select section → free-text note → AI improves that section only. Repeatable.
- **Pass 4 — Consistency Check**: one-click. Checks name inconsistencies, timeline gaps, tone drift, repetition, narration flags (tongue-twisters, >30-word sentences, phonetic collisions), hook strength.
- **Editor features**: hook highlight (first ~75 words), live word count + duration footer, pacing strip (per-section rhythm dots), word-count breakdown sidebar (per-section counts + % + rebalance button)
- **Imported scripts**: get the same tools (passes 3+4, breakdown, duration math) + optional auto-sectioning pass
- **Lock**: version snapshot, records stats (words, duration, sections, who/when), unlocks analysis, records draft-to-final edit diff for P23 learning
- **Pre-lock sanity card**: non-blocking 3-line glance (duration vs target, word count, sections, check status)
- **Unlock**: editing IS unlocking → new version → ripple flags downstream
- **Lock & Continue**: smart next-step button (→ analysis / style-kit / pipeline map)

### S05 — Cast Board
- **Source**: auto-populated from P09 character extraction (on locked script)
- **Card per character**: name, kind (named/generic), faction, significance (core/supporting/minor), render (drawn/fetched toggle), presence sections, green-conflict flag, library match indicator
- **Significance pick**: core = permanent. Supporting/minor = user toggles: full character / bundle to generic crowd / drop to text-only
- **Drawn ↔ Fetched toggle**: free flip at this stage (zero cost). Default rule: pre-photography era → drawn, photography era recognizable → fetched
- **Resolution inspector**: collapsed by default, shows mention map rows with confidence coloring (low-confidence = amber)
- **Actions**: edit, promote/demote significance, split generic, merge, add manually, one-click reuse from library
- **Scale check**: extracted cast count vs P04 idea-card estimate → mismatch flag

### S06 — Variant Timelines
- **Horizontal strips**: one per character, showing variant spans across the script
- **Each variant**: ID, span (from–to chunk), delta-from-master description, evidence, confidence
- **Visual**: dashed borders on low-evidence spans
- **Labels**: "+1 sheet" per variant
- **Actions**: merge spans, split spans, edit deltas, adjust boundaries, demote rare variants to one-off poses
- **Cost control**: variants spanning ≤2 beats → auto-suggest demotion to one-off
- **Contradiction detector**: spans checked against mention map presence; mismatches flagged

### S07 — Scout Board
- **Card per environment**: name, 3–4 structured elements, variation chips (trimmable)
- **Variations**: same location + different state (season/time/scene-state)
- **Visual**: dashed shading for low-evidence variations
- **Actions**: edit elements, merge over-splits, split, dismiss, hand-add
- **Green-conflict**: proactive white-background recommendation on nature/green environments
- **Cost controls**: env count vs idea-card estimate flagged; ≤2-beat environments default to minimal single-box sheets
- **Library reuse**: generic places check channel library first, one-click reuse
- **Cross-audit**: character-presence vs environment-span contradiction check

### S08 — World Desk
- **Cards grouped by family**: brands/logos, memes, real people, map triggers
- **Per card**: type badge, text, script context, usage intent (on_screen_insert/background_prop/text_only), search query (1–4 words), era hint
- **Meme cards**: mode toggle (fetched_template → insert layer, OR in_style_parody → actor layer)
- **Map trigger cards**: template preview (flag_fill/region_highlight/paper/split)
- **Actions**: approve, dismiss, edit, choose meme mode, set usage intent, hand-add
- **Feeds**: approved → P22 (download desk) for fetching, MT → P24 for special shots

### S09 — Choreography Board
- **Per drawn variant**: pose list with type badges (physical/expression), evidence, priority (script/mandatory)
- **Lean default**: <6 poses, script+mandatory only
- **Suggestions tray**: AI-proposed buffer poses, opt-in add only
- **Mandatory**: neutral expression per variant set; expression poses required
- **Packing**: >6 poses → type-grouped sheets (action sheet / reaction sheet)
- **Sheet counter**: live "+1 sheet" count
- **Actions**: add/cut/move poses across sheets
- **Library extensions**: missing poses on reused characters → extension sheet chained to library sheet, saved to library BY DEFAULT with context metadata

### S10 — Card View (Prompt Cards)
- **8-slot anatomy** (characters): [1] STYLE descriptor verbatim, [2] IDENTITY (master full block), [3] DELTA (variant only), [4] POSES (per-pose lines — character name in every line, ZERO pronouns), [5] ISOLATION, [6] BACKGROUND (green hex / white if conflict), [7] AVOID verbatim, [8] PARAMS (3:4, grid, draft-first)
- **8-slot anatomy** (environments): [1] STYLE, [2] IDENTITY (combined elements), [3] BOXES (visual separation), [4] SCALE (relative to Canonical H), [5] ISOLATION, [6] BACKGROUND, [7] AVOID, [8] PARAMS (16:9, draft-first)
- **Lint badges**: pre-export check — all 8 slots + references + params present, else error badge
- **Slot-stable regen**: only changed slots rewrite; diff preview before applying
- **Copy prompt + refs**: one-click to clipboard for external generation
- **Chaining**: master sheets have full identity; variant/extension sheets have delta + master image in refs
- **No-pronouns rule**: CRITICAL — every pose line repeats the character's name

### S11 — Export & Download Desk
- **Export Package builder**: generates `prompts/` + `references/` + `manifest.json` + `README.txt` + `editor_notes/` folder, zippable
- **Generation Checklist**: counts by type/ratio
- **Download Desk** (P22): per real-world record row with "Search in Browser" button (opens browser with pre-filled query), status (pending/fetched), drop zone for downloaded files
- **Role tags**: `final_insert` (use as-is) or `generation_reference` (feed to image gen to redraw in style)
- **Import zone**: drop folder/zip, auto-match via manifest/filename convention

### S12 — Checkpoint Board
- **Thumbnail grid**: all sheets with status chips (draft_imported/approved/final)
- **Triple view on click**: draft side-by-side with style-kit refs and master sheet
- **4+1 checklist**: (1) style consistency, (2) background correct, (3) proportions/attire, (4) isolation clean, (+1 for maps) geometry matches reference
- **Auto background check**: local corner-pixel sampling verifies actual bg ≈ expected hex — zero AI, instant amber on mismatch
- **Reject**: carries reason taxonomy (style_drift / wrong_bg / proportions / extra_elements / other) → loops back to card tweak → re-export
- **Bulk triage**: multi-select + approve/reject
- **Gate**: only `approved` or `final` sheets can be used by beats
- **Metadata capture**: seed + model filled at import; required for `final`, optional at `draft`

### S13 — Library
- **Browse/search**: by tags, kind, context (source episode, situation)
- **Per entry**: usage count, kit version, status (active/retired)
- **Retire-not-delete**: soft removal, never hard delete
- **Duplicate guard**: similarity check on save
- **Savings counter**: "This episode reused X sheets from library, saving Y generations"
- **Kit-version safety**: on reuse, compare kit versions. Mismatch → "Reuse as-is" OR "Regenerate under current kit" (draft-first)

### S14 — Beat Studio
- **Chunk-grouped beats**: each chunk (sentence) contains its beats
- **Per beat row**: VO line text, element chips (with layer tags: actor/insert), framing, duration, badges
- **Pacing visualizer**: word-count bars per beat/chunk
- **Element chips**: reuse-first (match existing approved poses/boxes). One-off prompts only for gaps.
- **One-off tray**: accept / promote to library / discard
- **SVO reveal toggle**: hidden by default, shows subject-verb-object per beat
- **Text-only toggles**: AI pre-flags candidates, confirmed here
- **Per-beat regenerate button**: always available independently of ripple

### S15 — Storyboard & Handoff
- **In-app storyboard**: scrollable preview — text + pose thumbnails per beat, before export
- **Retention flags overlay**: (from P23) drop-off pins on specific beats
- **Versioned export**: `HANDOFF_[EP]_v1/` containing:
  - `alignment_table.md` and `.txt` (B### | VO line | asset tags + layer | framing | duration | text-only flag)
  - `manifest.json`
  - `assets/` (all final images)
  - `one_off_prompts/` (prompts for one-off poses)
  - `inserts/` (real-world assets)
  - `editor_notes/` (compositing: standing planes, horizons, box maps, keying colors)
  - `text_only_beats.md` (overlay specs)
  - `README.txt`
- **Preflight lint**: all referenced assets have final files, one-offs generated, RW fetched, MT mapped. Advisory by default, strict mode optional.
- **Re-export after changes**: comes with a change-summary diff vs previous version

### S16 — Channel Intelligence
- **Metrics entry**: manual form or CSV paste — title shipped, description, tags, views, impressions, AVD/retention curve, drop-off timestamps, thumbnail upload
- **Retention mapping**: drop-off timestamp × 150 wpm = exact word/beat
- **Retention sparklines**: pinned to exact beats in the storyboard view
- **Pattern mining**: cross-video analysis of hooks, pacing, topics vs CTR/AVD
- **Lessons list**: structured records (observation + evidence + proposed tweak + target recipe + confidence + status)
- **Diff approval viewer**: AI proposes recipe tweaks, shown as before/after diff. Human approves → status becomes `active`. Nothing auto-applies. Revertible.
- **Context injection**: active lessons inject into relevant context packs (P04/P05/P06/P20). Transparency panel shows which lessons shaped a generation.

### S17 — Settings
- **Models**: 3 slots (Light/Medium/High) with text fields for model name + "Use one model" checkbox
- **Endpoint**: URL field for OpenAI-compatible endpoint
- **API Key**: paste field (masked display), "Test Connection" button
- **Kit wizard link**: to channel style kit setup
- **Overlay tokens**: font/color/stroke/placement config for text-only beats
- **Shot-type registry**: built-in types (4 map templates + meme parody) + future custom types
- **Thresholds**: configurable defaults (beat word range, pose limits, etc.)
- **SFX toggle**: 8-bit sound effects (OFF by default)
- **Theme toggles**: future theming options

### G01 — Ripple Review
- **Split view**: left = change diff (what changed upstream), right = affected downstream items
- **Per item**: checkboxes + action buttons (Keep / Regenerate / Decide Later)
- **Regenerate**: creates new version, old preserved
- **Decide Later**: item stays amber-dotted indefinitely
- **Batched**: triggered on leave or explicit apply, NOT popup spam

### G02 — Transparency Drawer
- **Right drawer**: slides in from right edge
- **Scoped per beat/job**: shows what the AI saw (context pack summary) and said (raw output summary)
- **Hidden from teammates by default** (dev-visible via role)
- **Auto-reset**: scope changes when navigating to different beat

---

## 9. Layout Architecture

```
┌──────────────────────────────────────────────────────────┐
│  TopBar: [Channel ▾] [Project ▾] [Model/Queue] [👤 User] │
├────────┬─────────────────────────────────┬───────────────┤
│        │                                 │               │
│ Sidebar│       Main Canvas               │ Transparency  │
│ (MAP)  │   (current screen/board)        │   Drawer      │
│        │                                 │  (contextual) │
│ - Idea │                                 │               │
│ - Title│                                 │               │
│ - Script                                 │               │
│ - Cast │                                 │               │
│ - Variants                               │               │
│ - Locations                              │               │
│ - World│                                 │               │
│ - Sheets                                 │               │
│ - Export                                 │               │
│ - Check│                                 │               │
│ - Library                                │               │
│ - Beats│                                 │               │
│ - Handoff                                │               │
│ - Stats│                                 │               │
│        │                                 │               │
│ [Changes Inbox]                          │               │
│ [Settings ⚙]                            │               │
├────────┴─────────────────────────────────┴───────────────┤
│  Status Bar (optional)                                   │
└──────────────────────────────────────────────────────────┘
```

- **Sidebar**: every node always clickable (free navigation, no disabled steps). Empty nodes say "not started". Amber dots show stale-item counts. Changes inbox lives at bottom.
- **Main Canvas**: boards are card grids; data-heavy views use clean Nunito tables.
- **Transparency Drawer**: scoped per beat, auto-reset, hidden from teammates by role.

---

## 10. API Endpoint Catalog

All endpoints are under `/api/v1/`. Standard REST conventions. JSON request/response bodies.

### 10.1 Settings
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/settings` | Get current settings |
| PUT | `/settings` | Update settings |
| POST | `/settings/test-connection` | Test LLM endpoint connectivity |

### 10.2 Channels
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/channels` | List all channels |
| POST | `/channels` | Create channel |
| GET | `/channels/{id}` | Get channel details |
| PUT | `/channels/{id}` | Update channel |
| POST | `/channels/{id}/kit/descriptor` | Generate style descriptor from uploaded images |
| PUT | `/channels/{id}/kit` | Update style kit (bumps kit_version) |
| POST | `/channels/{id}/kit/test-prompt` | Generate a test prompt to validate kit |
| POST | `/channels/{id}/host` | P-07: Create host record + LIB asset + channel-level sheets |
| PUT | `/channels/{id}/host` | P-07: Update host record |
| POST | `/channels/{id}/host/choreography` | P-07: Run choreography/prompt at channel level for host |

### 10.3 Projects
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/channels/{ch_id}/projects` | List projects in channel |
| POST | `/channels/{ch_id}/projects` | Create project |
| GET | `/projects/{id}` | Get project details |
| PUT | `/projects/{id}` | Update project (rename slug — folder stays stable per P-01) |
| POST | `/projects/{id}/duplicate` | Duplicate/fork project |
| DELETE | `/projects/{id}` | Delete project |
| POST | `/projects/scan` | Auto-scan projects directory |
| POST | `/projects/{id}/db/rebuild` | Rebuild DB from files |
| POST | `/projects/{id}/backup` | P-05: Download whole project (files + DB) as zip |
| POST | `/projects/import` | P-05: Import project from zip/folder |

### 10.4 Ideation (P04)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/ideas/generate` | Generate idea card (streamed) |
| POST | `/channels/{ch_id}/ideas/surprise` | Generate 6 surprise concepts |
| GET | `/projects/{id}/ideas` | List idea cards (with versions) |
| PUT | `/ideas/{idea_id}` | Edit idea card |
| POST | `/ideas/{idea_id}/refine` | Refine with free-form instruction |
| POST | `/channels/{ch_id}/shelf` | Save idea to shelf |
| GET | `/channels/{ch_id}/shelf` | List shelf ideas |
| POST | `/shelf/{idea_id}/promote` | Promote shelf idea to project |

### 10.5 Titles (P05)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/titles/generate` | Generate title candidates |
| GET | `/projects/{id}/titles` | List title candidates |
| PUT | `/titles/{title_id}` | Edit title |
| POST | `/titles/{title_id}/lock` | Lock a title |
| PUT | `/titles/{title_id}/shipped` | P-08: Mark title as shipped (for P23 stats) |
| POST | `/projects/{id}/titles/regen-selected` | Regenerate only selected titles |
| POST | `/projects/{id}/titles/shorten` | AI-suggest shortened variant |

### 10.6 Scripts (P06/P07)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/script/outline` | Generate outline (Pass 1) |
| POST | `/projects/{id}/script/draft` | Generate full draft — **streamed SSE** (Pass 2) |
| POST | `/projects/{id}/script/punchup` | Punch up selected section (Pass 3) |
| POST | `/projects/{id}/script/check` | Consistency check (Pass 4) |
| POST | `/projects/{id}/script/import` | Import script (paste/upload) |
| POST | `/projects/{id}/script/auto-section` | Auto-section imported script |
| GET | `/projects/{id}/script` | Get current script (with versions) |
| PUT | `/projects/{id}/script` | Edit script text |
| POST | `/projects/{id}/script/lock` | Lock script (snapshot + stats + diff capture) |
| POST | `/projects/{id}/script/rebalance` | Rebalance section word counts |

### 10.7 Characters (P09)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/characters/extract` | Run character extraction |
| GET | `/projects/{id}/characters` | List characters |
| PUT | `/characters/{char_id}` | Edit character |
| PUT | `/characters/{char_id}/significance` | Change significance (core/supporting/minor) |
| PUT | `/characters/{char_id}/render` | Toggle drawn↔fetched |
| POST | `/characters/{char_id}/bundle` | Bundle into generic |
| POST | `/characters/split` | Split a generic character |
| POST | `/characters/merge` | Merge characters |
| POST | `/characters/add` | Add character manually |
| GET | `/projects/{id}/mentions` | Get mention map |
| POST | `/projects/{id}/characters/reextract` | Re-extract (diff/merge) |

### 10.8 Variants (P10)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/variants/extract` | Run variant extraction |
| GET | `/characters/{char_id}/variants` | List variants for character |
| PUT | `/variants/{var_id}` | Edit variant |
| POST | `/variants/{var_id}/demote` | Demote to one-off pose |
| POST | `/variants/merge` | Merge variant spans |
| POST | `/variants/split` | Split variant span |

### 10.9 Environments (P11)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/environments/extract` | Run environment extraction |
| GET | `/projects/{id}/environments` | List environments |
| PUT | `/environments/{env_id}` | Edit environment |
| POST | `/environments/merge` | Merge environments |
| POST | `/environments/split` | Split environment |
| POST | `/environments/add` | Add manually |
| GET | `/environments/{env_id}/variations` | List variations |
| PUT | `/env-variations/{var_id}` | Edit variation |

### 10.10 World Records (P12)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/world/scan` | Run world scan |
| GET | `/projects/{id}/world` | List world records |
| PUT | `/world/{rw_id}` | Edit record |
| PUT | `/world/{rw_id}/approve` | Approve/dismiss |
| PUT | `/world/{rw_id}/mode` | Switch meme mode |
| POST | `/world/add` | Add manually |

### 10.11 Choreography (P13)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/choreography/infer` | Run pose inference |
| GET | `/characters/{char_id}/poses` | List poses for character/variant |
| PUT | `/sheets/{sheet_id}/poses` | Edit pose list |
| POST | `/sheets/{sheet_id}/poses/add` | Add pose from suggestions tray |

### 10.12 Prompt Cards (P14/P15)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/prompts/assemble` | Assemble all prompt cards |
| GET | `/projects/{id}/sheets` | List all sheets with prompt cards |
| GET | `/sheets/{sheet_id}` | Get single sheet detail |
| PUT | `/sheets/{sheet_id}/prompt` | Edit prompt text |
| POST | `/sheets/{sheet_id}/regen` | Regenerate prompt (slot-stable) |
| GET | `/sheets/{sheet_id}/lint` | Run lint check |

### 10.13 Export (P16)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/export/package` | Generate export package |
| GET | `/projects/{id}/export/checklist` | Get generation checklist |
| GET | `/projects/{id}/export/download` | Download zip |

### 10.14 Checkpoint (P17)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/checkpoint/import` | Import drafts/finals (auto-match) |
| GET | `/projects/{id}/checkpoint` | List sheets with checkpoint status |
| POST | `/sheets/{sheet_id}/approve` | Approve (with 4+1 checklist) |
| POST | `/sheets/{sheet_id}/reject` | Reject (with reason) |
| POST | `/projects/{id}/checkpoint/bulk` | Bulk approve/reject |
| GET | `/sheets/{sheet_id}/bg-check` | Run background color check |

### 10.15 Library (P18)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/channels/{ch_id}/library` | List library assets |
| POST | `/channels/{ch_id}/library` | Add to library |
| PUT | `/library/{lib_id}` | Edit tags/status |
| POST | `/library/{lib_id}/retire` | Retire asset |
| GET | `/channels/{ch_id}/library/savings` | Get savings counter |
| GET | `/channels/{ch_id}/library/match` | Find matches for current project |
| GET | `/channels/{ch_id}/library/manifest` | P-06: Export one-click library manifest (backup/audit) |

### 10.16 Beats (P19/P20)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/beats/chunk` | Run chunking (local, zero AI) |
| POST | `/projects/{id}/beats/split` | Run beat splitting |
| GET | `/projects/{id}/beats` | List chunks and beats |
| POST | `/beats/{beat_id}/merge` | Merge beats |
| POST | `/beats/{beat_id}/split` | Split beat |
| POST | `/projects/{id}/beats/prompts` | Generate per-beat prompts |
| PUT | `/beat-elements/{el_id}` | Edit beat element |
| POST | `/beats/{beat_id}/regen` | Regenerate single beat prompt |
| PUT | `/beats/{beat_id}/text-only` | Toggle text-only |
| GET | `/projects/{id}/beats/one-offs` | List one-off tray |
| POST | `/beat-elements/{el_id}/promote` | Promote one-off to library |

### 10.17 Handoff (P21)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/handoff/export` | Generate handoff package |
| GET | `/projects/{id}/handoff/preview` | Get storyboard preview data |
| GET | `/projects/{id}/handoff/preflight` | Run preflight lint |
| GET | `/projects/{id}/handoff/download` | Download handoff zip |

### 10.18 Download Desk (P22)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/projects/{id}/download-desk` | List pending RW assets |
| POST | `/world/{rw_id}/search-url` | Generate browser search URL |
| POST | `/world/{rw_id}/import` | Import downloaded file |
| PUT | `/world/{rw_id}/role-tag` | Set final_insert or generation_reference |

### 10.19 Channel Intelligence (P23)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/intelligence/metrics` | Submit video metrics |
| POST | `/projects/{id}/intelligence/thumbnail` | Upload thumbnail |
| GET | `/channels/{ch_id}/intelligence/retention` | Get retention analysis |
| GET | `/channels/{ch_id}/intelligence/patterns` | Get cross-video patterns |
| GET | `/channels/{ch_id}/lessons` | List lessons |
| POST | `/lessons/{id}/approve` | Approve a lesson |
| POST | `/lessons/{id}/retire` | Retire a lesson |
| POST | `/lessons/{id}/revert` | Revert a lesson |

### 10.20 Shot Types (P24)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/shots/scan` | Scan beats for special shot triggers |
| GET | `/projects/{id}/shots` | List detected special shots |
| GET | `/shot-types` | List registered shot type templates |
| POST | `/shot-types` | Register custom shot type |

### 10.21 Overlays (P25)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/overlays/generate` | Generate overlay text for text-only beats |
| GET | `/projects/{id}/overlays` | List overlay specs |
| PUT | `/beats/{beat_id}/overlay` | Edit overlay text/spec |
| GET | `/beats/{beat_id}/overlay/preview` | Preview overlay rendering |

### 10.22 Ripple & Jobs
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/projects/{id}/ripple` | Get all stale items |
| POST | `/projects/{id}/ripple/review` | Submit ripple review decisions |
| GET | `/projects/{id}/jobs` | List job queue |
| GET | `/jobs/{job_id}` | Get job status/log |
| GET | `/projects/{id}/transparency/{scope}` | Get transparency data for a scope |

---

## 11. Sprint Execution Order

### 🏃 Sprint 1 — Skeleton (P01, P02, P03, P08)
**Goal**: App boots, connects to LLM, channel with style kit exists, theme visible.

1. Init repo: FastAPI backend + React/Vite frontend
2. Wire Tailwind with ALL Pixel Platformer tokens (colors, fonts, shadows, textures)
3. Self-host fonts (Press Start 2P, Pixelify Sans, Nunito)
4. Build layout shell: Sidebar, TopBar, main canvas area
5. S17 Settings: endpoint, 3 model slots + one-model checkbox, key paste, test connection
6. `core/llm_client.py`: recipe loading, context packs, JSON validation + repair-retry, job_log
7. `core/id_generator.py`: sequential ID minting
8. `db/`: SQLite connection, schema creation, rebuild-from-files
9. S01 Home: create channel (kit wizard: upload refs → AI descriptor → confirm defaults), create/open/rename project, auto-scan projects dir
10. `start.bat` / `start.sh`: launcher that boots both servers + opens browser

**Definition of Done**: App boots via launcher; key works; channel with kit exists; Pixel Platformer theme fully visible.

---

### 🏃 Sprint 2 — The Funnel (P04, P05, P06, P07)
**Goal**: Idea → locked script end-to-end; imported scripts get the same tools.

1. S02 Idea Studio: textarea, Refine & Expand, Surprise Me (6 concepts), card grid, detail+refine loop, Shelf, fast-lane, skip doors
2. S03 Title Studio: 10 candidates, shortlist/edit/remix/regen-selected, own-title door, char count warning, lock
3. S04 Script Studio: slider↔duration, Pass 1 (outline), Pass 2 (streaming draft), Pass 3 (punch-up), Pass 4 (consistency check), hook highlight, pacing strip, breakdown sidebar, sanity card
4. Script import: paste/drop → instant word count/duration, optional auto-sectioning
5. Lock mechanics: version snapshot, stats capture, edit diff, ripple activation
6. P07 finalization-learning hook: capture draft→final diff for P23

**Definition of Done**: Full idea-to-locked-script pipeline works. Imported scripts get all tools. Versions preserved.

---

### 🏃 Sprint 3 — The Brain (P09, P10, P11, P12)
**Goal**: Locked script → four reviewed registries with IDs minted.

1. S05 Cast Board: character extraction, cards, drawn↔fetched toggle, significance, resolution inspector, library check, scale reality check
2. S06 Variant Timelines: horizontal strips, merge/split, cost control, contradiction detector
3. S07 Scout Board: environment extraction, cards, variations, green-conflict, library reuse, cross-audit
4. S08 World Desk: world scan, grouped cards, meme mode, map triggers, usage intent
5. World annotations emission from P09–P11 passes
6. Defensive sharding for scripts >4,000 words
7. Diff/merge re-extraction when script changes
8. `core/ripple.py`: basic stale-flagging for script→registries

**Definition of Done**: Locked script produces all four registries. IDs minted. Edits preserve human changes via diff/merge.

---

### 🏃 Sprint 4 — The Factory (P13, P14, P15, P16, P17)
**Goal**: Prompt cards exported → drafts imported → approved → finals recorded.

1. S09 Choreography Board: pose inference, lean sheets, suggestions tray, library extensions
2. S10 Card View: 8-slot prompt cards, lint, slot-stable regen, copy prompt+refs, no-pronouns enforcement
3. S11 Export Desk: package builder, generation checklist, zip download
4. S12 Checkpoint Board: auto-match import, pixel background check, 4+1 checklist, bulk triage, seed/model capture
5. Status ladder enforcement: draft_prompted → draft_imported → approved → final

**Definition of Done**: Complete loop: poses inferred → prompt cards assembled → exported → drafts imported → approved → finals with metadata.

---

### 🏃 Sprint 5 — The Storyboard (P18, P19, P20, P21)
**Goal**: Locked sheets + locked script → exported handoff zip.

1. S13 Library: browse/search, reuse matching, extension sheets, savings counter, kit-version safety
2. P19 chunking (local) + beat splitting (AI) + Beat Board
3. S14 Beat Studio: reuse-first elements, one-off tray, SVO reveal, pacing visualizer, text-only toggles
4. S15 Storyboard preview: scrollable text+thumbnails, versioned handoff export
5. Handoff package: alignment table, manifest, assets, one-off prompts, inserts, editor notes, text-only specs, README
6. Preflight lint + re-export with change summary

**Definition of Done**: Full pipeline from approved assets → handoff zip with everything an editor needs.

---

### 🏃 Sprint 6 — Loop & Extras (P22, P23, P24, P25)
**Goal**: Published video stats → one approved lesson visibly altering a new generation.

1. Download Desk polish: browser-search buttons, role tags, import matching
2. S16 Channel Intelligence: metrics entry, retention→beat mapping, sparklines, pattern mining, lessons, diff approval
3. P24 shot type registry + map redraw cards + meme parody pipeline
4. P25 text-only beat overlay specs + preview rendering
5. Lessons injection into context packs + transparency panel showing which lessons shaped output
6. G01 Ripple Review: full implementation with batched review
7. G02 Transparency Drawer: full implementation scoped per beat

**Definition of Done**: Stats entered → lesson proposed → user approves → next generation uses that lesson. Full loop closed.

---

## 12. Engineering Conventions (Mandatory)

1. **Every AI job** = recipe file + context pack + Pydantic schema validation + repair-retry once + `job_log` entry. No raw prose into the DB.
2. **Version everything; never overwrite.** Re-extraction/ripple = diff & merge. Old versions always preserved.
3. **Manual override affordance** on every AI surface. Edit/skip/replace always available.
4. **IDs minted by app only.** Export prefixes applied at handoff only. AI never sees prefixed IDs.
5. **Advisories never block** (amber notes, lints, warnings). Generation rules enforce (approved-sheets-only gate at beats).
6. **`data/` never in git.** Settings local. Secrets never hardcoded.
7. **File mirrors**: every DB artifact also exists as a human-readable `.txt`/`.md` file. DB can be rebuilt from files.
8. **Explorer-friendly folders**: stable naming, `README.txt` per project explaining layout.
9. **FIFO job queue** for multi-user: tiny "queued" badge in UI.
10. **Streaming** for long-form jobs (script draft, ideation) via SSE.

---

## 13. Error Handling & Edge Cases

| Scenario | Behavior |
|----------|----------|
| LLM returns invalid JSON | Auto-repair retry once (re-prompt with error + raw output). If still invalid → error badge + manual override. |
| LLM connection fails | Toast error with retry button. Settings link. |
| Script >4,000 words for extraction | Auto-shard into overlapping segments, merge/deduplicate results. |
| Cast >20 characters detected | Same defensive sharding. |
| Green-conflict on character/environment | Auto-switch background to white. Confirmed at checkpoint. |
| Kit version mismatch on library reuse | Prompt: "Reuse as-is" OR "Regenerate under current kit" (draft-first). |
| Variant spans ≤2 beats | Auto-suggest demotion to one-off pose. |
| File dropped outside app (manual edit in Explorer) | Rescan button picks up changes. |
| DB corruption | Rebuild-from-files button reconstructs entire DB. |
| Concurrent jobs (multi-user) | FIFO queue, "queued" badge. |

---

## 14. File Export Formats

### 14.1 Prompt Export Package (P16)
```
prompts/
  C01-S1_master.txt
  C01-S1_master.md
  C01-V1-S1_variant.txt
  ...
references/
  (copies of all style-kit refs + master sheet images for chaining)
editor_notes/
  C01_compositing.md
  E02_compositing.md
manifest.json
README.txt
generation_checklist.md
```

### 14.2 Handoff Package (P21)
```
HANDOFF_EP01_v1/
  alignment_table.txt
  alignment_table.md
  manifest.json
  assets/
    (all final images, named by sheet ID)
  one_off_prompts/
    (prompts for beat-specific one-offs)
  inserts/
    (real-world downloaded assets)
  editor_notes/
    (standing planes, horizons, box maps, keying colors)
  text_only_beats.md
  README.txt
```

---

## 15. Security & Deployment Notes

### Localhost (v1)
- API key stored in `data/settings.json` (gitignored)
- No auth needed for single-user localhost
- CORS: allow `localhost` origins only

### Cloud (future)
- Real login/roles required (auth stub in Sprint 6)
- Server-side key storage (env vars / secrets manager)
- File storage migration (S3/GCS)
- Team permissions (lock audit, role-based transparency drawer visibility)
- Key exposure redesign required before any public deployment

---

## 16. Reality Checks (Pinned Assumptions)

These were made explicit during verification. They are **not optional** — the implementing agent must honor them.

### 16.1 Pinned Dependencies (`requirements.txt`)
```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
openai>=1.12.0
pillow>=10.2.0              # P17 corner-pixel background check — easy to forget
python-multipart>=0.0.9     # file uploads (style kit refs, imports, thumbnails)
sse-starlette>=2.0.0        # SSE streaming (or use plain StreamingResponse — see §16.4)
aiosqlite>=0.20.0           # async SQLite access
pydantic>=2.6.0
```

### 16.2 Font Licensing
All three fonts are **SIL Open Font License (OFL)** — self-hosting is legally clean:
- Press Start 2P (OFL)
- Pixelify Sans (OFL)
- Nunito (OFL)

No copied/Nintendo assets anywhere. Original pixel assets only.

### 16.3 SQLite WAL Mode
Enable **Write-Ahead Logging (WAL)** on every `project.db` at creation:
```python
connection.execute("PRAGMA journal_mode=WAL;")
```
Why: v1 single-writer localhost is fine with default journal, but WAL prevents a storage rewrite when migrating to cloud/team (concurrent readers). Zero cost to enable now.

### 16.4 Vite Proxy + SSE
`EventSource` through Vite's dev proxy works for standard GET-based SSE. If the proxy complains with POST-initiated streams:
- Option A: Keep SSE endpoints as GET (query params for job reference)
- Option B: Use `fetch()` with `ReadableStream` instead of `EventSource`

Decide at implementation time based on actual proxy behavior. Both work; this is not a blocking design decision.

---

## 17. Patch Log

All patches applied from the verification cross-read:

| Patch | Issue | Fix |
|-------|-------|-----|
| P-01 | Project folder naming contradicts P02 portability lock | Folder = stable `{channel}_{EP##}`; date+slug are DB display metadata only |
| P-02 | Beats have no working folder (files-first violation) | Added `07_beats/` with chunks.json, beats.json, prompts/, one_offs/; shifted handoff to `08_`, intelligence to `09_` |
| P-03 | RW id collision between characters and world_records | One `RW##`/`MT##` counter per project; fetched person creates rows in BOTH tables with same id |
| P-04 | Missing `video_stats` table for P23 raw metrics | Added §3.18 `video_stats` table |
| P-05 | Missing project backup/import endpoints (P02 portability) | Added `POST /projects/{id}/backup` + `POST /projects/import` |
| P-06 | Missing library manifest export (P18 lock #7) | Added `GET /channels/{id}/library/manifest` |
| P-07 | Host builder flow not explicit (P09 amendment) | Added `POST/PUT /channels/{id}/host` + choreography endpoint |
| P-08 | Shipped-title marking has no endpoint (P05/P21) | Added `PUT /titles/{id}/shipped` |
| P-09 | Chroma hex + missing timestamps | Locked `#00FF00` as default; added `updated_at` to `titles`, `variants`, `beat_elements` |

---

> [!IMPORTANT]
> **This blueprint is the complete specification.** An implementing agent should be able to build the entire app from this document alone, without needing to reference the original four source documents. Every decision, every schema, every endpoint, every screen, every component is specified above. All 9 patches from cross-verification have been applied.

> [!NOTE]
> **Before you start**: Please review if there's anything you'd like to adjust, add, or clarify — particularly around the sprint priorities, any features you want to add/remove, or the tech stack choices.
