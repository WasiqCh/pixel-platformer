# backend/api/generation.py
import asyncio
import base64
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core.llm_client import dispatch
from backend.db.connection import get_app_db, get_project_db
from backend.models.scene import SvgGen
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["generation"])

_RUNNING = {"project": None}


class ImageSettings(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _get_cfg():
    db = await get_app_db()
    async with db.execute("SELECT * FROM image_settings WHERE id=1") as cur:
        row = await cur.fetchone()
    if not row:
        await db.execute("INSERT INTO image_settings (id, provider, api_key, model, updated_at) "
                         "VALUES (1,'manual','','gemini-2.5-flash-image','')")
        await db.commit()
        await db.close()
        return {"provider": "manual", "api_key": "", "model": "gemini-2.5-flash-image"}
    await db.close()
    return dict(row)


@router.get("/settings/image")
async def get_image_settings():
    cfg = await _get_cfg()
    out = dict(cfg)
    out["api_key"] = (cfg["api_key"][:4] + "..." + cfg["api_key"][-4:]) if len(cfg["api_key"]) > 8 else ""
    return out


@router.put("/settings/image")
async def put_image_settings(data: ImageSettings):
    cfg = await _get_cfg()
    db = await get_app_db()
    await db.execute("UPDATE image_settings SET provider=?, api_key=?, model=?, updated_at=? WHERE id=1",
                     (data.provider or cfg["provider"],
                      data.api_key if data.api_key is not None else cfg["api_key"],
                      data.model or cfg["model"], _now()))
    await db.commit()
    await db.close()
    return {"status": "saved"}


async def _proj(project_id):
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


async def _gemini_image(prompt, ref_bytes, model, key):
    parts = [{"text": prompt}]
    if ref_bytes:
        parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(ref_bytes).decode()}})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    async with httpx.AsyncClient(timeout=180) as cl:
        r = await cl.post(url, json={"contents": [{"parts": parts}]})
    if r.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    for part in (data.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
        blob = part.get("inlineData") or part.get("inline_data")
        if blob:
            return base64.b64decode(blob["data"])
    raise RuntimeError("Gemini returned no image (maybe rate-limited - retry in 30s)")


async def _generate_row(project_id, folder, ch_id, gen_id):
    cfg = await _get_cfg()
    if cfg["provider"] != "gemini" or not cfg["api_key"]:
        raise HTTPException(400, "Set your free Gemini API key first (⚙️ Generation Queue). Get one at https://aistudio.google.com/apikey")
    base = get_project_dir(ch_id, folder.split("_")[1])
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM generations WHERE id=? AND project_id=?", (gen_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close(); raise HTTPException(404, "Generation not found")
    row = dict(row)

    # SCENES-MP4 P2-T02: svg rows live in the SVG lane (svg_path source, P2-T04
    # generates; P2-T06 rasters into file_path). The Gemini PNG lane below is
    # masters/poses only — never let it fill an svg row's file_path.
    if row["kind"] == "svg":
        await proj_db.close()
        raise HTTPException(400, "SVG assets generate via the SVG pipeline (P2-T04), not the PNG lane.")

    ref_rel = None
    if row["kind"] == "pose":
        async with proj_db.execute("SELECT file_path FROM generations WHERE project_id=? AND kind='master' AND asset_ref=? AND status='ready'", (project_id, row["asset_ref"])) as cur:
            m = await cur.fetchone()
        if m: ref_rel = m["file_path"]
    if not ref_rel:
        async with proj_db.execute("SELECT file_path FROM library WHERE asset_ref=? AND status='ready' AND project_id=?", (row["asset_ref"], project_id)) as cur:
            l = await cur.fetchone()
        if l: ref_rel = l["file_path"]
    ref_bytes = (base / ref_rel).read_bytes() if ref_rel and (base / ref_rel).exists() else None

    try:
        img = await _gemini_image(row["prompt"], ref_bytes, cfg["model"], cfg["api_key"])
    except Exception as e:
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?", (str(e)[:300], _now(), gen_id))
        await proj_db.commit(); await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": str(e)[:300]}

    rel = f"06_assets/generated/{row['gen_label']}_{row['asset_ref']}" + (f"_{row['beat_id']}" if row["beat_id"] else "") + ".png"
    dest = base / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(img)
    await proj_db.execute("UPDATE generations SET status='ready', file_path=?, error='', updated_at=? WHERE id=?", (rel, _now(), gen_id))
    if row["kind"] == "master":
        await proj_db.execute("UPDATE library SET file_path=?, status='ready', source='generated', updated_at=? WHERE asset_ref=? AND project_id=?", (rel, _now(), row["asset_ref"], project_id))
        from backend.core.vault import vault_put, asset_key
        vkind = "character" if row["asset_ref"].startswith("C") else ("environment" if row["asset_ref"].startswith("E") else "world")
        await vault_put(ch_id, asset_key(row["title"]), vkind, row["title"], dest, project_id)
    await proj_db.commit(); await proj_db.close()
    return {"gen_id": gen_id, "status": "ready", "file_path": rel}


# --- SCENES-MP4 P2-T04: single SVG generation (dispatch -> validate -> versioned file) ---

_SVG_FALLBACK_DESCRIPTOR = "clean flat 2D animation, bold outlines, limited palette"


def _sanitize_svg_base(raw: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", (raw or "").strip()).strip("_")
    return base[:60] or "asset"


def _next_svg_version(svg_dir, base: str) -> int:
    pat = re.compile(rf"^{re.escape(base)}_v(\d+)\.svg$", re.IGNORECASE)
    best = 0
    try:
        for p in svg_dir.iterdir():
            m = pat.match(p.name)
            if m:
                try:
                    best = max(best, int(m.group(1)))
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return best + 1


async def _svg_style_pack(ch_id: str) -> tuple[str, str]:
    from backend.api.channels import DEFAULT_AVOID
    db = await get_app_db()
    async with db.execute("SELECT descriptor, avoid_list FROM channels WHERE id=?", (ch_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    descriptor = (row["descriptor"] if row and row["descriptor"] else _SVG_FALLBACK_DESCRIPTOR)
    avoid = (row["avoid_list"] if row and row["avoid_list"] else DEFAULT_AVOID)
    return descriptor, avoid


def _build_svg_context(descriptor: str, avoid: str, asset_name: str,
                       asset_kind: str, asset_desc: str,
                       previous_svg: str = "", fix_note: str = "") -> dict:
    """SCENES-MP4 P2-T04/T05 shared context builder (extend, don't duplicate).

    Single place that shapes the svg_gen context pack: style + asset desc
    always present; previous_svg + fix_note empty on first gen (T04), filled
    on improve (T05) per the recipe's retry/improve rule.
    """
    return {
        "style_descriptor": descriptor,
        "palette": [],
        "asset_name": asset_name,
        "asset_kind": asset_kind,
        "asset_description": asset_desc,
        "previous_svg": previous_svg or "",
        "fix_note": fix_note or "",
        "avoid_list": avoid,
    }


async def _svg_asset_info(proj_db, row: dict, gen_id: int) -> tuple[str, str, str]:
    """Shared asset-kind/description/name lookup (T04 first-gen + T05 improve).

    Prefers the linked scene_assets need (validated kind + search_query);
    falls back to the generation prompt. Returns (kind, desc, name).
    """
    asset_kind, asset_desc = "prop", row["prompt"] or row["title"] or ""
    try:
        async with proj_db.execute(
                "SELECT kind, search_query, name, reasoning FROM scene_assets WHERE generation_id=?",
                (gen_id,)) as cur:
            need = await cur.fetchone()
        if need:
            need = dict(need)
            if (need.get("kind") or "").lower() in ("character", "prop", "place", "photo"):
                asset_kind = need["kind"].lower()
            bits = [need.get("name") or row["title"] or ""]
            if need.get("search_query"):
                bits.append(f"({need['search_query']})")
            if row["prompt"]:
                bits.append(f"— {row['prompt']}")
            asset_desc = " ".join(b for b in bits if b)
    except Exception:
        pass
    asset_name = row["title"] or row["gen_label"] or f"gen{gen_id}"
    return asset_kind, asset_desc, asset_name


def _list_svg_versions(svg_dir, base: str) -> list[int]:
    pat = re.compile(rf"^{re.escape(base)}_v(\d+)\.svg$", re.IGNORECASE)
    out = []
    try:
        for p in svg_dir.iterdir():
            m = pat.match(p.name)
            if m:
                try:
                    out.append(int(m.group(1)))
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return sorted(out)


async def _generate_svg_row(project_id, folder, ch_id, gen_id):
    base = get_project_dir(ch_id, folder.split("_")[1])
    svg_dir = base / "06_sheets" / "svg"
    svg_dir.mkdir(parents=True, exist_ok=True)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM generations WHERE id=? AND project_id=?", (gen_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close()
        raise HTTPException(404, "Generation not found")
    row = dict(row)
    if row["kind"] != "svg":
        await proj_db.close()
        raise HTTPException(400, "Only kind='svg' rows use the SVG pipeline (PNG lane handles masters/poses).")

    # P2-T04 context via the shared builder (T05 extends the same call with
    # previous_svg + fix_note — do not inline a second dict literal).
    asset_kind, asset_desc, asset_name = await _svg_asset_info(proj_db, row, gen_id)
    descriptor, avoid = await _svg_style_pack(ch_id)
    context = _build_svg_context(descriptor, avoid, asset_name,
                                 asset_kind, asset_desc)

    try:
        res = await dispatch("svg_gen", context, schema=SvgGen,
                             project_id=project_id, channel_id=ch_id)
    except Exception as e:
        msg = f"dispatch crashed: {type(e).__name__}: {str(e)[:200]}"
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?",
                              (msg[:300], _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": msg[:300]}
    if not res.get("ok"):
        msg = str(res.get("error") or "svg_gen failed")[:300]
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?",
                              (msg, _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": msg}

    svg_text = (res["parsed"] or {}).get("svg") or ""
    reasoning = (res["parsed"] or {}).get("reasoning") or ""
    label = row["gen_label"] or row["asset_ref"] or f"gen{gen_id}"
    clean = _sanitize_svg_base(label)
    try:
        ver = _next_svg_version(svg_dir, clean)
        rel = f"06_sheets/svg/{clean}_v{ver}.svg"
        (svg_dir / f"{clean}_v{ver}.svg").write_text(svg_text, encoding="utf-8")
    except Exception as e:
        msg = f"write failed: {type(e).__name__}: {str(e)[:200]}"
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?",
                              (msg[:300], _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": msg[:300]}

    await proj_db.execute(
        "UPDATE generations SET svg_path=?, status='generated', error='', updated_at=? WHERE id=?",
        (rel, _now(), gen_id))
    await proj_db.commit()
    await proj_db.close()
    return {"gen_id": gen_id, "status": "generated", "svg_path": rel,
            "version": ver, "reasoning": reasoning}


@router.post("/projects/{project_id}/generate/svg/{gen_id}")
async def generate_svg_one(project_id: str, gen_id: int):
    folder, ch_id = await _proj(project_id)
    return await _generate_svg_row(project_id, folder, ch_id, gen_id)


# --- SCENES-MP4 P2-T05: improve-with-note (-> _v(N+1)) + revert (pointer only) ---

class SvgImproveRequest(BaseModel):
    note: str


class SvgRevertRequest(BaseModel):
    version: int


async def _improve_svg_row(project_id, folder, ch_id, gen_id, note: str):
    note = (note or "").strip()
    if not note:
        raise HTTPException(400, "note must be non-empty (what should change in the next version?)")
    base = get_project_dir(ch_id, folder.split("_")[1])
    svg_dir = base / "06_sheets" / "svg"
    svg_dir.mkdir(parents=True, exist_ok=True)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM generations WHERE id=? AND project_id=?", (gen_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close()
        raise HTTPException(404, "Generation not found")
    row = dict(row)
    if row["kind"] != "svg":
        await proj_db.close()
        raise HTTPException(400, "Only kind='svg' rows use the SVG pipeline.")
    if not row["svg_path"]:
        await proj_db.close()
        raise HTTPException(400, "No SVG version yet — generate once before improving.")
    prev_file = base / row["svg_path"]
    if not prev_file.exists():
        await proj_db.close()
        raise HTTPException(400, f"Previous SVG file missing on disk: {row['svg_path']}")
    try:
        previous_svg = prev_file.read_text(encoding="utf-8")
    except Exception as e:
        await proj_db.close()
        raise HTTPException(400, f"Cannot read previous SVG: {type(e).__name__}")
    if not previous_svg.strip():
        await proj_db.close()
        raise HTTPException(400, "Previous SVG is empty — cannot improve.")

    # Same context construction as first-gen (T04), extended with the
    # previous code + the user's fix-note (recipe's retry/improve rule).
    asset_kind, asset_desc, asset_name = await _svg_asset_info(proj_db, row, gen_id)
    descriptor, avoid = await _svg_style_pack(ch_id)
    context = _build_svg_context(descriptor, avoid, asset_name,
                                 asset_kind, asset_desc,
                                 previous_svg=previous_svg, fix_note=note)

    try:
        res = await dispatch("svg_gen", context, schema=SvgGen,
                             project_id=project_id, channel_id=ch_id)
    except Exception as e:
        msg = f"dispatch crashed: {type(e).__name__}: {str(e)[:200]}"
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?",
                              (msg[:300], _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": msg[:300]}
    if not res.get("ok"):
        msg = str(res.get("error") or "svg_gen failed")[:300]
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?",
                              (msg, _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": msg}

    svg_text = (res["parsed"] or {}).get("svg") or ""
    reasoning = (res["parsed"] or {}).get("reasoning") or ""
    label = row["gen_label"] or row["asset_ref"] or f"gen{gen_id}"
    clean = _sanitize_svg_base(label)
    try:
        ver = _next_svg_version(svg_dir, clean)
        rel = f"06_sheets/svg/{clean}_v{ver}.svg"
        (svg_dir / f"{clean}_v{ver}.svg").write_text(svg_text, encoding="utf-8")
    except Exception as e:
        msg = f"write failed: {type(e).__name__}: {str(e)[:200]}"
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?",
                              (msg[:300], _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": msg[:300]}

    await proj_db.execute(
        "UPDATE generations SET svg_path=?, status='generated', error='', updated_at=? WHERE id=?",
        (rel, _now(), gen_id))
    await proj_db.commit()
    await proj_db.close()
    return {"gen_id": gen_id, "status": "generated", "svg_path": rel,
            "version": ver, "reasoning": reasoning,
            "previous_svg_path": row["svg_path"]}


@router.post("/projects/{project_id}/generate/svg/{gen_id}/improve")
async def improve_svg_one(project_id: str, gen_id: int, data: SvgImproveRequest):
    folder, ch_id = await _proj(project_id)
    return await _improve_svg_row(project_id, folder, ch_id, gen_id, data.note)


@router.post("/projects/{project_id}/generate/svg/{gen_id}/revert")
async def revert_svg_one(project_id: str, gen_id: int, data: SvgRevertRequest):
    folder, ch_id = await _proj(project_id)
    base = get_project_dir(ch_id, folder.split("_")[1])
    svg_dir = base / "06_sheets" / "svg"
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM generations WHERE id=? AND project_id=?", (gen_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close()
        raise HTTPException(404, "Generation not found")
    row = dict(row)
    if row["kind"] != "svg":
        await proj_db.close()
        raise HTTPException(400, "Only kind='svg' rows use the SVG pipeline.")
    if not data.version or data.version < 1:
        await proj_db.close()
        raise HTTPException(400, "version must be a positive integer (target _vN).")
    label = row["gen_label"] or row["asset_ref"] or f"gen{gen_id}"
    clean = _sanitize_svg_base(label)
    rel = f"06_sheets/svg/{clean}_v{data.version}.svg"
    if not (svg_dir / f"{clean}_v{data.version}.svg").exists():
        await proj_db.close()
        have = _list_svg_versions(svg_dir, clean)
        raise HTTPException(404, f"Version v{data.version} not on disk (have versions {have}).")
    # Revert = move the newest pointer back; history files stay intact.
    await proj_db.execute(
        "UPDATE generations SET svg_path=?, status='generated', error='', updated_at=? WHERE id=?",
        (rel, _now(), gen_id))
    await proj_db.commit()
    await proj_db.close()
    return {"gen_id": gen_id, "status": "generated", "svg_path": rel,
            "version": data.version}


@router.get("/projects/{project_id}/generate/svg/{gen_id}/versions")
async def list_svg_versions(project_id: str, gen_id: int):
    folder, ch_id = await _proj(project_id)
    base = get_project_dir(ch_id, folder.split("_")[1])
    svg_dir = base / "06_sheets" / "svg"
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT gen_label, asset_ref, svg_path, status FROM generations WHERE id=? AND project_id=?",
                               (gen_id, project_id)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    if not row:
        raise HTTPException(404, "Generation not found")
    row = dict(row)
    clean = _sanitize_svg_base(row["gen_label"] or row["asset_ref"] or f"gen{gen_id}")
    vers = _list_svg_versions(svg_dir, clean)
    return {"gen_id": gen_id, "current_svg_path": row["svg_path"], "status": row["status"],
            "versions": [f"06_sheets/svg/{clean}_v{v}.svg" for v in vers]}


@router.get("/projects/{project_id}/generations")
async def list_generations(project_id: str):
    folder, ch_id = await _proj(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT * FROM generations WHERE project_id=? ORDER BY CASE kind WHEN 'master' THEN 0 ELSE 1 END, id",
        (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    return {"running": _RUNNING["project"] == project_id, "rows": rows}


@router.post("/projects/{project_id}/generate/{gen_id}")
async def generate_one(project_id: str, gen_id: int):
    folder, ch_id = await _proj(project_id)
    return await _generate_row(project_id, folder, ch_id, gen_id)


@router.post("/projects/{project_id}/generate/all")
async def generate_all(project_id: str):
    if _RUNNING["project"]:
        raise HTTPException(400, "A generation run is already in progress.")
    folder, ch_id = await _proj(project_id)
    asyncio.create_task(_run_all(project_id, folder, ch_id))
    return {"status": "started"}


async def _run_all(project_id, folder, ch_id):
    _RUNNING["project"] = project_id
    try:
        proj_db = await get_project_db(folder)
        async with proj_db.execute(
            "SELECT id FROM generations WHERE project_id=? AND status!='ready' "
            "ORDER BY CASE kind WHEN 'master' THEN 0 ELSE 1 END, id", (project_id,)) as cur:
            ids = [r["id"] for r in await cur.fetchall()]
        await proj_db.close()
        for gid in ids:
            try:
                await _generate_row(project_id, folder, ch_id, gid)
            except HTTPException:
                break
            await asyncio.sleep(4)
    finally:
        _RUNNING["project"] = None


@router.get("/projects/{project_id}/generations/{gen_id}/image")
async def gen_image(project_id: str, gen_id: int):
    folder, ch_id = await _proj(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT file_path FROM generations WHERE id=? AND project_id=?", (gen_id, project_id)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    if not row or not row["file_path"]:
        raise HTTPException(404, "No image yet")
    p = get_project_dir(ch_id, folder.split("_")[1]) / row["file_path"]
    if not p.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(p, media_type="image/png")
