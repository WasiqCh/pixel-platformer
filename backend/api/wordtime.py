# backend/api/wordtime.py — word timings for timed layers (Phase 2, general).
#
# POST .../wordtime/align {beat_id?|all, model} transcribes beat WAV(s)
# (08_export/voiceover) and force-aligns onto the locked beat text via
# backend/core/wordtime.py (system whisper CLI, no venv models, no keys).
# Results REPLACE beat_words rows (never append). GET fetches them.
# No LLM calls anywhere on this router.

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.wordtime import align_wav
from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["wordtime"])


class AlignRequest(BaseModel):
    beat_id: Optional[str] = None
    model: str = "base"


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _proj(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute(
            "SELECT folder_name, channel_id FROM projects WHERE id=?",
            (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


@router.post("/projects/{project_id}/wordtime/align")
async def align_words(project_id: str, req: AlignRequest):
    folder, ch_id = await _proj(project_id)
    proj_db = await get_project_db(folder)
    try:
        if req.beat_id:
            async with proj_db.execute(
                    "SELECT id, text FROM beats WHERE id=? AND project_id=?",
                    (req.beat_id, project_id)) as cur:
                row = await cur.fetchone()
            if not row:
                raise HTTPException(404, "Beat not found")
            beats = [dict(row)]
        else:
            async with proj_db.execute(
                    "SELECT id, text FROM beats WHERE project_id=? AND stale=0 "
                    "ORDER BY sort_order", (project_id,)) as cur:
                beats = [dict(r) for r in await cur.fetchall()]
        if not beats:
            raise HTTPException(400, "No beats to align.")
        base = get_project_dir(ch_id, folder.split("_")[1])
        vo_dir = base / "08_export" / "voiceover"
        out, now = [], _now()
        for b in beats:
            wav = vo_dir / f"{b['id']}.wav"
            if not wav.exists() or wav.stat().st_size == 0:
                out.append({"beat_id": b["id"], "status": "skipped",
                            "error": "WAV missing — build voiceover first"})
                continue
            try:
                words, stats = align_wav(str(wav), b["text"] or "",
                                         model=req.model or "base")
            except (FileNotFoundError, RuntimeError) as e:
                out.append({"beat_id": b["id"], "status": "error",
                            "error": str(e)[:200]})
                continue
            await proj_db.execute("DELETE FROM beat_words WHERE beat_id=?",
                                  (b["id"],))
            for i, w in enumerate(words):
                await proj_db.execute(
                    "INSERT INTO beat_words (beat_id, idx, word, start_sec, "
                    "end_sec, source, created_at) VALUES (?,?,?,?,?,?,?)",
                    (b["id"], i, w["word"], w["start"], w["end"],
                     "whisper", now))
            out.append({"beat_id": b["id"], "status": "aligned",
                        "words": len(words), **stats})
        await proj_db.commit()
        return {"aligned": [o for o in out if o["status"] == "aligned"],
                "skipped": [o for o in out if o["status"] != "aligned"],
                "total_beats": len(beats)}
    finally:
        await proj_db.close()


@router.get("/projects/{project_id}/wordtime/{beat_id}")
async def get_words(project_id: str, beat_id: str):
    folder, _ = await _proj(project_id)
    proj_db = await get_project_db(folder)
    try:
        async with proj_db.execute(
                "SELECT idx, word, start_sec, end_sec FROM beat_words "
                "WHERE beat_id=? ORDER BY idx", (beat_id,)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
        return {"beat_id": beat_id, "words": rows}
    finally:
        await proj_db.close()
