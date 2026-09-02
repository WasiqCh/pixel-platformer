# backend/api/scripts.py
from datetime import datetime, timezone
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.core.llm_client import dispatch, dispatch_stream
from backend.db.connection import get_app_db, get_project_db
from backend.models.script import OutlineResult, CheckResult, AutoSectionResult
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["scripts"])

class OutlineRequest(BaseModel):
    target_words: int

class OutlineEditRequest(BaseModel):
    sections: list

class OutlineRefineRequest(BaseModel):
    instruction: str

class LockRequest(BaseModel):
    text: str
    word_count: int
    source: str = "ai"

class PunchupRequest(BaseModel):
    script_text: str
    section_heading: str
    note: str

class CheckRequest(BaseModel):
    script_text: str

class ImportRequest(BaseModel):
    text: str

class AutoSectionRequest(BaseModel):
    script_text: str

def _now():
    return datetime.now(timezone.utc).isoformat()

async def _get_proj_info(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
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
        (project_id,)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    return json.loads(row["content"]) if row else {}

def _write_outline_mirror(ch_id, folder, version, sections):
    script_dir = get_project_dir(ch_id, folder.split("_")[1]) / "03_script"
    script_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# Outline v{version}", ""]
    for s in sections:
        lines.append(f"## {s['heading']} ({s.get('role', 'build')}) — {s['target_words']} words")
        lines.append(s["summary"])
        lines.append("")
    (script_dir / f"outline_v{version}.md").write_text("\n".join(lines), encoding="utf-8")

# ---------- script read-back & versions ----------
@router.get("/projects/{project_id}/script")
async def get_script(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT id, version, text, word_count, duration_sec, locked, locked_at, source, created_at "
        "FROM scripts WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    return {"script": dict(row) if row else None}

@router.get("/projects/{project_id}/script/versions")
async def list_versions(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT id, version, word_count, duration_sec, locked, source, created_at "
        "FROM scripts WHERE project_id=? ORDER BY id ASC", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    return rows

@router.get("/projects/{project_id}/script/versions/{version_id}")
async def get_version(project_id: str, version_id: int):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM scripts WHERE id=? AND project_id=?",
                               (version_id, project_id)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    if not row:
        raise HTTPException(404, "Version not found")
    return dict(row)

@router.delete("/projects/{project_id}/script/versions/{version_id}")
async def delete_version(project_id: str, version_id: int):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    await proj_db.execute("DELETE FROM scripts WHERE id=? AND project_id=?", (version_id, project_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "deleted"}

# ---------- Pass 1: outline (persisted + versioned) ----------
@router.post("/projects/{project_id}/script/outline")
async def generate_outline(project_id: str, req: OutlineRequest):
    folder, ch_id = await _get_proj_info(project_id)
    title = await _get_locked_title(folder, project_id)
    idea = await _get_current_idea(folder, project_id)

    context = {"idea_card": idea, "title": title,
               "channel_tone": "dramatic, playful", "target_word_count": req.target_words}
    result = await dispatch("script_outline", context, schema=OutlineResult,
                            project_id=project_id, channel_id=ch_id)
    if not result["ok"]:
        raise HTTPException(500, result.get("error", "AI failed to build outline"))

    sections = result["parsed"]["sections"]
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT MAX(version) FROM outlines WHERE project_id=?", (project_id,)) as cur:
        version = ((await cur.fetchone())[0] or 0) + 1
    now = _now()
    await proj_db.execute("UPDATE outlines SET is_current=0 WHERE project_id=? AND is_current=1", (project_id,))
    cur = await proj_db.execute(
        "INSERT INTO outlines (project_id, version, sections, target_words, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, version, json.dumps(sections), sum(s["target_words"] for s in sections), now, now))
    await proj_db.commit()
    new_id = cur.lastrowid
    await proj_db.close()
    _write_outline_mirror(ch_id, folder, version, sections)
    return {"sections": sections, "version": version, "id": new_id}

@router.get("/projects/{project_id}/outline")
async def get_outline(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT id, version, sections, target_words FROM outlines WHERE project_id=? AND is_current=1 LIMIT 1",
        (project_id,)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    if not row:
        return {"outline": None}
    return {"outline": {"id": row["id"], "version": row["version"],
                        "target_words": row["target_words"], "sections": json.loads(row["sections"])}}

@router.put("/projects/{project_id}/outline")
async def edit_outline(project_id: str, req: OutlineEditRequest):
    try:
        OutlineResult(sections=req.sections)
    except Exception as e:
        raise HTTPException(422, f"Bad outline shape: {e}")
    folder, ch_id = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT id, version FROM outlines WHERE project_id=? AND is_current=1 LIMIT 1", (project_id,)) as cur:
        row = await cur.fetchone()
    now = _now()
    total = sum(s["target_words"] for s in req.sections)
    if row:
        version = row["version"]
        await proj_db.execute("UPDATE outlines SET sections=?, target_words=?, updated_at=? WHERE id=?",
                              (json.dumps(req.sections), total, now, row["id"]))
    else:
        version = 1
        await proj_db.execute(
            "INSERT INTO outlines (project_id, version, sections, target_words, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (project_id, 1, json.dumps(req.sections), total, now, now))
    await proj_db.commit()
    await proj_db.close()
    _write_outline_mirror(ch_id, folder, version, req.sections)
    return {"status": "saved", "version": version}

@router.post("/projects/{project_id}/outline/refine")
async def refine_outline(project_id: str, req: OutlineRefineRequest):
    folder, ch_id = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT sections, target_words, version FROM outlines WHERE project_id=? AND is_current=1 LIMIT 1",
        (project_id,)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    if not row:
        raise HTTPException(400, "No outline yet — generate one first.")
    current, total, old_version = json.loads(row["sections"]), row["target_words"], row["version"]

    title = await _get_locked_title(folder, project_id)
    idea = await _get_current_idea(folder, project_id)
    result = await dispatch("outline_refine",
                            {"outline": current, "instruction": req.instruction,
                             "total_words": total, "title": title, "idea_card": idea},
                            schema=OutlineResult, project_id=project_id, channel_id=ch_id)
    if not result["ok"]:
        raise HTTPException(500, result.get("error"))

    sections = result["parsed"]["sections"]
    proj_db = await get_project_db(folder)
    now = _now()
    await proj_db.execute("UPDATE outlines SET is_current=0 WHERE project_id=? AND is_current=1", (project_id,))
    cur = await proj_db.execute(
        "INSERT INTO outlines (project_id, version, sections, target_words, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, old_version + 1, json.dumps(sections), sum(s["target_words"] for s in sections), now, now))
    await proj_db.commit()
    new_id = cur.lastrowid
    await proj_db.close()
    _write_outline_mirror(ch_id, folder, old_version + 1, sections)
    return {"sections": sections, "version": old_version + 1, "id": new_id}

# ---------- Pass 2: streamed draft ----------
@router.post("/projects/{project_id}/script/draft")
async def stream_draft(project_id: str, outline: OutlineResult):
    folder, ch_id = await _get_proj_info(project_id)
    title = await _get_locked_title(folder, project_id)
    idea = await _get_current_idea(folder, project_id)
    context = {"idea_card": idea, "title": title, "channel_tone": "dramatic, playful",
               "outline": [s.model_dump() for s in outline.sections],
               "target_words": sum(s.target_words for s in outline.sections)}
    return StreamingResponse(
        dispatch_stream("script_draft", context, project_id=project_id, channel_id=ch_id),
        media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

# ---------- Lock (versioned file mirror + unchanged guard) ----------
@router.post("/projects/{project_id}/script/lock")
async def lock_script(project_id: str, req: LockRequest):
    folder, ch_id = await _get_proj_info(project_id)
    now = _now()
    duration_sec = (req.word_count / 150.0) * 60.0

    proj_db = await get_project_db(folder)
    # Always increment version
    async with proj_db.execute("SELECT COUNT(*) FROM scripts WHERE project_id=?", (project_id,)) as cur:
        v = (await cur.fetchone())[0] + 1
    
    await proj_db.execute(
        "INSERT INTO scripts (project_id, version, text, word_count, duration_sec, locked, locked_at, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
        (project_id, v, req.text, req.word_count, duration_sec, now, req.source, now))
    await proj_db.commit()
    await proj_db.close()

    # File mirror
    script_dir = get_project_dir(ch_id, folder.split("_")[1]) / "03_script"
    script_dir.mkdir(parents=True, exist_ok=True)
    (script_dir / f"locked_v{v}.md").write_text(req.text, encoding="utf-8")

    # Update project stage
    app_db = await get_app_db()
    await app_db.execute("UPDATE projects SET stage='script', updated_at=? WHERE id=?", (now, project_id))
    await app_db.commit()
    await app_db.close()
    
    return {"status": "locked", "duration_sec": duration_sec, "version": v}

# ---------- Pass 3: Punch-up ----------
@router.post("/projects/{project_id}/script/punchup")
async def punchup_script(project_id: str, req: PunchupRequest):
    folder, ch_id = await _get_proj_info(project_id)
    context = {"full_script": req.script_text,
               "section_heading": req.section_heading,
               "note": req.note}
    result = await dispatch("script_punchup", context, schema=None,
                            project_id=project_id, channel_id=ch_id)
    if not result["ok"]:
        raise HTTPException(500, result.get("error"))
    return {"rewritten": result["parsed"].strip()}

# ---------- Pass 4: Consistency Check ----------
@router.post("/projects/{project_id}/script/check")
async def check_script(project_id: str, req: CheckRequest):
    folder, ch_id = await _get_proj_info(project_id)

    app_db = await get_app_db()
    async with app_db.execute("SELECT descriptor FROM channels WHERE id=?", (ch_id,)) as cur:
        ch_row = await cur.fetchone()
    await app_db.close()
    descriptor = (ch_row["descriptor"] or "") if ch_row else ""

    context = {"script": req.script_text, "channel_descriptor": descriptor}
    result = await dispatch("script_check", context, schema=CheckResult,
                            project_id=project_id, channel_id=ch_id)
    if not result["ok"]:
        raise HTTPException(500, result.get("error"))
    return result["parsed"]

# ---------- Import & Auto-Section ----------
@router.post("/projects/{project_id}/script/import")
async def import_script(project_id: str, req: ImportRequest):
    if len(req.text.strip()) < 50:
        raise HTTPException(400, "Script too short to import.")
    folder, _ = await _get_proj_info(project_id)
    words = len(req.text.split())
    duration_sec = (words / 150.0) * 60.0
    proj_db = await get_project_db(folder)
    await proj_db.execute(
        "INSERT INTO scripts (project_id, text, word_count, duration_sec, locked, source, created_at) "
        "VALUES (?, ?, ?, ?, 0, 'imported', ?)",
        (project_id, req.text, words, duration_sec, _now()))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "imported", "text": req.text,
            "word_count": words, "duration_sec": duration_sec}

@router.post("/projects/{project_id}/script/auto-section")
async def auto_section(project_id: str, req: AutoSectionRequest):
    try:
        folder, ch_id = await _get_proj_info(project_id)
        result = await dispatch("script_autosection", {"script": req.script_text},
                                schema=AutoSectionResult, project_id=project_id, channel_id=ch_id)
        if not result["ok"]:
            raise HTTPException(500, result.get("error", "AI failed"))

        sections, parts = [], []
        for s in result["parsed"]["sections"]:
            wc = len(s["chunk_text"].split())
            sections.append({"heading": s["heading"], "summary": s["summary"], "role": s["role"], "target_words": wc})
            parts.append(f"## {s['heading']}\n{s['chunk_text'].strip()}")
        rebuilt = "\n\n".join(parts)

        proj_db = await get_project_db(folder)
        async with proj_db.execute("SELECT MAX(version) FROM outlines WHERE project_id=?", (project_id,)) as cur:
            version = ((await cur.fetchone())[0] or 0) + 1
        now = _now()
        await proj_db.execute("UPDATE outlines SET is_current=0 WHERE project_id=? AND is_current=1", (project_id,))
        await proj_db.execute(
            "INSERT INTO outlines (project_id, version, sections, target_words, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (project_id, version, json.dumps(sections), sum(x["target_words"] for x in sections), now, now))
        await proj_db.commit()
        await proj_db.close()
        _write_outline_mirror(ch_id, folder, version, sections)
        return {"rebuilt_text": rebuilt, "outline": {"version": version, "sections": sections}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Auto-section crashed: {e}")
