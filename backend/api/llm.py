# backend/api/llm.py
from fastapi import APIRouter
from backend.core.llm_client import dispatch
from backend.models.title import TitleGenResult
from backend.db.connection import get_app_db
from fastapi.responses import StreamingResponse
from backend.core.llm_client import dispatch_stream

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

@router.post("/llm/stream-test")
async def stream_test():
    """Temporary dev endpoint: proves streaming end-to-end with a tiny draft."""
    context = {
        "idea_card": {"concept": "The 2021 Facebook outage: six hours the internet went dark",
                      "hooks": [], "tags": ["tech"]},
        "title": "The Day The Internet Died",
        "channel_tone": "dramatic, playful",
        "outline": [
            {"heading": "Hook", "summary": "open mid-outage, phones going silent", "target_words": 60, "role": "hook"},
            {"heading": "The Fall", "summary": "cascade of failures across the world", "target_words": 60, "role": "build"},
        ],
        "target_words": 120,
    }
    return StreamingResponse(
        dispatch_stream("script_draft", context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )