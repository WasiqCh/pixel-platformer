# backend/api/environments.py
from datetime import datetime, timezone
import asyncio
import json

from fastapi import APIRouter, HTTPException

from backend.core.sharding import sharded_extract
from backend.db.connection import get_app_db, get_project_db
from backend.models.environment import EnvironmentExtractResult
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["environments"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _next_id(proj_db, table, prefix):
    async with proj_db.execute(f"SELECT id FROM {table} WHERE id LIKE ?", (prefix + "%",)) as cur:
        ids = [r["id"] for r in await cur.fetchall()]
    nums = [int(x[len(prefix):]) for x in ids if x[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) + 1) if nums else 1:02d}"


async def _get_proj_info(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


async def _get_locked_script(folder: str, project_id: str):
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT text FROM scripts WHERE project_id=? AND locked=1 ORDER BY id DESC LIMIT 1",
        (project_id,)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    return row["text"] if row else None


def _merge_envs(a: dict, b: dict) -> dict:
    by_name = {}
    for item in a["environments"] + b["environments"]:
        key = item["name"].strip().lower()
        if key in by_name:
            cur = by_name[key]
            cur["elements"] = list(dict.fromkeys(cur["elements"] + item["elements"]))
            cur["variations"] = list(dict.fromkeys(cur["variations"] + item["variations"]))
            cur["presence_sections"] = list(dict.fromkeys(cur["presence_sections"] + item["presence_sections"]))
            cur["green_conflict"] = bool(cur["green_conflict"] or item["green_conflict"])
        else:
            by_name[key] = dict(item)
    return {"environments": list(by_name.values())}


def _write_env_mirror(ch_id, folder, rows):
    world_dir = get_project_dir(ch_id, folder.split("_")[1]) / "05_world"
    world_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Environment Registry", ""]
    for r in rows:
        lines.append(f"## {r['id']} — {r['name']}")
        lines.append("elements: " + "; ".join(r["elements"]))
        if r["variations"]:
            lines.append("variations: " + ", ".join(r["variations"]))
        if r["green_conflict"]:
            lines.append("⚠ green_conflict (foliage-heavy)")
        lines.append("")
    (world_dir / "environments.md").write_text("\n".join(lines), encoding="utf-8")


@router.post("/projects/{project_id}/environments/extract")
async def extract_environments(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    script = await _get_locked_script(folder, project_id)
    if not script:
        raise HTTPException(400, "Lock a script first (Script Studio -> Lock).")

    parsed, res = None, None
    for attempt in range(3):
        parsed, res = await sharded_extract(
            "environment_extract", EnvironmentExtractResult,
            {"channel_id": ch_id}, script, _merge_envs,
            project_id=project_id, channel_id=ch_id)
        if parsed is not None:
            break
        err = str(res.get("error", ""))
        if not any(k in err for k in ("Expecting value", "Unterminated", "Invalid", "JSON")):
            break
        await asyncio.sleep(3)
    if parsed is None:
        raise HTTPException(500,
            "The AI gateway returned an empty or broken answer (temporary rate limiting). "
            "Wait ~30 seconds and click again - nothing was lost. Raw: " + str(res.get("error"))[:200])

    proj_db = await get_project_db(folder)
    now = _now()

    async with proj_db.execute("SELECT * FROM environments WHERE project_id=?", (project_id,)) as cur:
        existing = {r["name"].strip().lower(): dict(r) for r in await cur.fetchall()}

    seen, added, updated = set(), 0, 0
    for item in parsed["environments"]:
        key = item["name"].strip().lower()
        seen.add(key)
        if key in existing:
            row = existing[key]
            env_id = row["id"]
            await proj_db.execute(
                "UPDATE environments SET elements=?, green_conflict=?, presence=?, stale=0, updated_at=? WHERE id=?",
                (json.dumps(item["elements"]), 1 if item["green_conflict"] else 0,
                 json.dumps(item["presence_sections"]), now, env_id))
            updated += 1
        else:
            env_id = await _next_id(proj_db, "environments", "E")
            await proj_db.execute(
                "INSERT INTO environments (id, project_id, name, elements, green_conflict, presence, stale, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (env_id, project_id, item["name"], json.dumps(item["elements"]),
                 1 if item["green_conflict"] else 0, json.dumps(item["presence_sections"]), now, now))
            added += 1

        await proj_db.execute("DELETE FROM env_variations WHERE environment_id=?", (env_id,))
        for v in item["variations"]:
            ev_id = await _next_id(proj_db, "env_variations", "EV")
            await proj_db.execute(
                "INSERT INTO env_variations (id, environment_id, state, span, evidence, stale, created_at) "
                "VALUES (?, ?, ?, '', '', 0, ?)",
                (ev_id, env_id, v, now))

    staled = 0
    for key, row in existing.items():
        if key not in seen and not row["stale"]:
            await proj_db.execute("UPDATE environments SET stale=1, updated_at=? WHERE id=?", (now, row["id"]))
            staled += 1
    await proj_db.commit()

    async with proj_db.execute("SELECT * FROM environments WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["elements"] = json.loads(r["elements"] or "[]")
        async with proj_db.execute("SELECT state FROM env_variations WHERE environment_id=? ORDER BY id", (r["id"],)) as cur:
            r["variations"] = [v["state"] for v in await cur.fetchall()]
    await proj_db.close()

    _write_env_mirror(ch_id, folder, rows)
    return {"added": added, "updated": updated, "staled": staled, "total": len(rows)}


@router.get("/projects/{project_id}/environments")
async def list_environments(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM environments WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["elements"] = json.loads(r["elements"] or "[]")
        r["presence"] = json.loads(r["presence"] or "[]")
        async with proj_db.execute("SELECT state FROM env_variations WHERE environment_id=? ORDER BY id", (r["id"],)) as cur:
            r["variations"] = [v["state"] for v in await cur.fetchall()]
    await proj_db.close()
    return rows


@router.delete("/projects/{project_id}/environments/{env_id}")
async def delete_environment(project_id: str, env_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    await proj_db.execute("DELETE FROM env_variations WHERE environment_id=?", (env_id,))
    await proj_db.execute("DELETE FROM environments WHERE id=? AND project_id=?", (env_id, project_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "deleted"}
