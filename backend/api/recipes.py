# backend/api/recipes.py
"""Prompt library + LLM run log.

Two things the app has always had but never exposed:
  - the 18 recipes that drive every AI call (editable, versioned)
  - the job_log table that records every call (for debugging cheap models)

Editing a recipe writes a NEW version file rather than overwriting, so a bad
edit can always be undone by loading an older version and saving it again.
"""
import json
import re
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import DATA_DIR
from backend.core.llm_client import JOB_MAP, RECIPES_DIR, _model_for, dispatch
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


class ABRequest(BaseModel):
    version_a: int
    version_b: int
    project_id: Optional[str] = None


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


@router.get("/recipes/{job}/preview")
async def recipe_preview(job: str):
    """What this job will use, and how it has actually behaved recently.

    Deliberately built from real job_log history rather than a token estimate:
    "the light model has failed this 9 of 12 times" is more useful than a guess.
    """
    _check_job(job)
    spec = JOB_MAP[job]
    db = await get_app_db()
    async with db.execute(
        "SELECT COUNT(*) n, SUM(error IS NOT NULL) bad, SUM(escalated) esc,"
        " AVG(COALESCE(tokens_in,0)) avg_in, AVG(COALESCE(tokens_out,0)) avg_out,"
        " AVG(duration_ms) avg_ms FROM job_log WHERE job_type=?", (job,)) as cur:
        hist = dict(await cur.fetchone())
    await db.close()
    n = hist.get("n") or 0
    return {
        "job": job,
        "tier": spec["tier"],
        "model": _model_for(spec["tier"]),
        "temperature": spec["temp"],
        "stream": spec["stream"],
        "versions": _versions(job),
        "history": {
            "runs": n,
            "failures": hist.get("bad") or 0,
            "escalated": hist.get("esc") or 0,
            "failure_rate": round((hist.get("bad") or 0) / n, 2) if n else None,
            "avg_tokens_in": round(hist["avg_in"] or 0),
            "avg_tokens_out": round(hist["avg_out"] or 0),
            "avg_ms": round(hist["avg_ms"] or 0),
        },
    }


@router.post("/recipes/{job}/ab-test")
async def ab_test(job: str, body: ABRequest):
    """Run the same input through two recipe versions and show both outputs.

    Reuses the context_pack of the most recent real run of this job, so you are
    comparing against something the pipeline actually sent rather than a
    made-up sample.
    """
    _check_job(job)
    versions = _versions(job)
    for v in (body.version_a, body.version_b):
        if v not in versions:
            raise HTTPException(400, f"Version {v} does not exist for '{job}'")

    db = await get_app_db()
    async with db.execute(
        "SELECT context_pack, project_id FROM job_log WHERE job_type=? AND context_pack IS NOT NULL"
        " ORDER BY id DESC LIMIT 1", (job,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(400, "No previous run of this job to reuse as sample input.")
    try:
        context = json.loads(row["context_pack"])
    except Exception:
        raise HTTPException(400, "Stored sample context could not be read.")

    pid = body.project_id or row["project_id"]
    a = await dispatch(job, context, schema=None, project_id=pid, recipe_version=body.version_a)
    b = await dispatch(job, context, schema=None, project_id=pid, recipe_version=body.version_b)

    def _side(res, version):
        return {"version": version, "ok": res.get("ok", False),
                "output": (res.get("parsed") or res.get("raw") or ""),
                "error": res.get("error")}

    return {"job": job, "context": context,
            "a": _side(a, body.version_a), "b": _side(b, body.version_b)}


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
