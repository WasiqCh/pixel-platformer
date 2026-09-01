# backend/api/ideation.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
import json

from backend.db.connection import get_app_db, get_project_db
from backend.core.llm_client import dispatch
from backend.models.idea import IdeaCard, SurpriseResult

router = APIRouter(tags=["ideation"])

class GenerateRequest(BaseModel):
    input: str

async def _get_proj_info(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]

@router.post("/projects/{project_id}/ideas/generate")
async def generate_idea(project_id: str, req: GenerateRequest):
    folder, ch_id = await _get_proj_info(project_id)
    
    context = {"raw_input": req.input, "channel_id": ch_id}
    result = await dispatch("ideation", context, schema=IdeaCard, project_id=project_id, channel_id=ch_id)
    
    if not result["ok"]:
        raise HTTPException(500, result.get("error", "AI failed to generate idea"))
        
    proj_db = await get_project_db(folder)
    now = datetime.now(timezone.utc).isoformat()
    content_json = json.dumps(result["parsed"])
    
    # Mark old cards as not current
    await proj_db.execute("UPDATE idea_cards SET is_current=0 WHERE project_id=? AND is_current=1", (project_id,))
    
    cur = await proj_db.execute(
        "INSERT INTO idea_cards (project_id, channel_id, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (project_id, ch_id, content_json, now, now)
    )
    await proj_db.commit()
    new_id = cur.lastrowid
    await proj_db.close()
    
    return {"id": new_id, "content": result["parsed"]}

@router.post("/channels/{ch_id}/ideas/surprise")
async def surprise_me(ch_id: str):
    context = {"channel_id": ch_id}
    result = await dispatch("surprise_me", context, schema=SurpriseResult, channel_id=ch_id)
    if not result["ok"]:
        raise HTTPException(500, result.get("error", "AI failed to generate surprises"))
    return result["parsed"]

@router.get("/projects/{project_id}/ideas")
async def list_ideas(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM idea_cards WHERE project_id=? ORDER BY id DESC", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    
    for r in rows:
        r["content"] = json.loads(r["content"])
    return rows