# backend/api/projects.py
import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import DATA_DIR
from backend.core.id_generator import IDGenerator
from backend.db.connection import get_app_db, get_project_db
from backend.db.migrations import init_project_db
from backend.storage.fs_manager import create_project_dirs

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    slug: str


class ProjectRename(BaseModel):
    slug: str


def _now():
    return datetime.now(timezone.utc).isoformat()


@router.get("/channels/{ch_id}/projects")
async def list_projects(ch_id: str):
    db = await get_app_db()
    async with db.execute("SELECT * FROM projects WHERE channel_id = ? ORDER BY created_at DESC", (ch_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return rows


@router.post("/channels/{ch_id}/projects")
async def create_project(ch_id: str, data: ProjectCreate):
    db = await get_app_db()
    gen = IDGenerator(db)
    ep_suffix = await gen.mint_project(ch_id)
    proj_id = f"{ch_id}_{ep_suffix}"
    now = _now()

    await db.execute(
        "INSERT INTO projects (id, channel_id, slug, folder_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (proj_id, ch_id, data.slug, proj_id, now, now),
    )
    await db.commit()
    await db.close()

    create_project_dirs(ch_id, ep_suffix)
    proj_db = await get_project_db(proj_id)
    await init_project_db(proj_db)
    await proj_db.close()
    return {"id": proj_id, "slug": data.slug}


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    db = await get_app_db()
    async with db.execute("SELECT * FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(row)


# P-01: rename touches slug ONLY — folder path never changes
@router.put("/projects/{project_id}")
async def rename_project(project_id: str, data: ProjectRename):
    db = await get_app_db()
    await db.execute("UPDATE projects SET slug=?, updated_at=? WHERE id=?", (data.slug, _now(), project_id))
    await db.commit()
    await db.close()
    return {"status": "renamed"}


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    db = await get_app_db()
    async with db.execute("SELECT folder_name FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    await db.commit()
    await db.close()
    if row:
        folder = DATA_DIR / "projects" / row["folder_name"]
        if folder.exists():
            shutil.rmtree(folder)
    return {"status": "deleted"}


@router.post("/projects/{project_id}/duplicate")
async def duplicate_project(project_id: str, data: ProjectCreate):
    db = await get_app_db()
    async with db.execute("SELECT * FROM projects WHERE id=?", (project_id,)) as cur:
        src = await cur.fetchone()
    if not src:
        await db.close()
        raise HTTPException(404, "Source project not found")

    gen = IDGenerator(db)
    ep_suffix = await gen.mint_project(src["channel_id"])
    new_id = f"{src['channel_id']}_{ep_suffix}"
    now = _now()

    await db.execute(
        "INSERT INTO projects (id, channel_id, slug, folder_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (new_id, src["channel_id"], data.slug, new_id, now, now),
    )
    await db.commit()
    await db.close()

    create_project_dirs(src["channel_id"], ep_suffix)
    new_db = await get_project_db(new_id)
    await init_project_db(new_db)

    src_db = await get_project_db(src["folder_name"])
    async with src_db.execute("SELECT content, channel_id FROM idea_cards WHERE project_id=? AND is_current=1", (project_id,)) as cur:
        for i in await cur.fetchall():
            await new_db.execute(
                "INSERT INTO idea_cards (project_id, channel_id, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (new_id, i["channel_id"], i["content"], now, now))
    async with src_db.execute("SELECT text, angle, style_tag, char_count, locked FROM titles WHERE project_id=?", (project_id,)) as cur:
        for t in await cur.fetchall():
            await new_db.execute(
                "INSERT INTO titles (project_id, text, angle, style_tag, char_count, locked, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id, t["text"], t["angle"], t["style_tag"], t["char_count"], t["locked"], now, now))
    async with src_db.execute("SELECT text, word_count, duration_sec, locked FROM scripts WHERE project_id=? AND locked=1", (project_id,)) as cur:
        for s in await cur.fetchall():
            await new_db.execute(
                "INSERT INTO scripts (project_id, text, word_count, duration_sec, locked, locked_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id, s["text"], s["word_count"], s["duration_sec"], s["locked"], now, now))
    await new_db.commit()
    await new_db.close()
    await src_db.close()
    return {"id": new_id, "slug": data.slug}


@router.post("/projects/scan")
async def scan_projects():
    """Reconcile data/projects/ with DB: recover folders, remove ghosts."""
    db = await get_app_db()
    added, removed = [], []
    projects_dir = DATA_DIR / "projects"

    async with db.execute("SELECT id FROM projects") as cur:
        known = {r["id"] for r in await cur.fetchall()}

    if projects_dir.exists():
        for folder in sorted(projects_dir.iterdir()):
            if not folder.is_dir() or len(folder.name.split("_")) != 2:
                continue
            ch_id = folder.name.split("_")[0]
            if folder.name not in known:
                try:
                    now = _now()
                    await db.execute(
                        "INSERT INTO projects (id, channel_id, slug, folder_name, stage, created_at, updated_at) VALUES (?, ?, ?, ?, 'idea', ?, ?)",
                        (folder.name, ch_id, folder.name, folder.name, now, now))
                    added.append(folder.name)
                except Exception:
                    pass  # channel row missing — skip silently

    async with db.execute("SELECT id, folder_name FROM projects") as cur:
        rows = await cur.fetchall()
    for r in rows:
        if not (projects_dir / r["folder_name"]).exists():
            await db.execute("DELETE FROM projects WHERE id=?", (r["id"],))
            removed.append(r["id"])

    await db.commit()
    await db.close()
    return {"added": added, "removed": removed}