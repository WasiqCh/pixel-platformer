# backend/db/connection.py
import aiosqlite
from pathlib import Path
from backend.core.config import DATA_DIR
from backend.db.migrations import init_app_db, init_project_db

APP_DB_PATH = DATA_DIR / "app.db"

async def _connect(db_path: Path) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    # P-10 & 16.3: Enable WAL mode and Foreign Keys for every connection
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    db.row_factory = aiosqlite.Row
    return db

async def get_app_db() -> aiosqlite.Connection:
    return await _connect(APP_DB_PATH)

async def get_project_db(folder_name: str) -> aiosqlite.Connection:
    project_dir = DATA_DIR / "projects" / folder_name
    project_dir.mkdir(parents=True, exist_ok=True)
    db = await _connect(project_dir / "project.db")
    await init_project_db(db)   # idempotent: heals old DBs whenever schema grows
    return db

async def setup_databases():
    # 1. Init Global App DB
    app_db = await get_app_db()
    await init_app_db(app_db)
    await app_db.close()
    
    # 2. Ensure base directories exist
    (DATA_DIR / "channels").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "projects").mkdir(parents=True, exist_ok=True)