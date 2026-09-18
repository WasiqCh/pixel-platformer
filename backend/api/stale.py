# backend/api/stale.py
"""Stale tracking.

When a locked script changes, backend/core/ripple.py flags the downstream
artifacts (characters, variants, environments, world records, beats, sheets)
as stale. This module makes that visible and gives one-click ways to deal
with it, instead of having to visit each stage and remember what changed.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.db.connection import get_app_db, get_project_db

router = APIRouter(tags=["stale"])

# Sidebar stage -> tables that hold its artifacts.
STAGE_TABLES = {
    "cast": ["characters"],
    "variants": ["variants"],
    "locations": ["environments", "env_variations"],
    "world": ["world_records"],
    "beats": ["beats"],
    "sheets": ["sheets"],
}

# Tables that carry a project_id column. The rest live in a per-project
# database, so every row already belongs to this project.
TABLES_WITH_PROJECT_ID = {"characters", "environments", "world_records", "beats"}

# Order matters: cast feeds variants, locations feed sheets, etc.
STAGE_ORDER = ["cast", "variants", "locations", "world", "beats", "sheets"]


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _get_proj_info(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


async def _count_stale(db, project_id: str, table: str) -> int:
    if table in TABLES_WITH_PROJECT_ID:
        sql, args = f"SELECT COUNT(*) c FROM {table} WHERE project_id=? AND stale=1", (project_id,)
    else:
        sql, args = f"SELECT COUNT(*) c FROM {table} WHERE stale=1", ()
    async with db.execute(sql, args) as cur:
        return (await cur.fetchone())["c"]


async def _clear_stale(db, project_id: str, table: str) -> int:
    if table in TABLES_WITH_PROJECT_ID:
        sql, args = f"UPDATE {table} SET stale=0 WHERE project_id=? AND stale=1", (project_id,)
    else:
        sql, args = f"UPDATE {table} SET stale=0 WHERE stale=1", ()
    cur = await db.execute(sql, args)
    return cur.rowcount


@router.get("/projects/{project_id}/stale")
async def stale_counts(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    db = await get_project_db(folder)
    counts, total = {}, 0
    for stage in STAGE_ORDER:
        n = 0
        for table in STAGE_TABLES[stage]:
            n += await _count_stale(db, project_id, table)
        counts[stage] = n
        total += n
    await db.close()
    counts["total"] = total
    return counts


@router.post("/projects/{project_id}/stale/clear")
async def clear_stale(project_id: str, stage: Optional[str] = None):
    """Mark stale artifacts reviewed without redoing them."""
    if stage and stage not in STAGE_TABLES:
        raise HTTPException(400, f"Unknown stage '{stage}'")
    folder, _ = await _get_proj_info(project_id)
    db = await get_project_db(folder)
    cleared = 0
    stages = [stage] if stage else STAGE_ORDER
    for s in stages:
        for table in STAGE_TABLES[s]:
            cleared += await _clear_stale(db, project_id, table)
    await db.commit()
    await db.close()
    return {"status": "cleared", "cleared": cleared}


@router.post("/projects/{project_id}/stale/reextract")
async def reextract_stale(project_id: str, stage: Optional[str] = None):
    """Re-run extraction for whichever stages are stale.

    Each stage is independent: one failing does not stop the others, and the
    per-stage result is reported so you can see what actually got rebuilt.
    """
    if stage and stage not in STAGE_TABLES:
        raise HTTPException(400, f"Unknown stage '{stage}'")
    folder, _ = await _get_proj_info(project_id)
    db = await get_project_db(folder)

    stale_stages = []
    for s in ([stage] if stage else STAGE_ORDER):
        n = 0
        for table in STAGE_TABLES[s]:
            n += await _count_stale(db, project_id, table)
        if n:
            stale_stages.append(s)
    await db.close()

    if not stale_stages:
        return {"status": "nothing_stale", "results": []}

    from backend.api.beats import extract_beats
    from backend.api.characters import extract_characters
    from backend.api.environments import extract_environments
    from backend.api.sheets import generate_sheets
    from backend.api.variants import extract_variants
    from backend.api.world import scan_world

    runners = {
        "cast": extract_characters,
        "variants": extract_variants,
        "locations": extract_environments,
        "world": scan_world,
        "beats": extract_beats,
        "sheets": generate_sheets,
    }

    results = []
    for s in stale_stages:
        try:
            await runners[s](project_id)
            results.append({"stage": s, "ok": True})
        except HTTPException as e:
            results.append({"stage": s, "ok": False, "error": str(e.detail)})
        except Exception as e:
            results.append({"stage": s, "ok": False, "error": str(e)})

    return {
        "status": "done",
        "attempted": stale_stages,
        "results": results,
        "failed": [r["stage"] for r in results if not r["ok"]],
    }
