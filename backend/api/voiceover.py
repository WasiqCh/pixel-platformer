# backend/api/voiceover.py
import asyncio
import base64
import wave
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["voiceover"])

_STATE = {"project": None, "done": 0, "total": 0}


class VoiceSettings(BaseModel):
    voice: Optional[str] = None
    enabled: Optional[bool] = None


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _get_vcfg():
    db = await get_app_db()
    async with db.execute("SELECT * FROM voice_settings WHERE id=1") as cur:
        row = await cur.fetchone()
    if not row:
        await db.execute("INSERT INTO voice_settings (id, voice, enabled, updated_at) VALUES (1,'Kore',1,'')")
        await db.commit()
        await db.close()
        return {"id": 1, "voice": "Kore", "enabled": 1, "updated_at": ""}
    await db.close()
    return dict(row)


@router.get("/settings/voice")
async def get_voice():
    return await _get_vcfg()


@router.put("/settings/voice")
async def put_voice(data: VoiceSettings):
    cfg = await _get_vcfg()
    db = await get_app_db()
    await db.execute("UPDATE voice_settings SET voice=?, enabled=?, updated_at=? WHERE id=1",
                     (data.voice or cfg["voice"],
                      cfg["enabled"] if data.enabled is None else (1 if data.enabled else 0),
                      _now()))
    await db.commit()
    await db.close()
    return {"status": "saved"}


async def _gemini_key():
    db = await get_app_db()
    async with db.execute("SELECT api_key FROM image_settings WHERE id=1") as cur:
        row = await cur.fetchone()
    await db.close()
    return row["api_key"] if row else ""


async def _tts(text, voice, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    async with httpx.AsyncClient(timeout=120) as cl:
        r = await cl.post(url, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"TTS HTTP {r.status_code}: {r.text[:150]}")
    data = r.json()
    for p in (data.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
        blob = p.get("inlineData") or p.get("inline_data")
        if blob:
            return base64.b64decode(blob["data"])
    raise RuntimeError("TTS returned no audio")


@router.post("/projects/{project_id}/voiceover/build")
async def build_voiceover(project_id: str):
    if _STATE["project"]:
        raise HTTPException(400, "A voiceover run is already in progress.")
    key = await _gemini_key()
    if not key:
        raise HTTPException(400, "Voiceover reuses your Gemini key — set it in Library ⚙️ first.")
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        prow = await cur.fetchone()
    await db.close()
    if not prow: raise HTTPException(404, "Project not found")
    asyncio.create_task(_run(project_id, prow["folder_name"], prow["channel_id"], key))
    return {"status": "started"}


@router.get("/projects/{project_id}/voiceover/status")
async def voiceover_status(project_id: str):
    return {"running": _STATE["project"] == project_id, "done": _STATE["done"], "total": _STATE["total"]}


async def _run(project_id, folder, ch_id, key):
    vcfg = await _get_vcfg()
    base = get_project_dir(ch_id, folder.split("_")[1])
    vo_dir = base / "08_export" / "voiceover"
    vo_dir.mkdir(parents=True, exist_ok=True)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT id, text FROM beats WHERE project_id=? AND stale=0 ORDER BY sort_order", (project_id,)) as cur:
        beats = [dict(b) for b in await cur.fetchall()]
    _STATE.update(project=project_id, done=0, total=len(beats))
    try:
        for b in beats:
            try:
                pcm = await _tts(b["text"], vcfg["voice"], key)
            except Exception:
                continue
            dur = len(pcm) / (24000 * 2)
            with wave.open(str(vo_dir / f"{b['id']}.wav"), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            await proj_db.execute("UPDATE beats SET duration_sec=?, updated_at=? WHERE id=?",
                                  (round(dur, 1), _now(), b["id"]))
            await proj_db.commit()
            _STATE["done"] += 1
            await asyncio.sleep(1)
    finally:
        await proj_db.close()
        _STATE["project"] = None