# backend/api/llm.py
from fastapi import APIRouter
from backend.core.llm_client import dispatch
from backend.models.title import TitleGenResult
from backend.db.connection import get_app_db

router = APIRouter(tags=["llm"])

@router.post("/llm/test")
async def llm_test():
    """Smoke test: runs a real title_gen job through the full dispatcher."""
    context = {
        "idea_card": {"concept": "The rise and fall of the Apple logo",
                      "hooks": [], "tags": ["business"]},
        "channel_tone": "dramatic, playful",
        "past_titles": [],
        "count": 5,
    }
    return await dispatch("title_gen", context, schema=TitleGenResult)

@router.get("/llm/jobs")
async def recent_jobs():
    """Transparency: last 10 job_log entries."""
    db = await get_app_db()
    async with db.execute(
        "SELECT id, job_type, model, temperature, error, duration_ms, created_at "
        "FROM job_log ORDER BY id DESC LIMIT 10") as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return rows