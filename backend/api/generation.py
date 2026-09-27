# backend/api/generation.py
import asyncio
import base64
import glob as _glob
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core.llm_client import dispatch
from backend.db.connection import get_app_db, get_project_db
from backend.models.scene import SvgGen, validate_svg_text
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["generation"])

_RUNNING = {"project": None}

# SCENES-MP4 P2-T06: Inkscape probe (DECISION_RASTER §18 rules 1-2).
# Order: INKSCAPE_PATH env -> PATH (inkscape) -> MSIX location glob.
# The MSIX pattern keeps the version wildcarded (version-pinned path WILL
# break on update — never hard-code the full path). The Appx fallback below
# queries the package manager for the live InstallLocation for the same reason.
_INKSCAPE_MSIX_GLOB = (
    r"C:\Program Files\WindowsApps\25415Inkscape.Inkscape_*"
    r"\VFS\ProgramFilesX64\Inkscape\bin\inkscape.exe"
)


def _probe_inkscape() -> tuple[str, str, list[str]]:
    """Probe for the Inkscape headless binary. Returns (path, source, tried).

    source is one of 'env' | 'PATH' | 'MSIX-glob' | 'MSIX-appx'.
    tried lists every location checked (for the clear-error rule).
    Raises FileNotFoundError naming every location tried when not found.
    """
    tried: list[str] = []
    env = (os.environ.get("INKSCAPE_PATH") or "").strip().strip('"')
    if env:
        tried.append(f"INKSCAPE_PATH={env}")
        if os.path.isfile(env):
            return env, "env", tried
        tried.append(f"INKSCAPE_PATH missing on disk: {env}")
    else:
        tried.append("INKSCAPE_PATH=(unset)")
    which = shutil.which("inkscape")
    tried.append(f"PATH:inkscape={'found ' + which if which else 'not found'}")
    if which and os.path.isfile(which):
        return which, "PATH", tried
    try:
        hits = sorted(_glob.glob(_INKSCAPE_MSIX_GLOB))
    except Exception as e:
        hits = []
        tried.append(f"MSIX glob failed: {type(e).__name__}: {e}")
    tried.append(f"MSIX glob {_INKSCAPE_MSIX_GLOB} -> {len(hits)} hit(s)")
    for h in hits:
        if os.path.isfile(h):
            return h, "MSIX-glob", tried
    # WindowsApps directory listing is permission-gated (glob can return []
    # even when the package exists), so resolve via the package manager —
    # no version hard-coded, uses the live InstallLocation.
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-AppxPackage -Name '*Inkscape*' | Select-Object -ExpandProperty InstallLocation"],
            capture_output=True, text=True, timeout=10)
        locs = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        tried.append(f"MSIX AppxPackage InstallLocation -> {locs if locs else 'none'}")
        for loc in locs:
            cand = os.path.join(loc, "VFS", "ProgramFilesX64", "Inkscape", "bin", "inkscape.exe")
            if os.path.isfile(cand):
                return cand, "MSIX-appx", tried
            tried.append(f"MSIX candidate missing: {cand}")
    except Exception as e:
        tried.append(f"MSIX Appx query failed: {type(e).__name__}: {e}")
    raise FileNotFoundError(
        "Inkscape not found. Tried: " + " | ".join(tried))


def _svg_content_hash(data: bytes) -> tuple[str, str]:
    """Hash-keyed cache identity: full sha256 + 12-char short for filenames."""
    full = hashlib.sha256(data).hexdigest()
    return full, full[:12]


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


# --- SCENES-MP4 D7-T01: bulk SVG re-generate (sequential, per-row isolation) ---
# NOTE: registered BEFORE /generate/svg/{gen_id} so the literal 'bulk' is
# never captured as gen_id (FastAPI matches in registration order).
# POST /projects/{id}/generate/svg/bulk {only: 'non-final'}: sequential loop
# over kind='svg' rows not yet final, calling the existing per-row
# _generate_svg_row (new version each, never overwrite) with per-row crash
# isolation (one gen's failure lands in its error field / result entry, never
# kills the batch — mirrors the PNG-lane generate/all shape but stays in the
# SVG lane, synchronous so the summary returns in the response). No frontend.
# Optional limit caps rows processed (safe proving on 2-3 rows without
# blasting the whole base; omitted = all non-final).

