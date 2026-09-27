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


# --- SCENES-MP4 ST-T01: one-call project status (runbook fuel, read-only). ---
# Aggregates what today takes six queries: beats, voice WAVs, scenes, assets,
# gens, overlays, plus the render gate and the latest render job. Composes
# existing queries only — no new logic, no writes (SELECTs + stat() checks;
# no INSERT/UPDATE/DELETE, no commit, no mkdir). Gate + job payload are reused
# from backend.api.render (render_gate / _latest_job_row / _job_status_payload)
# via deferred import so no import cycle can form. Unknown project 404s via
# _proj before any other work.
@router.get("/projects/{project_id}/status")
async def project_status(project_id: str):
    from pathlib import Path as _Path

    from backend.core.config import DATA_DIR as _DATA_DIR
    from backend.api import render as _render_api

    proj = await _proj(project_id)
    folder = proj["folder_name"]
    proj_db = await get_project_db(folder)
    try:
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM beats WHERE project_id=?", (project_id,)
        ) as cur:
            beats_total = (await cur.fetchone())["c"]
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM beats WHERE project_id=? AND stale=1",
            (project_id,),
        ) as cur:
            beats_stale = (await cur.fetchone())["c"]
        async with proj_db.execute(
            "SELECT id FROM beats WHERE project_id=? AND stale=1 ORDER BY sort_order",
            (project_id,),
        ) as cur:
            stale_beat_ids = [r["id"] for r in await cur.fetchall()]
        # Scenes are keyed by beat_id (no project_id) — scope via beats JOIN,
        # same shape as GET .../scenes (scenes.py::list_scenes).
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scenes s JOIN beats b ON b.id=s.beat_id "
            "WHERE b.project_id=?",
            (project_id,),
        ) as cur:
            scenes_total = (await cur.fetchone())["c"]
        # Assets: matched = library_ref set / pending = needs_generate set
        # (P1-T06 XOR invariant) — same scope shape as GET .../scenes/assets.
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scene_assets sa JOIN beats b ON b.id=sa.beat_id "
            "WHERE b.project_id=?",
            (project_id,),
        ) as cur:
            assets_total = (await cur.fetchone())["c"]
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scene_assets sa JOIN beats b ON b.id=sa.beat_id "
            "WHERE b.project_id=? AND sa.library_ref IS NOT NULL",
            (project_id,),
        ) as cur:
            assets_matched = (await cur.fetchone())["c"]
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scene_assets sa JOIN beats b ON b.id=sa.beat_id "
            "WHERE b.project_id=? AND sa.needs_generate=1",
            (project_id,),
        ) as cur:
            assets_pending = (await cur.fetchone())["c"]
        # Gens carry project_id — same filter as GET .../generations.
        async with proj_db.execute(
            "SELECT status, COUNT(*) c FROM generations WHERE project_id=? "
            "GROUP BY status",
            (project_id,),
        ) as cur:
            gen_rows = [dict(r) for r in await cur.fetchall()]
        # Overlays scoped via beats JOIN, same shape as GET .../scenes/overlays.
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scene_overlays so JOIN beats b ON b.id=so.beat_id "
            "WHERE b.project_id=?",
            (project_id,),
        ) as cur:
            overlays_total = (await cur.fetchone())["c"]
        # Voice WAV presence uses the same vo_dir layout render_gate reads
        # (08_export/voiceover/<beat>.wav); non-empty file + measured duration.
        async with proj_db.execute(
            "SELECT id, duration_sec FROM beats WHERE project_id=? AND stale=0 "
            "ORDER BY sort_order",
            (project_id,),
        ) as cur:
            fresh_beats = [dict(r) for r in await cur.fetchall()]
        latest_job = await _render_api._latest_job_row(proj_db, project_id)
    finally:
        await proj_db.close()

    vo_dir = _Path(_DATA_DIR) / "projects" / folder / "08_export" / "voiceover"
    voice_missing: list[str] = []
    for b in fresh_beats:
        wav = vo_dir / f"{b['id']}.wav"
        try:
            ok_file = wav.is_file() and wav.stat().st_size > 0
        except OSError:
            ok_file = False
        try:
            ok_dur = b.get("duration_sec") is not None and float(b["duration_sec"]) > 0
        except (TypeError, ValueError):
            ok_dur = False
        if not (ok_file and ok_dur):
            voice_missing.append(b["id"])
    voice_present = len(fresh_beats) - len(voice_missing)

    # Gate is the shared check (pure read) — blocker lists included verbatim.
    gate = await _render_api.render_gate(project_id)

    task = _render_api._TASKS.get(project_id)
    alive = task is not None and not task.done()
    job_payload = _render_api._job_status_payload(latest_job, alive)

    gens_by_status = {r["status"]: int(r["c"]) for r in gen_rows}
    gens_total = sum(gens_by_status.values())

    return {
        "project_id": project_id,
        "beats": {
            "total": beats_total,
            "fresh": len(fresh_beats),
            "stale": beats_stale,
            "stale_ids": stale_beat_ids,
        },
        "voice": {
            "present": voice_present,
            "missing": len(voice_missing),
            "missing_ids": voice_missing,
        },
        "scenes": {
            "total": scenes_total,
            "approved": gate["approved"],
            "unapproved": len(gate["unapproved"]),
            "unapproved_ids": gate["unapproved"],
            "stale": len(gate["stale_scenes"]),
            "stale_ids": gate["stale_scenes"],
        },
        "assets": {
            "total": assets_total,
            "matched": assets_matched,
            "pending": assets_pending,
        },
        "gens": {"total": gens_total, "by_status": gens_by_status},
        "overlays": {"total": overlays_total},
        "gate": gate,
        "render_job": job_payload,
    }
