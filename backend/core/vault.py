# backend/core/vault.py
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.db.connection import get_app_db
from backend.storage.fs_manager import get_project_dir


def vault_dir(ch_id: str) -> Path:
    return get_project_dir(ch_id, "_x").parent.parent / "channels" / ch_id / "library"


def asset_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def _now():
    return datetime.now(timezone.utc).isoformat()


async def vault_put(ch_id, key, kind, title, src_abs: Path, project_id):
    vd = vault_dir(ch_id)
    vd.mkdir(parents=True, exist_ok=True)
    dest = vd / (key + (src_abs.suffix or ".png"))
    if src_abs.exists():
        dest.write_bytes(src_abs.read_bytes())
    rel = f"channels/{ch_id}/library/{dest.name}"
    db = await get_app_db()
    async with db.execute("SELECT id FROM channel_library WHERE channel_id=? AND asset_key=?", (ch_id, key)) as cur:
        row = await cur.fetchone()
    if row:
        await db.execute("UPDATE channel_library SET kind=?, title=?, file_path=?, source_project=? WHERE id=?",
                         (kind, title, rel, project_id, row["id"]))
    else:
        await db.execute(
            "INSERT INTO channel_library (channel_id, asset_key, kind, title, file_path, source_project, created_at) "
            "VALUES (?,?,?,?,?,?,?)", (ch_id, key, kind, title, rel, project_id, _now()))
    await db.commit()
    await db.close()


async def vault_get(ch_id, key):
    db = await get_app_db()
    async with db.execute("SELECT * FROM channel_library WHERE channel_id=? AND asset_key=?", (ch_id, key)) as cur:
        row = await cur.fetchone()
    await db.close()
    return dict(row) if row else None