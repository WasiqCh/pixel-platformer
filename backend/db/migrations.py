# backend/db/migrations.py

APP_SCHEMA = """
-- 1. channels
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, kit_version INTEGER NOT NULL DEFAULT 1,
    has_host BOOLEAN NOT NULL DEFAULT 0, overlay_tokens TEXT, tone_samples TEXT,
    descriptor TEXT, avoid_list TEXT, bg_default_hex TEXT NOT NULL DEFAULT '#00FF00',
    env_resolution TEXT NOT NULL DEFAULT '1920x1080', char_resolution TEXT NOT NULL DEFAULT '3:4',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 2. projects (P-01: folder_name is stable, slug is display-only)
-- SCENES-MP4 F1-T02: bg_color_hex (nullable; NULL = channel chroma default).
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, channel_id TEXT NOT NULL REFERENCES channels(id),
    slug TEXT NOT NULL, folder_name TEXT NOT NULL UNIQUE,
    stage TEXT NOT NULL DEFAULT 'idea',
    bg_color_hex TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 3. library_assets
CREATE TABLE IF NOT EXISTS library_assets (
    id TEXT PRIMARY KEY, channel_id TEXT NOT NULL REFERENCES channels(id),
    kind TEXT NOT NULL, tags TEXT NOT NULL, context TEXT, sheet_ref TEXT,
    kit_version INTEGER NOT NULL, usage_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 4. lessons
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT NOT NULL REFERENCES channels(id),
    observation TEXT NOT NULL, evidence TEXT NOT NULL, tweak TEXT NOT NULL,
    target_recipe TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0.5,
    status TEXT NOT NULL DEFAULT 'proposed', diff_text TEXT,
    approved_by TEXT, approved_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 5. video_stats (P-04)
CREATE TABLE IF NOT EXISTS video_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
    channel_id TEXT NOT NULL REFERENCES channels(id), title_shipped TEXT, description TEXT,
    tags TEXT, thumbnail_path TEXT, views INTEGER, impressions INTEGER, ctr REAL,
    avd_seconds REAL, retention_curve TEXT, dropoff_points TEXT, published_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 6. job_log
CREATE TABLE IF NOT EXISTS job_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, channel_id TEXT,
    job_type TEXT NOT NULL, inputs TEXT NOT NULL, context_pack TEXT,
    model TEXT NOT NULL, temperature REAL NOT NULL, raw_output TEXT NOT NULL,
    parsed_output TEXT, tokens_in INTEGER, tokens_out INTEGER,
    duration_ms INTEGER, error TEXT, created_at TEXT NOT NULL
);

-- image generation settings (single row)
CREATE TABLE IF NOT EXISTS image_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT NOT NULL DEFAULT 'manual',
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT 'gemini-2.5-flash-image',
    updated_at TEXT NOT NULL DEFAULT ''
);

-- channel vault (cross-episode asset reuse)
CREATE TABLE IF NOT EXISTS channel_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    asset_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    source_project TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- voice settings (single row)
-- D4-T02: provider switch (gemini default) + per-provider voices (never mix).
CREATE TABLE IF NOT EXISTS voice_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    voice TEXT NOT NULL DEFAULT 'Kore',
    enabled INTEGER NOT NULL DEFAULT 1,
    provider TEXT NOT NULL DEFAULT 'gemini',
    kokoro_voice TEXT NOT NULL DEFAULT 'af_heart',
    updated_at TEXT NOT NULL DEFAULT ''
);

-- channel policy (meme mode)
CREATE TABLE IF NOT EXISTS channel_policy (
    channel_id TEXT PRIMARY KEY,
    meme_mode INTEGER NOT NULL DEFAULT 1
);
"""

