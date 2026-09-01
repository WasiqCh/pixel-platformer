# backend/api/scripts.py
from datetime import datetime, timezone
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.core.llm_client import dispatch, dispatch_stream
from backend.db.connection import get_app_db, get_project_db
from backend.models.script import OutlineResult
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["scripts"])


class OutlineRequest(BaseModel):
    target_words: int


class LockRequest(BaseModel):
    text: str
    word_count: int


async def _get_proj_info(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


async def _get_locked_title(folder: str, project_id: str) -> str:
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT text FROM titles WHERE project_id=? AND locked=1 LIMIT 1", (project_id,)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    return row["text"] if row else "Untitled Video"


async def _get_current_idea(folder: str, project_id: str) -> dict:
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT content FROM idea_cards WHERE project_id=? AND is_current=1 ORDER BY id DESC LIMIT 1",
        (project_id,),
    ) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    return json.loads(row["content"]) if row else {}


@router.post("/projects/{project_id}/script/outline")
async def generate_outline(project_id: str, req: OutlineRequest):
    folder, ch_id = await _get_proj_info(project_id)
    title = await _get_locked_title(folder, project_id)
    idea = await _get_current_idea(folder, project_id)

    context = {
        "idea_card": idea,
        "title": title,
        "channel_tone": "dramatic, playful",
        "target_word_count": req.target_words,
    }

    result = await dispatch("script_outline", context, schema=OutlineResult,
                            project_id=project_id, channel_id=ch_id)
    if not result["ok"]:
        raise HTTPException(500, result.get("error", "AI failed to build outline"))
    return result["parsed"]


@router.post("/projects/{project_id}/script/draft")
async def stream_draft(project_id: str, outline: OutlineResult):
    folder, ch_id = await _get_proj_info(project_id)
    title = await _get_locked_title(folder, project_id)
    idea = await _get_current_idea(folder, project_id)

    context = {
        "idea_card": idea,
        "title": title,
        "channel_tone": "dramatic, playful",
        "outline": [s.model_dump() for s in outline.sections],
        "target_words": sum(s.target_words for s in outline.sections),
    }

    return StreamingResponse(
        dispatch_stream("script_draft", context, project_id=project_id, channel_id=ch_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/projects/{project_id}/script/lock")
async def lock_script(project_id: str, req: LockRequest):
    folder, ch_id = await _get_proj_info(project_id)
    now = datetime.now(timezone.utc).isoformat()
    duration_sec = (req.word_count / 150.0) * 60.0

    # 1. Save to project DB
    proj_db = await get_project_db(folder)
    await proj_db.execute(
        "INSERT INTO scripts (project_id, text, word_count, duration_sec, locked, locked_at, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?, ?)",
        (project_id, req.text, req.word_count, duration_sec, now, now),
    )
    await proj_db.commit()
    await proj_db.close()

    # 2. File mirror (files-first principle)
    script_dir = get_project_dir(ch_id, folder.split("_")[1]) / "03_script"
    script_dir.mkdir(parents=True, exist_ok=True)
    (script_dir / "locked_v1.md").write_text(req.text, encoding="utf-8")

    # 3. Advance project stage
    app_db = await get_app_db()
    await app_db.execute("UPDATE projects SET stage='script', updated_at=? WHERE id=?", (now, project_id))
    await app_db.commit()
    await app_db.close()

    return {"status": "locked", "duration_sec": duration_sec}