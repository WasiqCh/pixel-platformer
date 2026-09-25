# backend/api/scenes.py
from datetime import datetime, timezone
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.llm_client import dispatch
from backend.db.connection import get_app_db, get_project_db
from backend.models.scene import ScenePlan

router = APIRouter(tags=["scenes"])

# Sharding thresholds shared with backend/core/sharding.py::sharded_extract
# (long scripts split at >4000 words / 300 overlap). Per-beat planning is
# inherently sharded (one small dispatch per beat); only the shared
# full-script context below is capped at the same threshold.
_SHARD_THRESHOLD = 4000
_SHARD_OVERLAP = 300

_FALLBACK_DESCRIPTOR = "clean flat 2D animation, bold outlines, limited palette"


class SceneEdit(BaseModel):
    place_asset_ref: Optional[str] = None
    shot: Optional[str] = None
    reasoning: Optional[str] = None
    status: Optional[str] = None


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _get_proj_info(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


async def _get_locked_script(folder: str, project_id: str):
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT text FROM scripts WHERE project_id=? AND locked=1 ORDER BY id DESC LIMIT 1",
        (project_id,)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    return row["text"] if row else None


async def _style_pack(ch_id: str) -> tuple[str, str]:
    from backend.api.channels import DEFAULT_AVOID
    db = await get_app_db()
    async with db.execute("SELECT descriptor, avoid_list FROM channels WHERE id=?", (ch_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    descriptor = (row["descriptor"] if row and row["descriptor"] else _FALLBACK_DESCRIPTOR)
    avoid = (row["avoid_list"] if row and row["avoid_list"] else DEFAULT_AVOID)
    return descriptor, avoid


async def _approved_registry(proj_db, project_id: str) -> list:
    """Reusable-art index: IDs + names only (never file paths or prefixes)."""
    registry = []
    async with proj_db.execute(
        "SELECT id, names FROM characters WHERE project_id=? AND stale=0 ORDER BY id",
        (project_id,)) as cur:
        for r in await cur.fetchall():
            names = json.loads(r["names"] or "[]")
            registry.append({"id": r["id"], "name": names[0] if names else r["id"]})
    async with proj_db.execute(
        "SELECT id, name FROM environments WHERE project_id=? AND stale=0 ORDER BY id",
        (project_id,)) as cur:
        for r in await cur.fetchall():
            registry.append({"id": r["id"], "name": r["name"]})
    async with proj_db.execute(
        "SELECT id, text FROM world_records WHERE project_id=? AND stale=0 ORDER BY id",
        (project_id,)) as cur:
        for r in await cur.fetchall():
            registry.append({"id": r["id"], "name": (r["text"] or "")[:80]})
    return registry


def _cap_script(script: str) -> str:
    words = script.split()
    if len(words) <= _SHARD_THRESHOLD:
        return script
    keep = _SHARD_THRESHOLD - _SHARD_OVERLAP
    return (" ".join(words[:keep])
            + f" ... [truncated {len(words) - keep} words; "
            + f"sharded_extract thresholds { _SHARD_THRESHOLD}/{_SHARD_OVERLAP}]")


@router.post("/projects/{project_id}/scenes/plan")
async def plan_scenes(project_id: str):
    try:
        return await _plan_scenes_inner(project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Scene plan crashed: {type(e).__name__}: {e}")


async def _plan_scenes_inner(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    script = await _get_locked_script(folder, project_id)
    if not script:
        raise HTTPException(400, "Lock a script first (Script Studio -> Lock).")

    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT id, text FROM beats WHERE project_id=? AND stale=0 ORDER BY sort_order",
        (project_id,)) as cur:
        beats = [dict(r) for r in await cur.fetchall()]
    if not beats:
        await proj_db.close()
        raise HTTPException(400, "Extract beats first (no beats to plan).")

    registry = await _approved_registry(proj_db, project_id)
    descriptor, avoid = await _style_pack(ch_id)
    full_script = _cap_script(script)

    planned, skipped_approved, failed = 0, 0, []
    now = _now()
    for i, beat in enumerate(beats):
        async with proj_db.execute("SELECT status FROM scenes WHERE beat_id=?", (beat["id"],)) as cur:
            existing = await cur.fetchone()
        if existing and existing["status"] == "approved":
            skipped_approved += 1
            continue

        context = {
            "beat_text": beat["text"],
            "prev_beat": beats[i - 1]["text"] if i > 0 else "",
            "next_beat": beats[i + 1]["text"] if i + 1 < len(beats) else "",
            "full_script": full_script,
            "approved_sheets": registry,
            "style_descriptor": descriptor,
            "avoid_list": avoid,
        }
        try:
            res = await dispatch("scene_plan", context, schema=ScenePlan,
                                 project_id=project_id, channel_id=ch_id)
        except Exception as e:
            # One beat's crash must not kill the batch (or leak past `failed`).
            failed.append({"beat_id": beat["id"],
                           "error": f"dispatch crashed: {type(e).__name__}: {str(e)[:150]}"})
            continue
        if not res["ok"]:
            failed.append({"beat_id": beat["id"], "error": str(res.get("error"))[:200]})
            continue

        parsed = res["parsed"]
        if existing:
            await proj_db.execute(
                "UPDATE scenes SET place_asset_ref=?, shot=?, reasoning=?, "
                "status='draft', stale=0, updated_at=? WHERE beat_id=?",
                (parsed["place_ref"], parsed["shot"], parsed["reasoning"], now, beat["id"]))
        else:
            await proj_db.execute(
                "INSERT INTO scenes (beat_id, place_asset_ref, shot, reasoning, "
                "status, stale, created_at, updated_at) VALUES (?,?,?,?, 'draft', 0, ?, ?)",
                (beat["id"], parsed["place_ref"], parsed["shot"],
                 parsed["reasoning"], now, now))
            planned += 1

    await proj_db.commit()
    await proj_db.close()
    return {"planned": planned, "skipped_approved": skipped_approved,
            "failed": failed, "total_beats": len(beats)}


@router.put("/projects/{project_id}/scenes/{beat_id}")
async def edit_scene(project_id: str, beat_id: str, data: SceneEdit):
    """Manual row write — always allowed, even on approved rows."""
    if data.status is not None and data.status not in ("draft", "approved"):
        raise HTTPException(422, "status must be 'draft' or 'approved'")
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT id FROM beats WHERE id=? AND project_id=?",
                               (beat_id, project_id)) as cur:
        beat = await cur.fetchone()
    if not beat:
        await proj_db.close()
        raise HTTPException(404, "Beat not found")
    async with proj_db.execute("SELECT * FROM scenes WHERE beat_id=?", (beat_id,)) as cur:
        existing = await cur.fetchone()
    now = _now()
    if existing:
        row = dict(existing)
        await proj_db.execute(
            "UPDATE scenes SET place_asset_ref=?, shot=?, reasoning=?, status=?, updated_at=? "
            "WHERE beat_id=?",
            (data.place_asset_ref if data.place_asset_ref is not None else row["place_asset_ref"],
             data.shot if data.shot is not None else row["shot"],
             data.reasoning if data.reasoning is not None else row["reasoning"],
             data.status if data.status is not None else row["status"],
             now, beat_id))
    else:
        await proj_db.execute(
            "INSERT INTO scenes (beat_id, place_asset_ref, shot, reasoning, "
            "status, stale, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (beat_id, data.place_asset_ref, data.shot or "", data.reasoning or "",
             data.status or "draft", 0, now, now))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "saved"}


@router.get("/projects/{project_id}/scenes")
async def list_scenes(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT s.* FROM scenes s JOIN beats b ON b.id=s.beat_id "
        "WHERE b.project_id=? ORDER BY b.sort_order", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    return rows
