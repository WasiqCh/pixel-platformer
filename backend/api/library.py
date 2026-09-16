# backend/api/library.py
from datetime import datetime, timezone
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["library"])


class LibraryUpdate(BaseModel):
    notes: Optional[str] = None
    status: Optional[str] = None


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _next_id(proj_db, prefix="LIB"):
    async with proj_db.execute("SELECT id FROM library WHERE id LIKE ?", (prefix + "%",)) as cur:
        ids = [r["id"] for r in await cur.fetchall()]
    nums = [int(x[len(prefix):]) for x in ids if x[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) + 1) if nums else 1:02d}"


async def _get_proj_info(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


@router.post("/projects/{project_id}/library/scaffold")
async def scaffold_library(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    now = _now()
    created = 0
    reused = 0
    base = get_project_dir(ch_id, folder.split("_")[1])
    from pathlib import Path
    from backend.core.vault import vault_get, vault_dir, asset_key

    async with proj_db.execute("SELECT id, names FROM characters WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        chars = [(r["id"], json.loads(r["names"])[0]) for r in await cur.fetchall()]
    async with proj_db.execute("SELECT id, name FROM environments WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        envs = [(r["id"], r["name"]) for r in await cur.fetchall()]
    async with proj_db.execute("SELECT id, text FROM world_records WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        worlds = [(r["id"], r["text"]) for r in await cur.fetchall()]

    items = ([("character", c, n) for c, n in chars] +
             [("environment", e, n) for e, n in envs] +
             [("world", w, n) for w, n in worlds])

    for kind, ref, title in items:
        async with proj_db.execute("SELECT id FROM library WHERE project_id=? AND asset_ref=?", (project_id, ref)) as cur:
            if await cur.fetchone():
                continue
        lib_id = await _next_id(proj_db)
        await proj_db.execute(
            "INSERT INTO library (id, project_id, kind, asset_ref, title, file_path, source, status, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, '', 'manual', 'empty', '', ?, ?)",
            (lib_id, project_id, kind, ref, title, now, now))
        if kind == "character":
            await proj_db.execute("UPDATE characters SET library_ref=? WHERE id=?", (lib_id, ref))
        elif kind == "environment":
            await proj_db.execute("UPDATE environments SET library_ref=? WHERE id=?", (lib_id, ref))
        # world link lives on library.asset_ref (world_records has no library_ref column)

        vrow = await vault_get(ch_id, asset_key(title))
        if vrow:
            vfile = vault_dir(ch_id) / Path(vrow["file_path"]).name
            if vfile.exists():
                relv = f"06_assets/library/{lib_id}_vault{vfile.suffix}"
                (base / relv).parent.mkdir(parents=True, exist_ok=True)
                (base / relv).write_bytes(vfile.read_bytes())
                await proj_db.execute("UPDATE library SET file_path=?, status='ready', source='channel', updated_at=? WHERE id=?",
                                      (relv, now, lib_id))
                reused += 1
        created += 1

    await proj_db.commit()
    await proj_db.close()
    return {"created": created, "reused": reused}


@router.get("/projects/{project_id}/library")
async def list_library(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM library WHERE project_id=? ORDER BY kind, id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    async with proj_db.execute("SELECT id, search_query, era_hint FROM world_records WHERE project_id=?", (project_id,)) as cur:
        winfo = {r["id"]: (r["search_query"] or "", r["era_hint"] or "") for r in await cur.fetchall()}
    for r in rows:
        if r["kind"] == "world":
            r["search_query"], r["era_hint"] = winfo.get(r["asset_ref"], ("", ""))
    await proj_db.close()
    return rows


@router.post("/projects/{project_id}/library/{lib_id}/upload")
async def upload_asset(project_id: str, lib_id: str, file: UploadFile = File(...)):
    folder, ch_id = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM library WHERE id=? AND project_id=?", (lib_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close()
        raise HTTPException(404, "Library item not found")

    lib_dir = get_project_dir(ch_id, folder.split("_")[1]) / "06_assets" / "library"
    lib_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{lib_id}_{(file.filename or 'asset.bin').replace(' ', '_')}"
    (lib_dir / safe_name).write_bytes(await file.read())

    rel = f"06_assets/library/{safe_name}"
    await proj_db.execute(
        "UPDATE library SET file_path=?, status='ready', source='manual', updated_at=? WHERE id=?",
        (rel, _now(), lib_id))
    if row["kind"] == "world" and row["asset_ref"]:
        await proj_db.execute(
            "UPDATE world_records SET provenance=?, updated_at=? WHERE id=?",
            (rel, _now(), row["asset_ref"]))
    from backend.core.vault import vault_put, asset_key
    await vault_put(ch_id, asset_key(row["title"]), row["kind"], row["title"], lib_dir / safe_name, project_id)
    await proj_db.commit()
    await proj_db.close()
    return {"status": "ready", "file_path": rel}


@router.put("/projects/{project_id}/library/{lib_id}")
async def update_library(project_id: str, lib_id: str, data: LibraryUpdate):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    now = _now()
    if data.notes is not None:
        await proj_db.execute("UPDATE library SET notes=?, updated_at=? WHERE id=?", (data.notes, now, lib_id))
    if data.status is not None:
        await proj_db.execute("UPDATE library SET status=?, updated_at=? WHERE id=?", (data.status, now, lib_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "updated"}


@router.delete("/projects/{project_id}/library/{lib_id}")
async def delete_library(project_id: str, lib_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    await proj_db.execute("UPDATE characters SET library_ref=NULL WHERE library_ref=?", (lib_id,))
    await proj_db.execute("UPDATE environments SET library_ref=NULL WHERE library_ref=?", (lib_id,))
    await proj_db.execute("DELETE FROM library WHERE id=? AND project_id=?", (lib_id, project_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "deleted"}


@router.get("/channels/{channel_id}/vault")
async def list_vault(channel_id: str):
    db = await get_app_db()
    async with db.execute("SELECT * FROM channel_library WHERE channel_id=? ORDER BY kind, title", (channel_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return rows