_SVG_BULK_RUNNING = {"project": None}


class SvgBulkRequest(BaseModel):
    only: str = "non-final"
    limit: Optional[int] = None


@router.post("/projects/{project_id}/generate/svg/bulk")
async def bulk_generate_svg(project_id: str, data: SvgBulkRequest):
    if (data.only or "") != "non-final":
        raise HTTPException(400, "only must be 'non-final' (previously-final rows stay untouched).")
    if data.limit is not None and (not isinstance(data.limit, int) or data.limit < 1):
        raise HTTPException(400, "limit must be a positive integer when given.")
    if _SVG_BULK_RUNNING["project"]:
        raise HTTPException(400, "An SVG bulk run is already in progress.")
    folder, ch_id = await _proj(project_id)
    proj_db = await get_project_db(folder)
    try:
        async with proj_db.execute(
            "SELECT id, status FROM generations WHERE project_id=? AND kind='svg' ORDER BY id",
            (project_id,)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    finally:
        await proj_db.close()
    skipped_final = sum(1 for r in rows if r["status"] == "final")
    targets = [r["id"] for r in rows if r["status"] != "final"]
    if data.limit is not None:
        targets = targets[:data.limit]
    _SVG_BULK_RUNNING["project"] = project_id
    results: list[dict] = []
    try:
        # Sequential await (never gather): one LLM call at a time, same as the
        # D8-T01 frontend loop but server-side. Each row isolated: any raise
        # becomes a failed entry, the batch always continues.
        for gid in targets:
            try:
                res = await _generate_svg_row(project_id, folder, ch_id, gid)
            except HTTPException as e:
                results.append({"gen_id": gid, "status": "error",
                                "error": f"HTTP {e.status_code}: {e.detail}"[:300]})
                continue
            except Exception as e:
                results.append({"gen_id": gid, "status": "error",
                                "error": f"bulk crashed: {type(e).__name__}: {str(e)[:200]}"[:300]})
                continue
            results.append(res)
    finally:
        _SVG_BULK_RUNNING["project"] = None
    regenerated = sum(1 for r in results if r.get("status") == "generated")
    failed = sum(1 for r in results if r.get("status") != "generated")
    return {"only": "non-final", "processed": len(targets),
            "regenerated": regenerated, "failed": failed,
            "skipped_final": skipped_final, "total_svg": len(rows),
            "results": results}


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


# --- SCENES-MP4 D2-T02: paste-code (external SVG validated like AI output) ---

class SvgPasteRequest(BaseModel):
    code: str


async def _paste_svg_row(project_id, folder, ch_id, gen_id, code: str):
    """Paste external SVG code as a new versioned _vN.svg (manual-always-valid).

    Validates through the real SvgGen/validate_svg_text path (same messages
    AI output gets), writes versioned file, moves the newest pointer
    (history intact — same semantics as improve). Works on pending rows
    (skip-generation: user brings code instead of AI) and on generated rows
    (new version); approved/final rows demote to generated (needs re-approve,
    same as improve). Sets source='pasted' so the D2-T01 badge reads PASTED.
    """
    text = (code or "").strip()
    if not text:
        raise HTTPException(400, "code must be non-empty (paste SVG markup).")
    try:
        clean_svg = validate_svg_text(text)
    except ValueError as e:
        # Same validator AI output goes through (SvgGen._svg_must_be_safe) —
        # same message, nothing written.
        raise HTTPException(400, str(e)[:300])
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
    label = row["gen_label"] or row["asset_ref"] or f"gen{gen_id}"
    clean = _sanitize_svg_base(label)
    previous = row.get("svg_path") or ""
    try:
        ver = _next_svg_version(svg_dir, clean)
        rel = f"06_sheets/svg/{clean}_v{ver}.svg"
        (svg_dir / f"{clean}_v{ver}.svg").write_text(clean_svg, encoding="utf-8")
    except Exception as e:
        msg = f"write failed: {type(e).__name__}: {str(e)[:200]}"
        await proj_db.close()
        raise HTTPException(500, msg[:300])
    await proj_db.execute(
        "UPDATE generations SET svg_path=?, status='generated', source='pasted', "
        "error='', updated_at=? WHERE id=?",
        (rel, _now(), gen_id))
    await proj_db.commit()
    await proj_db.close()
    return {"gen_id": gen_id, "status": "generated", "svg_path": rel,
            "version": ver, "source": "pasted",
            "previous_svg_path": previous or None}


@router.post("/projects/{project_id}/generate/svg/{gen_id}/paste")
async def paste_svg_one(project_id: str, gen_id: int, data: SvgPasteRequest):
    folder, ch_id = await _proj(project_id)
    return await _paste_svg_row(project_id, folder, ch_id, gen_id, data.code)


# --- SCENES-MP4 P2-T06: approve -> raster PNG (hash-keyed cache) + finalize ---
# Status ladder: generated -> approved -> final. Approve rasterizes the current
# svg_path into 06_sheets/raster/<base>_<hash12>.png via Inkscape headless;
# identical SVG bytes = cache hit (no re-raster). file_path holds the PNG so
# the existing GET .../generations/{gen_id}/image endpoint serves the render.
# Approval UI shows that PNG, never the SVG source.

_RASTER_W, _RASTER_H = 1920, 1080


async def _approve_svg_row(project_id, folder, ch_id, gen_id):
    base = get_project_dir(ch_id, folder.split("_")[1])
    svg_dir = base / "06_sheets" / "svg"
    raster_dir = base / "06_sheets" / "raster"
    raster_dir.mkdir(parents=True, exist_ok=True)
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
        raise HTTPException(400, "No SVG version yet — generate once before approving.")
    svg_file = base / row["svg_path"]
    if not svg_file.exists():
        await proj_db.close()
        raise HTTPException(400, f"SVG file missing on disk: {row['svg_path']}")
    try:
        svg_bytes = svg_file.read_bytes()
    except Exception as e:
        await proj_db.close()
        raise HTTPException(400, f"Cannot read SVG: {type(e).__name__}")
    if not svg_bytes.strip():
        await proj_db.close()
        raise HTTPException(400, "SVG is empty — cannot approve.")
    full_hash, short = _svg_content_hash(svg_bytes)
    label = row["gen_label"] or row["asset_ref"] or f"gen{gen_id}"
    clean = _sanitize_svg_base(label)
    rel = f"06_sheets/raster/{clean}_{short}.png"
    dest = base / rel

    # Cache hit: PNG for these exact bytes already on disk — no re-raster.
    # Keep 'final' final on re-approve (don't demote); otherwise approved.
    if dest.exists() and dest.stat().st_size > 0:
        target = "final" if row["status"] == "final" and row["file_path"] == rel else "approved"
        await proj_db.execute(
            "UPDATE generations SET file_path=?, status=?, error='', updated_at=? WHERE id=?",
            (rel, target, _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": target, "svg_path": row["svg_path"],
                "file_path": rel, "svg_hash": full_hash, "cached": True,
                "raster_path": rel}

    try:
        inkscape, source, tried = _probe_inkscape()
    except FileNotFoundError as e:
        msg = str(e)[:300]
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?",
                              (msg, _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": msg}
    cmd = [inkscape, str(svg_file), "--export-type=png",
           f"--export-filename={dest}", "-w", str(_RASTER_W), "-h", str(_RASTER_H)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        msg = f"raster crashed: {type(e).__name__}: {str(e)[:200]}"
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?",
                              (msg[:300], _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": msg[:300]}
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        err = (r.stderr or r.stdout or f"exit {r.returncode}")[-250:]
        msg = f"inkscape failed (exit {r.returncode}): {err}"[:300]
        await proj_db.execute("UPDATE generations SET status='error', error=?, updated_at=? WHERE id=?",
                              (msg, _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "error", "error": msg}
    await proj_db.execute(
        "UPDATE generations SET file_path=?, status='approved', error='', updated_at=? WHERE id=?",
        (rel, _now(), gen_id))
    await proj_db.commit()
    await proj_db.close()
    return {"gen_id": gen_id, "status": "approved", "svg_path": row["svg_path"],
            "file_path": rel, "svg_hash": full_hash, "cached": False,
            "raster_path": rel, "inkscape_source": source}


@router.post("/projects/{project_id}/generate/svg/{gen_id}/approve")
async def approve_svg_one(project_id: str, gen_id: int):
    folder, ch_id = await _proj(project_id)
    return await _approve_svg_row(project_id, folder, ch_id, gen_id)


@router.post("/projects/{project_id}/generate/svg/{gen_id}/finalize")
async def finalize_svg_one(project_id: str, gen_id: int):
    folder, ch_id = await _proj(project_id)
    base = get_project_dir(ch_id, folder.split("_")[1])
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
    if row["status"] == "final":
        await proj_db.close()
        return {"gen_id": gen_id, "status": "final", "file_path": row["file_path"]}
    if row["status"] != "approved":
        await proj_db.close()
        raise HTTPException(400, f"Approve first (status is '{row['status']}', need 'approved').")
    if not row["file_path"] or not (base / row["file_path"]).exists():
        await proj_db.close()
        raise HTTPException(400, f"Raster PNG missing on disk: {row['file_path'] or '(none)'} — re-approve.")
    await proj_db.execute(
        "UPDATE generations SET status='final', error='', updated_at=? WHERE id=?",
        (_now(), gen_id))
    await proj_db.commit()
    await proj_db.close()
    return {"gen_id": gen_id, "status": "final", "file_path": row["file_path"]}


# --- SCENES-MP4 D2-T03: SVG playground (validate + raster, no project writes) ---
# POST /projects/{id}/svg-playground {code}: validates pasted code through
# the real SvgGen/validate_svg_text path (same messages AI output + paste
# get), rasters via the P2-T06 Inkscape probe to a hash-named temp PNG under
# %TEMP% (never into project dirs), and returns the PNG bytes for preview +
# download. NEVER opens the project DB (only _proj's app.db read to 404
# unknown projects) — project.db stays byte-identical by construction.

class SvgPlaygroundRequest(BaseModel):
    code: str


@router.post("/projects/{project_id}/svg-playground")
async def svg_playground(project_id: str, data: SvgPlaygroundRequest):
    await _proj(project_id)
    text = (data.code or "").strip()
    if not text:
        raise HTTPException(400, "code must be non-empty (paste SVG markup).")
    try:
        clean_svg = validate_svg_text(text)
    except ValueError as e:
        # Same validator AI output + D2-T02 paste go through — same message,
        # nothing written anywhere.
        raise HTTPException(400, str(e)[:300])
    _full_hash, short = _svg_content_hash(clean_svg.encode("utf-8"))
    svg_tmp = os.path.join(tempfile.gettempdir(), f"svg_playground_{short}.svg")
    png_tmp = os.path.join(tempfile.gettempdir(), f"svg_playground_{short}.png")
    fname = f"svg_playground_{short}.png"
    # Cache hit: identical pastes raster once — same bytes back, no re-raster.
    if os.path.isfile(png_tmp) and os.path.getsize(png_tmp) > 0:
        return FileResponse(png_tmp, media_type="image/png", filename=fname,
                            headers={"X-Svg-Hash": _full_hash,
                                     "X-Playground-Cached": "true"})
    try:
        with open(svg_tmp, "w", encoding="utf-8") as f:
            f.write(clean_svg)
    except Exception as e:
        raise HTTPException(500, f"temp write failed: {type(e).__name__}: {str(e)[:200]}")
    try:
        inkscape, source, _tried = _probe_inkscape()
    except FileNotFoundError as e:
        raise HTTPException(500, str(e)[:300])
    cmd = [inkscape, svg_tmp, "--export-type=png",
           f"--export-filename={png_tmp}", "-w", str(_RASTER_W), "-h", str(_RASTER_H)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        raise HTTPException(500, f"raster crashed: {type(e).__name__}: {str(e)[:200]}")
    if r.returncode != 0 or not os.path.isfile(png_tmp) or os.path.getsize(png_tmp) == 0:
        err = (r.stderr or r.stdout or f"exit {r.returncode}")[-250:]
        raise HTTPException(500, f"inkscape failed (exit {r.returncode}): {err}"[:300])
    return FileResponse(png_tmp, media_type="image/png", filename=fname,
                        headers={"X-Svg-Hash": _full_hash,
                                 "X-Playground-Cached": "false",
                                 "X-Inkscape-Source": source})


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
