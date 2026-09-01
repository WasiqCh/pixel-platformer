# backend/api/titles.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
import json

from backend.db.connection import get_app_db, get_project_db
from backend.core.llm_client import dispatch
from backend.models.title import TitleGenResult

router = APIRouter(tags=["titles"])

class GenerateTitlesRequest(BaseModel):
    count: int = 10

async def _get_proj_info(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]

async def _get_current_idea(folder: str, project_id: str) -> dict:
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT content FROM idea_cards WHERE project_id=? AND is_current=1 ORDER BY id DESC LIMIT 1", (project_id,)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    if not row: return {}
    return json.loads(row["content"])

@router.post("/projects/{project_id}/titles/generate")
async def generate_titles(project_id: str, req: GenerateTitlesRequest):
    folder, ch_id = await _get_proj_info(project_id)
    idea = await _get_current_idea(folder, project_id)
    if not idea:
        raise HTTPException(400, "No idea card found. Generate an idea first.")
        
    context = {
        "idea_card": idea,
        "channel_tone": "dramatic, playful", # TODO: fetch from channel kit later
        "past_titles": [], 
        "count": req.count
    }
    
    result = await dispatch("title_gen", context, schema=TitleGenResult, project_id=project_id, channel_id=ch_id)
    if not result["ok"]:
        raise HTTPException(500, result.get("error", "AI failed"))
        
    proj_db = await get_project_db(folder)
    now = datetime.now(timezone.utc).isoformat()
    
    for t in result["parsed"]["titles"]:
        await proj_db.execute(
            "INSERT INTO titles (project_id, text, angle, style_tag, char_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, t["text"], t["angle"], t["style_tag"], len(t["text"]), now, now)
        )
    await proj_db.commit()
    await proj_db.close()
    
    return {"status": "generated", "count": len(result["parsed"]["titles"])}

@router.get("/projects/{project_id}/titles")
async def list_titles(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM titles WHERE project_id=? ORDER BY id DESC", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    return rows

@router.post("/titles/{title_id}/lock")
async def lock_title(title_id: int, project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    now = datetime.now(timezone.utc).isoformat()
    
    # Lock this title
    await proj_db.execute("UPDATE titles SET locked=1, updated_at=? WHERE id=? AND project_id=?", (now, title_id, project_id))
    await proj_db.commit()
    await proj_db.close()
    
    # Update project stage in global DB
    app_db = await get_app_db()
    await app_db.execute("UPDATE projects SET stage='title', updated_at=? WHERE id=?", (now, project_id))
    await app_db.commit()
    await app_db.close()
    
    return {"status": "locked"}