# backend/api/characters.py
import asyncio
from datetime import datetime, timezone
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.id_generator import IDGenerator
from backend.core.sharding import sharded_extract
from backend.core.sheet_layout import CHAR_ACTIONS_PER_SHEET
from backend.db.connection import get_app_db, get_project_db
from backend.models.character import CharacterExtractResult
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["characters"])


class CharacterEdit(BaseModel):
    names: Optional[List[str]] = None
    appearance: Optional[str] = None
    faction: Optional[str] = None
    kind: Optional[str] = None

class SignificanceUpdate(BaseModel):
    significance: str

class RenderUpdate(BaseModel):
    render: str


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


def _merge_characters(a: dict, b: dict) -> dict:
    """§4.6 shard merge: dedupe by name, union aliases/presence, keep top significance."""
    by_name = {}
    for item in a["characters"] + b["characters"]:
        key = item["name"].strip().lower()
        if key in by_name:
            cur = by_name[key]
            cur["aliases"] = list(dict.fromkeys(cur["aliases"] + item["aliases"]))
            cur["presence_sections"] = list(dict.fromkeys(cur["presence_sections"] + item["presence_sections"]))
            cur["world_annotations"] = list(dict.fromkeys(cur["world_annotations"] + item["world_annotations"]))
            cur["green_conflict"] = bool(cur["green_conflict"] or item["green_conflict"])
            rank = {"minor": 0, "supporting": 1, "core": 2}
            if rank.get(item["significance"], 0) > rank.get(cur["significance"], 0):
                cur["significance"] = item["significance"]
        else:
            by_name[key] = dict(item)
    return {"characters": list(by_name.values()), "mentions": a["mentions"] + b["mentions"]}


def _write_cast_mirror(ch_id, folder, rows, mentions):
    cast_dir = get_project_dir(ch_id, folder.split("_")[1]) / "04_cast"
    cast_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Cast Manifest", ""]
    for r in rows:
        names = r["names"] if isinstance(r["names"], list) else json.loads(r["names"])
        lines.append(f"## {r['id']} — {names[0]} ({r['kind']}, {r['significance']}, {r['render']})")
        if len(names) > 1:
            lines.append(f"aliases: {', '.join(names[1:])}")
        lines.append(f"appearance: {r['appearance'] or 'TBD'}")
        if r["green_conflict"]:
            lines.append("⚠ green_conflict")
        lines.append("")
    (cast_dir / "characters.md").write_text("\n".join(lines), encoding="utf-8")

    mlines = ["# Mention Map", ""]
    for m in mentions:
        mlines.append(f"- \"{m['mention_text']}\" → {m['resolved_to']} @ {m['section'] or '?'} (conf {m['confidence']})")
    (cast_dir / "mentions.md").write_text("\n".join(mlines), encoding="utf-8")


