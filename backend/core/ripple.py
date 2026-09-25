# backend/core/ripple.py
from backend.db.connection import get_project_db


async def flag_downstream_stale(folder: str, project_id: str) -> dict:
    """Ripple v1: script text changed -> brain artifacts need review.
    Variants are not touched directly: they hide behind stale characters
    (UI joins on characters.stale=0) and rebuild on re-extraction.
    Scenes are leaves until Phase 3: they go stale here but scene edits
    never cascade further (no downstream of scenes yet)."""
    proj_db = await get_project_db(folder)
    counts = {}
    for table in ("characters", "environments", "world_records", "beats"):
        cur = await proj_db.execute(
            f"UPDATE {table} SET stale=1 WHERE project_id=? AND stale=0", (project_id,))
        counts[table] = cur.rowcount
    # SCENES-MP4 P1-T07: scenes has no project_id column (keyed by beat_id),
    # so scope via the beats join; count must equal the beat count.
    cur = await proj_db.execute(
        "UPDATE scenes SET stale=1 WHERE stale=0 AND beat_id IN "
        "(SELECT id FROM beats WHERE project_id=?)", (project_id,))
    counts["scenes"] = cur.rowcount
    await proj_db.commit()
    await proj_db.close()
    return counts
