# backend/api/recipes.py
"""Prompt library + LLM run log.

Two things the app has always had but never exposed:
  - the 18 recipes that drive every AI call (editable, versioned)
  - the job_log table that records every call (for debugging cheap models)

Editing a recipe writes a NEW version file rather than overwriting, so a bad
edit can always be undone by loading an older version and saving it again.
"""
import re
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import DATA_DIR
from backend.core.llm_client import JOB_MAP, RECIPES_DIR
from backend.db.connection import get_app_db

router = APIRouter(tags=["recipes"])

_SAFE_JOB = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


def _versions(job: str) -> List[int]:
    vs = []
    for p in RECIPES_DIR.glob(f"{job}_v*.txt"):
        m = re.match(rf"^{re.escape(job)}_v(\d+)\.txt$", p.name)
        if m:
            vs.append(int(m.group(1)))
    return sorted(vs)


def _check_job(job: str):
    """Guard against path traversal - only known job types are addressable."""
    if job not in JOB_MAP or not _SAFE_JOB.match(job):
        raise HTTPException(404, f"Unknown job type '{job}'")


class RecipeUpdate(BaseModel):
    content: str


@router.get("/recipes")
async def list_recipes():
    out = []
    for job, spec in JOB_MAP.items():
        vs = _versions(job)
        out.append({
            "job": job,
            "tier": spec["tier"],
            "temperature": spec["temp"],
            "stream": spec["stream"],
            "versions": vs,
            "current_version": vs[-1] if vs else None,
            "has_recipe": bool(vs),
        })
    out.sort(key=lambda r: (not r["has_recipe"], r["job"]))
    return out


@router.get("/recipes/{job}")
async def get_recipe(job: str, version: Optional[int] = None):
    _check_job(job)
    vs = _versions(job)
    if not vs:
        raise HTTPException(404, f"No recipe file found for '{job}'")
    v = version if version in vs else vs[-1]
    path = RECIPES_DIR / f"{job}_v{v}.txt"
    return {
        "job": job,
        "version": v,
        "versions": vs,
        "content": path.read_text(encoding="utf-8"),
        "tier": JOB_MAP[job]["tier"],
        "temperature": JOB_MAP[job]["temp"],
        "stream": JOB_MAP[job]["stream"],
    }


@router.put("/recipes/{job}")
async def save_recipe(job: str, body: RecipeUpdate):
    """Save as a NEW version. Old versions are kept so edits are reversible."""
    _check_job(job)
    text = body.content
    if not text.strip():
        raise HTTPException(400, "Recipe cannot be empty.")
    vs = _versions(job)
    if not vs:
        raise HTTPException(404, f"No recipe file found for '{job}'")
    current = vs[-1]
    current_text = (RECIPES_DIR / f"{job}_v{current}.txt").read_text(encoding="utf-8")
    if text == current_text:
        return {"status": "unchanged", "version": current}

    new_v = current + 1
    (RECIPES_DIR / f"{job}_v{new_v}.txt").write_text(text, encoding="utf-8")
    return {"status": "saved", "version": new_v, "previous_version": current}


@router.get("/runs")
async def list_runs(limit: int = 50, job_type: Optional[str] = None,
                    project_id: Optional[str] = None, errors_only: bool = False):
    """Most recent LLM calls. Raw output is truncated - use /runs/{id} for full."""
    limit = max(1, min(limit, 500))
    where, args = [], []
    if job_type:
        where.append("job_type = ?")
        args.append(job_type)
    if project_id:
        where.append("project_id = ?")
        args.append(project_id)
    if errors_only:
        where.append("error IS NOT NULL")
    sql = ("SELECT id, project_id, job_type, model, temperature, escalated, tokens_in,"
           " tokens_out, duration_ms, error, created_at,"
           " substr(raw_output, 1, 300) AS raw_preview FROM job_log")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)

    db = await get_app_db()
    async with db.execute(sql, args) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    for r in rows:
        r["ok"] = r["error"] is None
        r["escalated"] = bool(r.get("escalated"))
    return rows


@router.get("/runs/{run_id}")
async def get_run(run_id: int):
    db = await get_app_db()
    async with db.execute("SELECT * FROM job_log WHERE id=?", (run_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Run not found")
    d = dict(row)
    d["escalated"] = bool(d.get("escalated"))
    return d


@router.get("/runs/stats/summary")
async def run_stats():
    """Cheap overview: totals, failure rate, and the jobs that fail most."""
    db = await get_app_db()
    async with db.execute(
        "SELECT COUNT(*) n, SUM(error IS NOT NULL) bad, SUM(escalated) esc,"
        " SUM(COALESCE(tokens_in,0)+COALESCE(tokens_out,0)) tok,"
        " AVG(duration_ms) avg_ms FROM job_log"
    ) as cur:
        total = dict(await cur.fetchone())
    async with db.execute(
        "SELECT job_type, COUNT(*) n, SUM(error IS NOT NULL) bad,"
        " SUM(escalated) esc FROM job_log GROUP BY job_type ORDER BY bad DESC, n DESC"
    ) as cur:
        per_job = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"total": total, "per_job": per_job}
