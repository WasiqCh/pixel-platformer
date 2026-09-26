# backend/api/voiceover.py
import asyncio
import base64
import os
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

# SCENES-MP4 D4-T02: local Kokoro voice (owner priority). Default stays Gemini;
# Kokoro is offered only when its deps import cleanly (see kokoro-status
# endpoint). Voice names differ per provider — stored per-provider, never mixed.
_KOKORO_DEFAULT_VOICE = "af_heart"
# D4-T01 verified locations (defaults-to-verify, never the only path — env
# KOKORO_MODEL / KOKORO_VOICES override; existence is always verified, never
# assumed). See docs/scenes-mp4/DECISION_KOKORO.md.
_KOKORO_DEFAULT_MODEL = r"C:\Users\wasiq\Downloads\Kokoro\kokoro-v1.0.onnx"
_KOKORO_DEFAULT_VOICES = r"C:\Users\wasiq\Downloads\Kokoro\voices-v1.0.bin"
# Model cache: one Kokoro instance per (model_path, voices_path). Model load is
# ~1s on CPU — the per-beat loop reuses it (same WAV contract, same pacing).
_KOKORO_CACHE: dict = {"key": None, "kokoro": None}


class VoiceSettings(BaseModel):
    voice: Optional[str] = None
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    kokoro_voice: Optional[str] = None


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _ensure_voice_cols(db):
    """Heal old app.db files (same discipline as migrations._ensure_column)."""
    async with db.execute("PRAGMA table_info(voice_settings)") as cur:
        cols = {r["name"] for r in await cur.fetchall()}
    if "provider" not in cols:
        await db.execute("ALTER TABLE voice_settings ADD COLUMN provider TEXT NOT NULL DEFAULT 'gemini'")
    if "kokoro_voice" not in cols:
        await db.execute("ALTER TABLE voice_settings ADD COLUMN kokoro_voice TEXT NOT NULL DEFAULT 'af_heart'")
    await db.commit()


async def _get_vcfg():
    db = await get_app_db()
    await _ensure_voice_cols(db)
    async with db.execute("SELECT * FROM voice_settings WHERE id=1") as cur:
        row = await cur.fetchone()
    if not row:
        await db.execute(
            "INSERT INTO voice_settings (id, voice, enabled, provider, kokoro_voice, updated_at)"
            " VALUES (1,'Kore',1,'gemini','af_heart','')")
        await db.commit()
        await db.close()
        return {"id": 1, "voice": "Kore", "enabled": 1,
                "provider": "gemini", "kokoro_voice": "af_heart", "updated_at": ""}
    await db.close()
    d = dict(row)
    d.setdefault("provider", "gemini")
    d.setdefault("kokoro_voice", _KOKORO_DEFAULT_VOICE)
    return d


@router.get("/settings/voice")
async def get_voice():
    return await _get_vcfg()


@router.get("/settings/voice/kokoro-status")
async def kokoro_status():
    """Probe for local Kokoro deps (D4-T01). Offered only when imports cleanly.

    Depends on kokoro-onnx only — never imports standalone phonemizer
    (module clash: phonemizer-fork wins, see DECISION_KOKORO.md). Phonemization
    runs exclusively through kokoro_onnx.tokenizer.Tokenizer (it owns the
    espeak DLL wiring).
    """
    return await asyncio.to_thread(_kokoro_probe)


def _kokoro_paths() -> tuple:
    """Weight paths: env override first, D4-T01 verified defaults otherwise.

    Never hard-coded as the only path — KOKORO_MODEL / KOKORO_VOICES win when
    set. Existence is always verified by the caller (probe + synth fail fast
    with a clear message naming what was tried).
    """
    model = (os.environ.get("KOKORO_MODEL") or "").strip().strip('"') or _KOKORO_DEFAULT_MODEL
    voices = (os.environ.get("KOKORO_VOICES") or "").strip().strip('"') or _KOKORO_DEFAULT_VOICES
    return model, voices


def _kokoro_probe() -> dict:
    try:
        import kokoro_onnx  # noqa: F401
        import onnxruntime  # noqa: F401
        from kokoro_onnx.tokenizer import Tokenizer  # noqa: F401
    except Exception as e:
        return {"available": False,
                "reason": f"kokoro deps not installed: {type(e).__name__}: {str(e)[:200]}. "
                          "Run: pip install kokoro-onnx onnxruntime (D5 Setup covers this).",
                "voices": [], "model_found": False, "voices_found": False}
    model_path, voices_path = _kokoro_paths()
    model_found = os.path.isfile(model_path)
    voices_found = os.path.isfile(voices_path)
    if not (model_found and voices_found):
        missing = []
        if not model_found:
            missing.append(f"model missing: {model_path}")
        if not voices_found:
            missing.append(f"voices missing: {voices_path}")
        return {"available": False,
                "reason": "kokoro packages installed but weights missing — "
                          + "; ".join(missing)
                          + ". Set KOKORO_MODEL / KOKORO_VOICES env or place weights at the D4-T01 paths.",
                "voices": [], "model_found": model_found, "voices_found": voices_found,
                "model_path": model_path, "voices_path": voices_path}
    return {"available": True, "reason": "kokoro-onnx + onnxruntime import cleanly, weights present",
            "voices": _kokoro_voice_list(),
            "default_voice": _KOKORO_DEFAULT_VOICE,
            "model_found": True, "voices_found": True,
            "model_path": model_path, "voices_path": voices_path}


