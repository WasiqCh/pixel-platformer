# backend/api/world.py
from datetime import datetime, timezone
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.id_generator import IDGenerator
from backend.core.sharding import sharded_extract
from backend.db.connection import get_app_db, get_project_db
from backend.models.world_record import WorldScanResult
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["world"])


class StatusUpdate(BaseModel):
    status: str  # pending | approved | dismissed

class PolicyUpdate(BaseModel):
    meme_mode: bool

class WorldEdit(BaseModel):
    search_query: Optional[str] = None
    era_hint: Optional[str] = None
    usage_intent: Optional[str] = None
    map_template: Optional[str] = None


async def _meme_on(channel_id: str) -> bool:
    db = await get_app_db()
    async with db.execute("SELECT meme_mode FROM channel_policy WHERE channel_id=?", (channel_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await db.execute("INSERT INTO channel_policy (channel_id, meme_mode) VALUES (?,1)", (channel_id,))
        await db.commit()
        await db.close()
        return True
    await db.close()
    return bool(row["meme_mode"])


@router.get("/channels/{channel_id}/policy")
async def get_policy(channel_id: str):
    return {"meme_mode": await _meme_on(channel_id)}


@router.put("/channels/{channel_id}/policy")
async def put_policy(channel_id: str, data: PolicyUpdate):
    await _meme_on(channel_id)
    db = await get_app_db()
    await db.execute("UPDATE channel_policy SET meme_mode=? WHERE channel_id=?",
                     (1 if data.meme_mode else 0, channel_id))
    async with db.execute("SELECT id, folder_name FROM projects WHERE channel_id=?", (channel_id,)) as cur:
        prows = [dict(r) for r in await cur.fetchall()]
    await db.commit()
    await db.close()
    for p in prows:
        pdb = await get_project_db(p["folder_name"])
        if data.meme_mode:
            await pdb.execute("UPDATE world_records SET stale=0 WHERE project_id=? AND type='meme'", (p["id"],))
        else:
            await pdb.execute("UPDATE world_records SET stale=1 WHERE project_id=? AND type='meme'", (p["id"],))
        await pdb.commit()
        await pdb.close()
    return {"meme_mode": bool(data.meme_mode)}


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


def _merge_world(a: dict, b: dict) -> dict:
    by_text = {}
    for item in a["records"] + b["records"]:
        key = item["text"].strip().lower()
        if key not in by_text:
            by_text[key] = dict(item)
        else:
            cur = by_text[key]
            for f in ("search_query", "era_hint", "map_template", "script_context"):
                if not cur.get(f) and item.get(f):
                    cur[f] = item[f]
    return {"records": list(by_text.values())}


def _write_world_mirror(ch_id, folder, rows):
    world_dir = get_project_dir(ch_id, folder.split("_")[1]) / "05_world"
    world_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# World Records", ""]
    for r in rows:
        lines.append(f"## {r['id']} — {r['text']} [{r['type']}] status={r['status']}")
        lines.append(f"intent: {r['usage_intent']} · query: {r['search_query']} · era: {r['era_hint']}")
        if r["map_template"]:
            lines.append(f"map_template: {r['map_template']}")
        lines.append(f"context: {r['script_context']}")
        lines.append("")
    (world_dir / "world_records.md").write_text("\n".join(lines), encoding="utf-8")


@router.post("/projects/{project_id}/world/scan")
async def scan_world(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    script = await _get_locked_script(folder, project_id)
    if not script:
        raise HTTPException(400, "Lock a script first (Script Studio -> Lock).")

    parsed, res = None, None
    for attempt in range(3):
        parsed, res = await sharded_extract(
            "world_scan", WorldScanResult, {"channel_id": ch_id}, script, _merge_world,
            project_id=project_id, channel_id=ch_id)
        if parsed is not None:
            break
        err = str(res.get("error", ""))
        if not any(k in err for k in ("Expecting value", "Unterminated", "Invalid", "JSON")):
            break
        await asyncio.sleep(3)
    if parsed is None:
        raise HTTPException(500,
            "The AI gateway returned an empty or broken answer (temporary rate limiting). "
            "Wait ~30 seconds and click again - nothing was lost. Raw: " + str(res.get("error"))[:200])

    proj_db = await get_project_db(folder)
    gen = IDGenerator(proj_db)
    now = _now()

    async with proj_db.execute("SELECT * FROM world_records WHERE project_id=?", (project_id,)) as cur:
        existing = {r["text"].strip().lower(): dict(r) for r in await cur.fetchall()}

    seen, added, updated = set(), 0, 0
    for item in parsed["records"]:
        key = item["text"].strip().lower()
        seen.add(key)
        if key in existing:
            row = existing[key]
            await proj_db.execute(
                "UPDATE world_records SET type=?, script_context=?, usage_intent=?, search_query=?, "
                "era_hint=?, map_template=?, stale=0, updated_at=? WHERE id=?",
                (item["type"], item["script_context"], item["usage_intent"], item["search_query"],
                 item["era_hint"], item["map_template"], now, row["id"]))
            updated += 1
        else:
            prefix = "MT" if item["type"] == "map_trigger" else "RW"
            rec_id = await gen.mint_rw_or_mt(prefix)
            await proj_db.execute(
                "INSERT INTO world_records (id, project_id, type, text, script_context, usage_intent, "
                "search_query, era_hint, map_template, status, role_tag, stale, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'world', 0, ?, ?)",
                (rec_id, project_id, item["type"], item["text"], item["script_context"],
                 item["usage_intent"], item["search_query"], item["era_hint"],
                 item["map_template"], now, now))
            added += 1

    staled = 0
    for key, row in existing.items():
        if key not in seen and not row["stale"] and row["role_tag"] != "character":
            await proj_db.execute("UPDATE world_records SET stale=1, updated_at=? WHERE id=?", (now, row["id"]))
            staled += 1

    await proj_db.commit()

    if not await _meme_on(ch_id):
        await proj_db.execute("UPDATE world_records SET stale=1 WHERE project_id=? AND type='meme'", (project_id,))

    async with proj_db.execute(
        "SELECT * FROM world_records WHERE project_id=? AND stale=0 ORDER BY type, id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()

    _write_world_mirror(ch_id, folder, rows)
    return {"added": added, "updated": updated, "staled": staled, "total": len(rows)}


@router.get("/projects/{project_id}/world")
async def list_world(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT * FROM world_records WHERE project_id=? AND stale=0 ORDER BY type, id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    return rows


@router.put("/projects/{project_id}/world/{rec_id}/status")
async def set_status(project_id: str, rec_id: str, data: StatusUpdate):
    if data.status not in ("pending", "approved", "dismissed"):
        raise HTTPException(422, "status must be pending, approved or dismissed")
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    await proj_db.execute("UPDATE world_records SET status=?, updated_at=? WHERE id=? AND project_id=?",
                          (data.status, _now(), rec_id, project_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "updated"}


@router.put("/projects/{project_id}/world/{rec_id}")
async def edit_world(project_id: str, rec_id: str, data: WorldEdit):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    now = _now()
    if data.search_query is not None:
        await proj_db.execute("UPDATE world_records SET search_query=?, updated_at=? WHERE id=?", (data.search_query, now, rec_id))
    if data.era_hint is not None:
        await proj_db.execute("UPDATE world_records SET era_hint=?, updated_at=? WHERE id=?", (data.era_hint, now, rec_id))
    if data.usage_intent is not None:
        await proj_db.execute("UPDATE world_records SET usage_intent=?, updated_at=? WHERE id=?", (data.usage_intent, now, rec_id))
    if data.map_template is not None:
        await proj_db.execute("UPDATE world_records SET map_template=?, updated_at=? WHERE id=?", (data.map_template, now, rec_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "edited"}


@router.delete("/projects/{project_id}/world/{rec_id}")
async def delete_world(project_id: str, rec_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    await proj_db.execute("DELETE FROM world_records WHERE id=? AND project_id=?", (rec_id, project_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "deleted"}
