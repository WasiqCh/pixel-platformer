# backend/api/variants.py
import asyncio
from datetime import datetime, timezone
import json

from fastapi import APIRouter, HTTPException

from backend.core.sharding import sharded_extract
from backend.db.connection import get_app_db, get_project_db
from backend.models.variant import VariantExtractResult
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["variants"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _next_variant_id(proj_db):
    async with proj_db.execute("SELECT id FROM variants WHERE id LIKE 'V%'") as cur:
        ids = [r["id"] for r in await cur.fetchall()]
    nums = [int(x[1:]) for x in ids if x[1:].isdigit()]
    return f"V{(max(nums) + 1) if nums else 1:02d}"


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


def _merge_variants(a: dict, b: dict) -> dict:
    by_key = {}
    for v in a["variants"] + b["variants"]:
        key = (v["character_name"].strip().lower(), v["label"].strip().lower(),
               v["from_section"], v["to_section"])
        if key not in by_key or v["confidence"] > by_key[key]["confidence"]:
            by_key[key] = dict(v)
    return {"variants": list(by_key.values())}


def _write_variants_mirror(ch_id, folder, rows):
    cast_dir = get_project_dir(ch_id, folder.split("_")[1]) / "04_cast"
    cast_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Variant Timelines", ""]
    for r in rows:
        rare_tag = " (ONE-OFF candidate)" if r["stale"] else ""
        lines.append(f"## {r['id']} — {r['label']}{rare_tag}")
        lines.append(f"character: {r['character_id']}")
        lines.append(f"span: {r['span']}")
        lines.append(f"delta: {r['delta']}")
        lines.append(f"confidence: {r['confidence']}")
        lines.append(f"evidence: {r['evidence'] or 'TBD'}")
        lines.append("")
    (cast_dir / "variants.md").write_text("\n".join(lines), encoding="utf-8")


@router.post("/projects/{project_id}/variants/extract")
async def extract_variants(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    script = await _get_locked_script(folder, project_id)
    if not script:
        raise HTTPException(400, "Lock a script first (Script Studio -> Lock).")

    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM characters WHERE project_id=? AND stale=0", (project_id,)) as cur:
        chars = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    if not chars:
        raise HTTPException(400, "No active characters. Run character extraction first.")

    char_registry = []
    for c in chars:
        names = c["names"] if isinstance(c["names"], list) else json.loads(c["names"])
        char_registry.append({"id": c["id"], "name": names[0], "significance": c["significance"]})

    parsed, res = None, None
    for attempt in range(3):
        parsed, res = await sharded_extract(
            "variant_extract", VariantExtractResult,
            {"channel_id": ch_id, "characters": char_registry}, script, _merge_variants,
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

    char_by_name = {}
    for c in chars:
        names = c["names"] if isinstance(c["names"], list) else json.loads(c["names"])
        for n in names:
            char_by_name[n.strip().lower()] = c["id"]

    await proj_db.execute(
        "DELETE FROM variants WHERE character_id IN (SELECT id FROM characters WHERE project_id=?)",
        (project_id,))

    added, unlinked, rows_saved = 0, 0, []
    for v in parsed["variants"]:
        char_id = char_by_name.get(v["character_name"].strip().lower())
        if not char_id:
            unlinked += 1
            continue
        var_id = await _next_variant_id(proj_db)
        span = f"{v['from_section']} -> {v['to_section']}" if v["from_section"] else "(unspecified)"
        await proj_db.execute(
            "INSERT INTO variants (id, character_id, span, delta, evidence, confidence, stale, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (var_id, char_id, span, v["delta"], v["evidence"], v["confidence"],
             1 if v.get("rare") else 0, now, now))
        rows_saved.append({
            "id": var_id, "character_id": char_id, "label": v["label"],
            "span": span, "delta": v["delta"], "evidence": v["evidence"],
            "confidence": v["confidence"], "stale": 1 if v.get("rare") else 0,
        })
        added += 1

    await proj_db.commit()
    await proj_db.close()

    _write_variants_mirror(ch_id, folder, rows_saved)
    return {"added": added, "unlinked": unlinked, "total": len(rows_saved)}


@router.get("/projects/{project_id}/variants")
async def list_variants(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT v.*, c.names as char_names FROM variants v "
        "JOIN characters c ON v.character_id = c.id "
        "WHERE c.project_id=? AND c.stale=0 ORDER BY v.id",
        (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    for r in rows:
        r["char_names"] = json.loads(r["char_names"])
    return rows


@router.delete("/projects/{project_id}/variants/{var_id}")
async def delete_variant(project_id: str, var_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    await proj_db.execute("DELETE FROM variants WHERE id=?", (var_id,))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "deleted"}