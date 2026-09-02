# backend/api/beats.py
from datetime import datetime, timezone
import asyncio
import json

from fastapi import APIRouter, HTTPException

from backend.core.sharding import sharded_extract
from backend.db.connection import get_app_db, get_project_db
from backend.models.beat import BeatBreakdownResult
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["beats"])


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


def _parse_sections(script: str) -> dict:
    secs, current, buf = {}, None, []
    for line in script.split("\n"):
        if line.startswith("## "):
            if current: secs[current] = "\n".join(buf).strip()
            current = line[3:].strip().lower()
            buf = []
        else:
            buf.append(line)
    if current: secs[current] = "\n".join(buf).strip()
    return secs


def _merge_beats(a: dict, b: dict) -> dict:
    return {"beats": a["beats"] + b["beats"]}


def _write_beats_mirror(ch_id, folder, rows):
    beats_dir = get_project_dir(ch_id, folder.split("_")[1]) / "07_beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Beat Breakdown", ""]
    for r in rows:
        tag = "TEXT-ONLY" if r["text_only"] else " · ".join(r["elements"]) or "no elements"
        lines.append(f"## {r['id']} [{r['duration_sec']:.1f}s] {tag}")
        if r["svo"]: lines.append(f"svo: {r['svo']}")
        if r["overlay_text"]: lines.append(f"overlay: {r['overlay_text']}")
        lines.append(f'"{r["text"]}"')
        lines.append("")
    (beats_dir / "beats.md").write_text("\n".join(lines), encoding="utf-8")