PROJECT_SCHEMA = """
-- 7. idea_cards (Cross-DB foreign keys removed)
CREATE TABLE IF NOT EXISTS idea_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, channel_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1, content TEXT NOT NULL,
    shelf_flag BOOLEAN NOT NULL DEFAULT 0, is_current BOOLEAN NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 8. titles
CREATE TABLE IF NOT EXISTS titles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
    text TEXT NOT NULL, angle TEXT, style_tag TEXT, char_count INTEGER NOT NULL,
    locked BOOLEAN NOT NULL DEFAULT 0, shipped BOOLEAN NOT NULL DEFAULT 0,
    is_alternate BOOLEAN NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 9. scripts
CREATE TABLE IF NOT EXISTS scripts (
     id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
     text TEXT NOT NULL, sections TEXT, word_count INTEGER NOT NULL, duration_sec REAL NOT NULL,
     locked BOOLEAN NOT NULL DEFAULT 0, locked_by TEXT, locked_at TEXT,
     source TEXT NOT NULL DEFAULT 'ai', edit_diff TEXT, is_current BOOLEAN NOT NULL DEFAULT 1,
     created_at TEXT NOT NULL
 );

-- 10. characters
CREATE TABLE IF NOT EXISTS characters (
     id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL, faction TEXT,
     render TEXT NOT NULL DEFAULT 'drawn', names TEXT NOT NULL, appearance TEXT,
     significance TEXT NOT NULL DEFAULT 'supporting', presence TEXT,
     green_conflict BOOLEAN NOT NULL DEFAULT 0, library_ref TEXT, world_record_ref TEXT,
     stale BOOLEAN NOT NULL DEFAULT 0,
     created_at TEXT NOT NULL, updated_at TEXT NOT NULL
 );

-- 11. variants (Internal FK kept)
CREATE TABLE IF NOT EXISTS variants (
    id TEXT PRIMARY KEY, character_id TEXT NOT NULL REFERENCES characters(id), span TEXT NOT NULL, delta TEXT NOT NULL,
    evidence TEXT, confidence REAL NOT NULL DEFAULT 0.8, rejected_changes TEXT,
    stale BOOLEAN NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 12. mentions
CREATE TABLE IF NOT EXISTS mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, section TEXT, chunk TEXT,
    mention_text TEXT NOT NULL, resolved_to TEXT, confidence REAL NOT NULL DEFAULT 0.8,
    context TEXT, created_at TEXT NOT NULL
);

-- 13. environments
CREATE TABLE IF NOT EXISTS environments (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, elements TEXT NOT NULL,
    green_conflict BOOLEAN NOT NULL DEFAULT 0, presence TEXT, library_ref TEXT,
    stale BOOLEAN NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 14. env_variations (Internal FK kept)
CREATE TABLE IF NOT EXISTS env_variations (
    id TEXT PRIMARY KEY, environment_id TEXT NOT NULL REFERENCES environments(id), state TEXT NOT NULL, span TEXT NOT NULL,
    evidence TEXT, stale BOOLEAN NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);

-- 15. world_records
CREATE TABLE IF NOT EXISTS world_records (
     id TEXT PRIMARY KEY, project_id TEXT NOT NULL, type TEXT NOT NULL, text TEXT NOT NULL,
     script_context TEXT, usage_intent TEXT NOT NULL DEFAULT 'on_screen_insert',
     search_query TEXT, era_hint TEXT, mode TEXT, layer TEXT NOT NULL DEFAULT 'insert',
     map_template TEXT, status TEXT NOT NULL DEFAULT 'pending', provenance TEXT,
     role_tag TEXT, stale BOOLEAN NOT NULL DEFAULT 0,
     created_at TEXT NOT NULL, updated_at TEXT NOT NULL
 );

-- 16. sheets
CREATE TABLE IF NOT EXISTS sheets (
     id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, parent_type TEXT NOT NULL, kind TEXT NOT NULL,
     grid TEXT, poses TEXT, boxes TEXT, box_map TEXT, status TEXT NOT NULL DEFAULT 'draft_prompted',
     background_color TEXT, kit_version INTEGER, seed TEXT, model TEXT, prompt_text TEXT NOT NULL,
     references_list TEXT, editor_notes TEXT, reject_reason TEXT, stale BOOLEAN NOT NULL DEFAULT 0,
     created_at TEXT NOT NULL, updated_at TEXT NOT NULL
 );

-- 17. beats
CREATE TABLE IF NOT EXISTS beats (
     id TEXT PRIMARY KEY, project_id TEXT NOT NULL, chunk_id TEXT NOT NULL, chunk_text TEXT NOT NULL,
     text TEXT NOT NULL, word_count INTEGER NOT NULL, duration_sec REAL NOT NULL,
     text_only BOOLEAN NOT NULL DEFAULT 0, svo TEXT, overlay_text TEXT, overlay_spec TEXT,
     sort_order INTEGER NOT NULL, stale BOOLEAN NOT NULL DEFAULT 0,
     created_at TEXT NOT NULL, updated_at TEXT NOT NULL
 );

-- 18. beat_elements (Internal FK kept)
CREATE TABLE IF NOT EXISTS beat_elements (
    id TEXT PRIMARY KEY, beat_id TEXT NOT NULL REFERENCES beats(id), asset_ref TEXT NOT NULL, layer TEXT NOT NULL,
    framing TEXT, prompt_text TEXT, refs_to_attach TEXT, editor_note TEXT, improv_note TEXT,
    is_one_off BOOLEAN NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL,
    x REAL, y REAL, scale REAL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- 19. outlines (Sprint 2.5.3: persisted, versioned, editable)
CREATE TABLE IF NOT EXISTS outlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    sections TEXT NOT NULL,
    target_words INTEGER NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 20. library (Sprint 4.5: asset slots linked to cast/locations)
CREATE TABLE IF NOT EXISTS library (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    asset_ref TEXT,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'empty',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 21. generations (Sprint 9: image generation queue)
CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    gen_label TEXT NOT NULL,
    kind TEXT NOT NULL,
    asset_ref TEXT NOT NULL,
    beat_id TEXT,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    file_path TEXT NOT NULL DEFAULT '',
    -- SCENES-MP4 P2-T02: versioned SVG source (06_sheets/svg/<asset>_vN.svg,
    -- nullable; file_path holds the rastered PNG once P2-T06 approves+rasters).
    svg_path TEXT,
    -- SCENES-MP4 D2-T02: provenance marker ('' = AI lane, 'pasted' = user
    -- pasted external SVG via POST .../paste; S15 badge reads PASTED).
    source TEXT NOT NULL DEFAULT '',
    -- SCENES-MP4 S-T04: web-fetch provenance (license + source page recorded
    -- on POST .../fetch; '' = none / AI lane / user upload of own file).
    license TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 22. scenes (SCENES-MP4 P1-T01: per-beat scene plan, leaf until Phase 3)
-- P1-T05: reasoning added (acceptance needs non-empty shot + reasoning per row).
CREATE TABLE IF NOT EXISTS scenes (
    beat_id TEXT PRIMARY KEY REFERENCES beats(id),
    place_asset_ref TEXT,
    shot TEXT,
    reasoning TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    stale BOOLEAN NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 23. scene_assets (SCENES-MP4 P1-T06: per-scene asset needs + library/svg resolution).
-- Each need ends as EXACTLY ONE of library_ref set / needs_generate set
-- (never neither, never both). Misses link out to generations (kind='svg').
CREATE TABLE IF NOT EXISTS scene_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    beat_id TEXT NOT NULL REFERENCES beats(id),
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    search_query TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    library_ref TEXT,
    needs_generate BOOLEAN NOT NULL DEFAULT 0,
    generation_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (library_ref IS NOT NULL AND needs_generate = 0)
        OR (library_ref IS NULL AND needs_generate = 1)
    )
);

-- 24. render_jobs (SCENES-MP4 P4-T01: persisted MP4 render progress).
-- One row per render attempt; resume reuses the same row (keeps
-- current_segment), a fresh render after done inserts a new row (never
-- overwrite). status: running | cancel_requested | cancelled | done | error.
-- current_segment = index of the NEXT segment to process (0-based), so done
-- count = current_segment and resume continues at N, not 1. progress is 0-1.
-- P4-T02/T03 fill in real frames/ffmpeg; T01 iterates beats-as-segments with
-- a short placeholder step so cancel/resume mechanics are provable with no
-- LLM calls.
CREATE TABLE IF NOT EXISTS render_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    total_segments INTEGER NOT NULL DEFAULT 0,
    current_segment INTEGER NOT NULL DEFAULT 0,
    progress REAL NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    output_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 25. scene_overlays (SCENES-MP4 D9-T01: per-scene text-overlay spec, data only).
-- 0+ rows per beat (feasibility is the AI's judgement; absence = explicit
-- none). Re-plan is replace-on-success per beat (P1-T06 precedent). Manual
-- PUT/DELETE per row always allowed. reasoning is non-empty per item (owner
-- review, same rule as scenes/scene_assets).
CREATE TABLE IF NOT EXISTS scene_overlays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    beat_id TEXT NOT NULL REFERENCES beats(id),
    text TEXT NOT NULL,
    role TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '',
    position TEXT NOT NULL DEFAULT '',
    reasoning TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

async def init_app_db(db_conn):
    await db_conn.executescript(APP_SCHEMA)
    # 1 when this row was produced by tier auto-escalation after the cheap
    # model failed validation twice (see llm_client.dispatch).
    await _ensure_column(db_conn, "job_log", "escalated", "INTEGER NOT NULL DEFAULT 0")
    # SCENES-MP4 D4-T02: provider switch (gemini default) + per-provider voice.
    await _ensure_column(db_conn, "voice_settings", "provider", "TEXT NOT NULL DEFAULT 'gemini'")
    await _ensure_column(db_conn, "voice_settings", "kokoro_voice", "TEXT NOT NULL DEFAULT 'af_heart'")
    # SCENES-MP4 F1-T02: project canvas background (NULL = channel chroma
    # default; heals old app.db files idempotently like the voice switch).
    await _ensure_column(db_conn, "projects", "bg_color_hex", "TEXT")
    await _ensure_column(db_conn, "channels", "bg_default_hex", "TEXT NOT NULL DEFAULT '#00FF00'")
    await db_conn.commit()

async def _ensure_column(db_conn, table: str, column: str, ddl: str):
    """Add a column to an existing table if it is missing.

    PROJECT_SCHEMA is CREATE TABLE IF NOT EXISTS, which is a no-op on any
    project database that already exists - so newly added columns would never
    reach existing projects. This backfills them idempotently.
    """
    async with db_conn.execute(f"PRAGMA table_info({table})") as cur:
        cols = {r["name"] for r in await cur.fetchall()}
    if column not in cols:
        await db_conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


async def init_project_db(db_conn):
    await db_conn.executescript(PROJECT_SCHEMA)
    # AI-chosen sprite-sheet actions per character (JSON list, 2-6 entries).
    await _ensure_column(db_conn, "characters", "actions", "TEXT")
    # SCENES-MP4 P1-T02: placement fractions (0-1, nullable; NULL = fall back to framing text).
    await _ensure_column(db_conn, "beat_elements", "x", "REAL")
    await _ensure_column(db_conn, "beat_elements", "y", "REAL")
    await _ensure_column(db_conn, "beat_elements", "scale", "REAL")
    # SCENES-MP4 P1-T05: per-row reasoning (acceptance: non-empty shot + reasoning).
    await _ensure_column(db_conn, "scenes", "reasoning", "TEXT")
    # SCENES-MP4 P2-T02: svg source path (nullable; file_path stays the P2-T06 raster PNG).
    await _ensure_column(db_conn, "generations", "svg_path", "TEXT")
    # SCENES-MP4 D2-T02: provenance marker ('' default = AI lane; 'pasted' set
    # on first paste; heals old DBs idempotently like svg_path above).
    await _ensure_column(db_conn, "generations", "source", "TEXT NOT NULL DEFAULT ''")
    # SCENES-MP4 S-T04: web-fetch provenance (license + source page recorded on
    # POST .../fetch; heals old DBs idempotently like source above).
    await _ensure_column(db_conn, "generations", "license", "TEXT NOT NULL DEFAULT ''")
    await _ensure_column(db_conn, "generations", "source_url", "TEXT NOT NULL DEFAULT ''")
    await db_conn.commit()