def _kokoro_voice_list() -> list:
    try:
        from kokoro_onnx import Kokoro
        model_path, voices_path = _kokoro_paths()
        k = Kokoro(model_path, voices_path)
        return sorted(k.get_voices())
    except Exception:
        return []


@router.put("/settings/voice")
async def put_voice(data: VoiceSettings):
    cfg = await _get_vcfg()
    provider = (data.provider or cfg.get("provider") or "gemini").lower()
    if provider not in ("gemini", "kokoro"):
        raise HTTPException(400, "provider must be 'gemini' or 'kokoro'")
    if provider == "kokoro":
        probe = await asyncio.to_thread(_kokoro_probe)
        if not probe.get("available"):
            raise HTTPException(400, probe.get("reason", "kokoro unavailable"))
    db = await get_app_db()
    await _ensure_voice_cols(db)
    await db.execute("UPDATE voice_settings SET voice=?, enabled=?, provider=?, kokoro_voice=?, updated_at=? WHERE id=1",
                     (data.voice or cfg["voice"],
                      cfg["enabled"] if data.enabled is None else (1 if data.enabled else 0),
                      provider,
                      data.kokoro_voice or cfg.get("kokoro_voice") or _KOKORO_DEFAULT_VOICE,
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


def _load_kokoro_sync(model_path: str, voices_path: str):
    """Blocking model load (called via asyncio.to_thread). Cached per paths."""
    if _KOKORO_CACHE["key"] == (model_path, voices_path) and _KOKORO_CACHE["kokoro"] is not None:
        return _KOKORO_CACHE["kokoro"]
    from kokoro_onnx import Kokoro
    k = Kokoro(model_path, voices_path)
    _KOKORO_CACHE["key"] = (model_path, voices_path)
    _KOKORO_CACHE["kokoro"] = k
    return k


def _synth_kokoro_sync(kokoro, text: str, voice: str):
    """Blocking synth (called via asyncio.to_thread). Returns (samples, rate)."""
    return kokoro.create(text, voice, speed=1.0, lang="en-us")


async def _tts_kokoro(text, voice):
    """Local Kokoro TTS beside _tts (D4-T02). Same contract: raw 24kHz mono
    16-bit PCM bytes (no WAV header — _run writes the header identically).

    Depends on kokoro-onnx only — phonemization runs exclusively through
    kokoro_onnx.tokenizer.Tokenizer inside Kokoro.create (it owns the espeak
    DLL wiring); never calls raw phonemizer (module clash, see DECISION_KOKORO).
    PYTHONUTF8 is set for the synth path (Windows cp1252 consoles crash on IPA
    logging otherwise — D4-T01 console gotcha). No GPU: CPUExecutionProvider
    (default, ~1s/sentence — per-beat pacing dominates anyway).
    """
    os.environ["PYTHONUTF8"] = "1"
    model_path, voices_path = _kokoro_paths()
    tried = f"KOKORO_MODEL={model_path} | KOKORO_VOICES={voices_path}"
    if not os.path.isfile(model_path) or not os.path.isfile(voices_path):
        raise RuntimeError(f"Kokoro weights missing. Tried: {tried}")
    try:
        kokoro = await asyncio.to_thread(_load_kokoro_sync, model_path, voices_path)
    except Exception as e:
        raise RuntimeError(f"Kokoro load failed ({tried}): {type(e).__name__}: {str(e)[:200]}")
    try:
        samples, rate = await asyncio.to_thread(_synth_kokoro_sync, kokoro, text, voice)
    except Exception as e:
        raise RuntimeError(f"Kokoro synth failed (voice={voice}): {type(e).__name__}: {str(e)[:200]}")
    if int(rate) != 24000:
        raise RuntimeError(f"Kokoro sample-rate mismatch: got {rate}, contract is 24000")
    import numpy as np
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2").tobytes()
    if not pcm:
        raise RuntimeError("Kokoro synth returned no audio")
    return pcm


@router.post("/projects/{project_id}/voiceover/build")
async def build_voiceover(project_id: str):
    if _STATE["project"]:
        raise HTTPException(400, "A voiceover run is already in progress.")
    vcfg = await _get_vcfg()
    provider = (vcfg.get("provider") or "gemini").lower()
    key = await _gemini_key()
    if provider == "kokoro":
        probe = await asyncio.to_thread(_kokoro_probe)
        if not probe.get("available"):
            raise HTTPException(400, probe.get("reason", "kokoro unavailable"))
    elif not key:
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
    provider = (vcfg.get("provider") or "gemini").lower()
    gemini_voice = vcfg.get("voice") or "Kore"
    kokoro_voice = vcfg.get("kokoro_voice") or _KOKORO_DEFAULT_VOICE
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
                if provider == "kokoro":
                    pcm = await _tts_kokoro(b["text"], kokoro_voice)
                else:
                    pcm = await _tts(b["text"], gemini_voice, key)
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