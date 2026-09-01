# backend/api/projects.py
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from backend.db.connection import get_app_db, get_project_db
from backend.db.migrations import init_project_db
from backend.core.id_generator import IDGenerator
from backend.storage.fs_manager import create_project_dirs

router = APIRouter(tags=["projects"])

class ProjectCreate(BaseModel):
    slug: str

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
    ep_suffix = await gen.mint_project(ch_id) # e.g., "EP01"
    proj_id = f"{ch_id}_{ep_suffix}"          # e.g., "CH01_EP01"
    now = datetime.now(timezone.utc).isoformat()
    
    # 1. Save to Global DB
    await db.execute(
        "INSERT INTO projects (id, channel_id, slug, folder_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (proj_id, ch_id, data.slug, proj_id, now, now)
    )
    await db.commit()
    await db.close()
    
    # 2. Create Folders (pass suffix "EP01" so fs_manager builds "CH01_EP01")
    create_project_dirs(ch_id, ep_suffix)
    
    # 3. Init Project DB
    proj_db = await get_project_db(proj_id)
    await init_project_db(proj_db)
    await proj_db.close()
    
    return {"id": proj_id, "slug": data.slug}