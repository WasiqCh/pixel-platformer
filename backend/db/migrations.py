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
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, channel_id TEXT NOT NULL REFERENCES channels(id),
    slug TEXT NOT NULL, folder_name TEXT NOT NULL UNIQUE,
    stage TEXT NOT NULL DEFAULT 'idea',
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
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

async def init_app_db(db_conn):
    await db_conn.executescript(APP_SCHEMA)
    await db_conn.commit()

async def init_project_db(db_conn):
    await db_conn.executescript(PROJECT_SCHEMA)
    await db_conn.commit()