@router.post("/projects/{project_id}/beats/extract")
async def extract_beats(project_id: str):
    try:
        return await _extract_beats_inner(project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Beats extract crashed: {type(e).__name__}: {e}")


async def _extract_beats_inner(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    script = await _get_locked_script(folder, project_id)
    if not script:
        raise HTTPException(400, "Lock a script first (Script Studio -> Lock).")

    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT id, names FROM characters WHERE project_id=? AND stale=0", (project_id,)) as cur:
        char_rows = await cur.fetchall()
    async with proj_db.execute("SELECT id, name FROM environments WHERE project_id=? AND stale=0", (project_id,)) as cur:
        env_rows = await cur.fetchall()
    async with proj_db.execute("SELECT id, text FROM world_records WHERE project_id=? AND stale=0", (project_id,)) as cur:
        world_rows = await cur.fetchall()
    await proj_db.close()

    name_to_id = {}
    for r in char_rows:
        for n in json.loads(r["names"]):
            name_to_id[n.strip().lower()] = r["id"]
    for r in env_rows:
        name_to_id[r["name"].strip().lower()] = r["id"]
    for r in world_rows:
        name_to_id[r["text"].strip().lower()] = r["id"]

    parsed, res = None, None
    for attempt in range(3):
        parsed, res = await sharded_extract(
            "beat_breakdown", BeatBreakdownResult,
            {"channel_id": ch_id, "asset_names": sorted(name_to_id.keys())},
            script, _merge_beats, project_id=project_id, channel_id=ch_id)
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

    sections = _parse_sections(script)

    proj_db = await get_project_db(folder)
    now = _now()
    async with proj_db.execute("SELECT id FROM beats WHERE project_id=?", (project_id,)) as cur:
        old_ids = [r["id"] for r in await cur.fetchall()]
    for bid in old_ids:
        await proj_db.execute("DELETE FROM beat_elements WHERE beat_id=?", (bid,))
    await proj_db.execute("DELETE FROM beats WHERE project_id=?", (project_id,))

    added, element_count, unmapped = 0, 0, 0
    rows_for_mirror = []
    for i, b in enumerate(parsed["beats"]):
        beat_id = await _next_id(proj_db, "beats", "B")
        b_text = b["text"]
        b_section = (b.get("section") or "").strip()
        b_svo = b.get("svo") or ""
        b_overlay = b.get("overlay_text") or ""
        b_textonly = bool(b.get("text_only"))
        words = len(b_text.split())
        dur = (words / 150.0) * 60.0
        chunk_text = sections.get(b_section.lower(), "")
        await proj_db.execute(
            "INSERT INTO beats (id, project_id, chunk_id, chunk_text, text, word_count, duration_sec, "
            "text_only, svo, overlay_text, overlay_spec, sort_order, stale, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
            (beat_id, project_id, b_section, chunk_text, b_text, words, dur,
             1 if b_textonly else 0, b_svo, b_overlay, "", i, now, now))

        el_tags = []
        for j, el in enumerate(b.get("elements") or []):
            asset_id = name_to_id.get((el.get("name") or "").strip().lower())
            if not asset_id:
                unmapped += 1
                continue
            be_id = await _next_id(proj_db, "beat_elements", "BE")
            await proj_db.execute(
                "INSERT INTO beat_elements (id, beat_id, asset_ref, layer, framing, prompt_text, "
                "refs_to_attach, editor_note, improv_note, is_one_off, sort_order, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?)",
                (be_id, beat_id, asset_id, el.get("layer") or "midground",
                 el.get("framing") or "medium", "", "", "", "", j, now, now))
            element_count += 1
            el_tags.append(f"{asset_id}/{el.get('layer') or 'midground'}")
        added += 1
        rows_for_mirror.append({"id": beat_id, "text": b_text, "svo": b_svo,
                                "overlay_text": b_overlay, "text_only": b_textonly,
                                "duration_sec": dur, "elements": el_tags})

    await proj_db.commit()
    await proj_db.close()

    _write_beats_mirror(ch_id, folder, rows_for_mirror)
    return {"beats": added, "elements": element_count, "unmapped": unmapped}


@router.get("/projects/{project_id}/beats")
async def list_beats(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT * FROM beats WHERE project_id=? AND stale=0 ORDER BY sort_order", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        async with proj_db.execute(
            "SELECT * FROM beat_elements WHERE beat_id=? ORDER BY sort_order", (r["id"],)) as cur:
            r["elements"] = [dict(x) for x in await cur.fetchall()]
    await proj_db.close()
    return rows


@router.delete("/projects/{project_id}/beats/{beat_id}")
async def delete_beat(project_id: str, beat_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    await proj_db.execute("DELETE FROM beat_elements WHERE beat_id=?", (beat_id,))
    await proj_db.execute("DELETE FROM beats WHERE id=? AND project_id=?", (beat_id, project_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "deleted"}


@router.get("/projects/{project_id}/beats/{beat_id}/assets")
async def beat_assets(project_id: str, beat_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM beats WHERE id=? AND project_id=?", (beat_id, project_id)) as cur:
        beat = await cur.fetchone()
    if not beat:
        await proj_db.close()
        raise HTTPException(404, "Beat not found")
    async with proj_db.execute("SELECT * FROM beat_elements WHERE beat_id=? ORDER BY sort_order", (beat_id,)) as cur:
        elements = [dict(r) for r in await cur.fetchall()]

    async with proj_db.execute("SELECT * FROM library WHERE project_id=?", (project_id,)) as cur:
        lib_by_ref = {r["asset_ref"]: dict(r) for r in await cur.fetchall() if r["asset_ref"]}
    async with proj_db.execute("SELECT id, names FROM characters WHERE project_id=?", (project_id,)) as cur:
        char_titles = {r["id"]: json.loads(r["names"])[0] for r in await cur.fetchall()}
    async with proj_db.execute("SELECT id, name FROM environments WHERE project_id=?", (project_id,)) as cur:
        env_titles = {r["id"]: r["name"] for r in await cur.fetchall()}
    await proj_db.close()

    manifest = []
    for el in elements:
        ref = el["asset_ref"]
        lib = lib_by_ref.get(ref)
        entry = {
            "asset_ref": ref, "layer": el["layer"], "framing": el["framing"],
            "kind": "character" if ref in char_titles else ("environment" if ref in env_titles else "world"),
            "title": char_titles.get(ref) or env_titles.get(ref) or (lib["title"] if lib else ref),
            "status": lib["status"] if lib else "missing",
            "file_path": (lib["file_path"] or None) if lib else None,
            "lib_id": lib["id"] if lib else None,
        }
        manifest.append(entry)

    ready = sum(1 for m in manifest if m["status"] == "ready")
    return {"beat_id": beat_id, "text": beat["text"], "svo": beat["svo"],
            "duration_sec": beat["duration_sec"], "overlay_text": beat["overlay_text"],
            "ready": ready, "total": len(manifest), "assets": manifest}