@router.post("/projects/{project_id}/characters/extract")
async def extract_characters(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    script = await _get_locked_script(folder, project_id)
    if not script:
        raise HTTPException(400, "Lock a script first (Script Studio → Lock).")

    parsed, res = None, None
    for attempt in range(3):
        parsed, res = await sharded_extract(
            "character_extract", CharacterExtractResult,
            {"channel_id": ch_id}, script, _merge_characters,
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

    async with proj_db.execute("SELECT * FROM characters WHERE project_id=?", (project_id,)) as cur:
        existing = {}
        for r in await cur.fetchall():
            primary = json.loads(r["names"])[0].strip().lower()
            existing[primary] = dict(r)

    seen, added, updated = set(), 0, 0
    for item in parsed["characters"]:
        key = item["name"].strip().lower()
        seen.add(key)
        if key in existing:
            row = existing[key]
            await proj_db.execute(
                "UPDATE characters SET kind=?, faction=?, significance=?, presence=?, green_conflict=?, stale=0, updated_at=? WHERE id=?",
                (item["kind"], item["faction"], item["significance"],
                 json.dumps(item["presence_sections"]), 1 if item["green_conflict"] else 0,
                 now, row["id"]))
            # Only overwrite actions when the AI actually proposed some, so a
            # thin re-extract doesn't wipe previously chosen poses.
            if item.get("actions"):
                await proj_db.execute("UPDATE characters SET actions=? WHERE id=?",
                                      (json.dumps(item["actions"][:CHAR_ACTIONS_PER_SHEET]), row["id"]))
            updated += 1
        else:
            world_ref = None
            if item["render"] == "fetched":
                rw_id = await gen.mint_rw_or_mt("RW")
                await proj_db.execute(
                    "INSERT INTO world_records (id, project_id, type, text, usage_intent, status, role_tag, created_at, updated_at) "
                    "VALUES (?, ?, 'real_person', ?, 'on_screen_insert', 'pending', 'character', ?, ?)",
                    (rw_id, project_id, item["name"], now, now))
                world_ref = rw_id
            char_id = await gen.mint_character()
            await proj_db.execute(
                "INSERT INTO characters (id, project_id, kind, faction, render, names, appearance, significance, presence, green_conflict, world_record_ref, actions, stale, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (char_id, project_id, item["kind"], item["faction"], item["render"],
                 json.dumps([item["name"]] + item["aliases"]), item["appearance"],
                 item["significance"], json.dumps(item["presence_sections"]),
                 1 if item["green_conflict"] else 0, world_ref,
                 json.dumps((item.get("actions") or [])[:CHAR_ACTIONS_PER_SHEET]), now, now))
            added += 1

    staled = 0
    for key, row in existing.items():
        if key not in seen and not row["stale"]:
            await proj_db.execute("UPDATE characters SET stale=1, updated_at=? WHERE id=?", (now, row["id"]))
            staled += 1

    await proj_db.execute("DELETE FROM mentions WHERE project_id=?", (project_id,))
    for m in parsed["mentions"]:
        await proj_db.execute(
            "INSERT INTO mentions (project_id, section, mention_text, resolved_to, confidence, context, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, m["section"], m["text"], m["character_name"], m["confidence"], "", now))
    await proj_db.commit()

    async with proj_db.execute("SELECT * FROM characters WHERE project_id=? ORDER BY id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    async with proj_db.execute("SELECT * FROM mentions WHERE project_id=? ORDER BY id", (project_id,)) as cur:
        mrows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()

    _write_cast_mirror(ch_id, folder, rows, mrows)
    return {"added": added, "updated": updated, "staled": staled,
            "characters": len(rows), "mentions": len(mrows)}


@router.get("/projects/{project_id}/characters")
async def list_characters(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM characters WHERE project_id=? ORDER BY id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    for r in rows:
        r["names"] = json.loads(r["names"])
        r["presence"] = json.loads(r["presence"] or "[]")
    return rows


@router.get("/projects/{project_id}/mentions")
async def list_mentions(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM mentions WHERE project_id=? ORDER BY confidence DESC, id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    return rows


@router.put("/projects/{project_id}/characters/{char_id}")
async def edit_character(project_id: str, char_id: str, data: CharacterEdit):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    now = _now()
    if data.names is not None:
        await proj_db.execute("UPDATE characters SET names=?, updated_at=? WHERE id=? AND project_id=?",
                              (json.dumps(data.names), now, char_id, project_id))
    if data.appearance is not None:
        await proj_db.execute("UPDATE characters SET appearance=?, updated_at=? WHERE id=? AND project_id=?",
                              (data.appearance, now, char_id, project_id))
    if data.faction is not None:
        await proj_db.execute("UPDATE characters SET faction=?, updated_at=? WHERE id=? AND project_id=?",
                              (data.faction, now, char_id, project_id))
    if data.kind is not None:
        await proj_db.execute("UPDATE characters SET kind=?, updated_at=? WHERE id=? AND project_id=?",
                              (data.kind, now, char_id, project_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "edited"}


@router.put("/projects/{project_id}/characters/{char_id}/significance")
async def set_significance(project_id: str, char_id: str, data: SignificanceUpdate):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    await proj_db.execute("UPDATE characters SET significance=?, updated_at=? WHERE id=? AND project_id=?",
                          (data.significance, _now(), char_id, project_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "updated"}


@router.put("/projects/{project_id}/characters/{char_id}/render")
async def set_render(project_id: str, char_id: str, data: RenderUpdate):
    if data.render not in ("drawn", "fetched"):
        raise HTTPException(422, "render must be 'drawn' or 'fetched'")
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    now = _now()

    async with proj_db.execute("SELECT * FROM characters WHERE id=? AND project_id=?", (char_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close()
        raise HTTPException(404, "Character not found")

    world_ref = row["world_record_ref"]
    if data.render == "fetched" and not world_ref:
        gen = IDGenerator(proj_db)
        rw_id = await gen.mint_rw_or_mt("RW")
        names = json.loads(row["names"])
        await proj_db.execute(
            "INSERT INTO world_records (id, project_id, type, text, usage_intent, status, role_tag, created_at, updated_at) "
            "VALUES (?, ?, 'real_person', ?, 'on_screen_insert', 'pending', 'character', ?, ?)",
            (rw_id, project_id, names[0], now, now))
        world_ref = rw_id

    await proj_db.execute("UPDATE characters SET render=?, world_record_ref=?, updated_at=? WHERE id=?",
                          (data.render, world_ref, now, char_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "updated", "render": data.render, "world_record_ref": world_ref}
