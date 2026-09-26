# backend/api/checkpoint.py
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["checkpoint"])


async def _get_proj(project_id: str) -> dict:
    db = await get_app_db()
    async with db.execute("SELECT * FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
    return dict(row)


@router.get("/projects/{project_id}/checkpoint")
async def checkpoint(project_id: str):
    proj = await _get_proj(project_id)
    folder, ch_id = proj["folder_name"], proj["channel_id"]
    proj_db = await get_project_db(folder)

    async with proj_db.execute("SELECT COUNT(*) c, MAX(version) v FROM scripts WHERE project_id=? AND locked=1", (project_id,)) as cur:
        s = await cur.fetchone()
    locked = s["c"] > 0
    async with proj_db.execute("SELECT COUNT(*) c FROM outlines WHERE project_id=?", (project_id,)) as cur:
        outlines = (await cur.fetchone())["c"]
    async with proj_db.execute("SELECT COUNT(*) c FROM characters WHERE project_id=? AND stale=0", (project_id,)) as cur:
        chars = (await cur.fetchone())["c"]
    async with proj_db.execute("SELECT COUNT(*) c FROM environments WHERE project_id=? AND stale=0", (project_id,)) as cur:
        envs = (await cur.fetchone())["c"]
    async with proj_db.execute("SELECT COUNT(*) c FROM world_records WHERE project_id=? AND stale=0", (project_id,)) as cur:
        worlds = (await cur.fetchone())["c"]
    async with proj_db.execute("SELECT COUNT(*) c FROM beats WHERE project_id=? AND stale=0", (project_id,)) as cur:
        beats = (await cur.fetchone())["c"]
    async with proj_db.execute("SELECT status FROM library WHERE project_id=?", (project_id,)) as cur:
        librows = [r["status"] for r in await cur.fetchall()]
    async with proj_db.execute("SELECT green_conflict g FROM characters WHERE project_id=? AND stale=0", (project_id,)) as cur:
        green = sum(r["g"] for r in await cur.fetchall())
    async with proj_db.execute("SELECT green_conflict g FROM environments WHERE project_id=? AND stale=0", (project_id,)) as cur:
        green += sum(r["g"] for r in await cur.fetchall())
    async with proj_db.execute("SELECT duration_sec FROM beats WHERE project_id=? AND stale=0", (project_id,)) as cur:
        durs = [r["duration_sec"] for r in await cur.fetchall()]
    outliers = sum(1 for d in durs if d < 3.5 or d > 11)
    await proj_db.close()


    lib = len(librows)
    ready = sum(1 for st in librows if st == "ready")
    sheets_dir = get_project_dir(ch_id, folder.split("_")[1]) / "06_assets"
    sheets = 0
    for sub in ("characters", "environments"):
        d = sheets_dir / sub
        if d.exists():
            sheets += len(list(d.glob("*_sheet.md")))

    checks = [
        {"id": "script",  "label": "Script locked",          "required": True,  "ok": locked,
         "detail": f"v{s['v']} locked" if locked else "Lock a script in Script Studio"},
        {"id": "outline", "label": "Outline generated",      "required": True,  "ok": outlines > 0,
         "detail": f"{outlines} version(s)" if outlines else "Generate an outline (Script Studio card 1)"},
        {"id": "cast",    "label": "Cast extracted",         "required": True,  "ok": chars > 0,  "detail": f"{chars} characters"},
        {"id": "envs",    "label": "Locations extracted",    "required": True,  "ok": envs > 0,   "detail": f"{envs} environments"},
        {"id": "beats",   "label": "Beats broken down",      "required": True,  "ok": beats > 0,  "detail": f"{beats} beats"},
        {"id": "sheets",  "label": "Sheets written",         "required": True,  "ok": sheets > 0, "detail": f"{sheets} sheets"},
        {"id": "library", "label": "Library scaffolded",     "required": True,  "ok": lib > 0,    "detail": f"{lib} slots · {ready} ready"},
        {"id": "world",   "label": "World scanned",          "required": False, "ok": worlds > 0, "detail": f"{worlds} records"},
        {"id": "ready",   "label": "All assets ready",       "required": False, "ok": lib > 0 and ready == lib,
         "detail": f"{ready}/{lib} ready"},
        {"id": "green",   "label": "Green conflicts reviewed","required": False,"ok": True,
         "detail": f"{green} flagged — confirm non-green palette plan"},
        {"id": "pacing",  "label": "Pacing outliers reviewed", "required": False, "ok": True,
         "detail": f"{outliers} beats flagged (⚡ too fast / 🐢 too slow) — review in Beat Board"},
    ]

    req = [c for c in checks if c["required"]]
    passed = sum(1 for c in req if c["ok"])
    # SCENES-MP4 P3-T03: the ONE blocking gate for S13 — render readiness
    # (scenes approved + beat audio). Advisory here (never blocks advance);
    # the POST /projects/{id}/render endpoint enforces it with a 409.
    try:
        from backend.api.render import render_gate as _render_gate
        _rg = await _render_gate(project_id)
        render_gate = {
            "can_render": _rg["can_render"],
            "total_beats": _rg["total_beats"],
            "approved": _rg["approved"],
            "unapproved": len(_rg["unapproved"]),
            "stale": len(_rg["stale_scenes"]),
            "missing_audio": len(_rg["missing_audio"]),
            "message": _rg["message"],
        }
    except HTTPException as e:
        render_gate = {"can_render": False, "total_beats": 0, "approved": 0,
                       "unapproved": 0, "stale": 0, "missing_audio": 0,
                       "message": f"Render gate error: {e.detail}"}
    except Exception as e:
        render_gate = {"can_render": False, "total_beats": 0, "approved": 0,
                       "unapproved": 0, "stale": 0, "missing_audio": 0,
                       "message": f"Render gate error: {type(e).__name__}: {e}"}
    return {"checks": checks, "required_pass": passed, "required_total": len(req),
            "can_advance": passed == len(req), "stage": proj.get("stage") or "script",
            "render_gate": render_gate}


@router.post("/projects/{project_id}/checkpoint/advance")
async def advance(project_id: str):
    await _get_proj(project_id)
    data = await checkpoint(project_id)
    if not data["can_advance"]:
        raise HTTPException(400, f"{data['required_total'] - data['required_pass']} required check(s) failing — fix them first.")
    db = await get_app_db()
    await db.execute("UPDATE projects SET stage='ready_for_handoff', updated_at=? WHERE id=?",
                     (datetime.now(timezone.utc).isoformat(), project_id))
    await db.commit()
    await db.close()
    return {"stage": "ready_for_handoff"}
