# backend/api/dashboard.py
"""One-call summary of where an episode stands.

Everything here is already stored somewhere (project.db, job_log, the stale
flags) - the point is to answer "what do I do next" without visiting every
stage to work it out.
"""
from fastapi import APIRouter, HTTPException

from backend.db.connection import get_app_db, get_project_db
from backend.api.stale import stale_counts

router = APIRouter(tags=["dashboard"])

# Tables that carry project_id; the rest live in a per-project database.
_WITH_PID = {"characters", "environments", "world_records", "beats", "generations", "scripts", "library"}


async def _proj(project_id: str):
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id, stage, slug FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(row)


async def _n(proj_db, project_id: str, table: str, where: str = "") -> int:
    if table in _WITH_PID:
        sql, args = f"SELECT COUNT(*) c FROM {table} WHERE project_id=?{where}", (project_id,)
    else:
        sql, args = f"SELECT COUNT(*) c FROM {table} WHERE 1=1{where}", ()
    async with proj_db.execute(sql, args) as cur:
        return (await cur.fetchone())["c"]


@router.get("/projects/{project_id}/dashboard")
async def dashboard(project_id: str):
    proj = await _proj(project_id)
    folder = proj["folder_name"]
    proj_db = await get_project_db(folder)

    counts = {
        "characters": await _n(proj_db, project_id, "characters"),
        "variants": await _n(proj_db, project_id, "variants"),
        "environments": await _n(proj_db, project_id, "environments"),
        "world_records": await _n(proj_db, project_id, "world_records"),
        "beats": await _n(proj_db, project_id, "beats"),
        "generations": await _n(proj_db, project_id, "generations"),
        "sheets": await _n(proj_db, project_id, "sheets"),
    }

    lib_total = await _n(proj_db, project_id, "library")
    lib_ready = await _n(proj_db, project_id, "library", " AND status='ready'")

    async with proj_db.execute(
        "SELECT version, word_count FROM scripts WHERE project_id=? AND locked=1 "
        "ORDER BY id DESC LIMIT 1", (project_id,)) as cur:
        script = await cur.fetchone()
    await proj_db.close()

    stale = await stale_counts(project_id)
    stale_total = stale.get("total", 0)

    locked = script is not None
    script_words = script["word_count"] if script else 0
    script_version = script["version"] if script else None

    # What to do next, and where to do it.
    if not locked:
        next_action = {"label": "Write and lock a script", "screen": "script", "why": "Nothing downstream can run until the script is locked."}
    elif stale_total:
        next_action = {"label": f"Re-extract {stale_total} stale artifact{'s' if stale_total != 1 else ''}",
                       "screen": "cast", "action": "reextract",
                       "why": "The locked script changed, so these no longer match it."}
    elif not counts["characters"]:
        next_action = {"label": "Extract the cast", "screen": "cast", "why": "No characters found yet."}
    elif not counts["environments"]:
        next_action = {"label": "Extract locations", "screen": "locations", "why": "No locations found yet."}
    elif not counts["beats"]:
        next_action = {"label": "Cut the script into beats", "screen": "beats", "why": "Beats are the shots you will generate."}
    elif not counts["generations"]:
        next_action = {"label": "Compose shot prompts", "screen": "beats", "why": "No prompts built yet."}
    elif lib_ready < lib_total:
        next_action = {"label": f"Attach {lib_total - lib_ready} remaining asset{'s' if lib_total - lib_ready != 1 else ''}",
                       "screen": "library", "why": "Export waits until every library slot is ready."}
    else:
        next_action = {"label": "Export the episode package", "screen": "export", "why": "Everything is ready."}

    blockers = []
    if not locked:
        blockers.append({"label": "No locked script", "done": False})
    if stale_total:
        blockers.append({"label": f"{stale_total} stale artifacts not re-extracted", "done": False})
    if not counts["generations"]:
        blockers.append({"label": "Shot prompts not composed", "done": False})
    else:
        blockers.append({"label": f"{counts['generations']} shot prompts composed", "done": True})
    if lib_ready < lib_total:
        blockers.append({"label": f"{lib_ready} of {lib_total} assets ready", "done": False})
    else:
        blockers.append({"label": f"All {lib_total} assets ready", "done": True})

    return {
        "project_id": project_id,
        "slug": proj["slug"],
        "stage": proj["stage"],
        "script": {"locked": locked, "version": script_version, "words": script_words},
        "counts": counts,
        "library": {"total": lib_total, "ready": lib_ready},
        "stale": stale,
        "next_action": next_action,
        "blockers": blockers,
    }
