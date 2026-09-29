# backend/api/generation.py
import asyncio
import base64
import glob as _glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
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

    SCENES-MP4 I-T01: for needs matched to a character/environment, appends
    its extracted identity (characters.appearance / environments.elements)
    into the description server-side. No recipe change (description key
    already exists). Unmatched/generic needs stay byte-identical.
    """
    asset_kind, asset_desc = "prop", row["prompt"] or row["title"] or ""
    need_name, need_query = "", ""
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
            need_name = need.get("name") or ""
            need_query = need.get("search_query") or ""
    except Exception:
        pass
    # I-T01 identity append (character -> appearance, place -> elements).
    # Generic kinds (prop/photo) skip entirely -> byte-identical. Matched
    # kinds with no record match or empty identity also stay identical.
    # Every failure falls through silently (never break the draw call).
    try:
        if asset_kind in ("character", "place") and (need_name or need_query):
            project_id = row.get("project_id")
            if project_id:
                if asset_kind == "character":
                    async with proj_db.execute(
                            "SELECT names, appearance FROM characters "
                            "WHERE project_id=? AND stale=0 ORDER BY id",
                            (project_id,)) as cur:
                        chars = [dict(r) for r in await cur.fetchall()]
                    for ch in chars:
                        try:
                            aliases = json.loads(ch.get("names") or "[]")
                        except Exception:
                            aliases = []
                        if not isinstance(aliases, list):
                            aliases = [aliases]
                        hit = any(
                            _identity_entry_matches(need_name, need_query, str(a or ""))
                            for a in aliases if str(a or "").strip()
                        )
                        if hit:
                            appearance = (ch.get("appearance") or "").strip()
                            if appearance:
                                asset_desc = (
                                    f"{asset_desc} Identity (locked appearance — "
                                    f"draw exactly, do not redesign): {appearance}"
                                )
                            break
                else:  # place -> environments.elements
                    async with proj_db.execute(
                            "SELECT name, elements FROM environments "
                            "WHERE project_id=? AND stale=0 ORDER BY id",
                            (project_id,)) as cur:
                        envs = [dict(r) for r in await cur.fetchall()]
                    for env in envs:
                        env_name = env.get("name") or ""
                        if not _identity_entry_matches(need_name, need_query, env_name):
                            continue
                        try:
                            elems = json.loads(env.get("elements") or "[]")
                        except Exception:
                            elems = []
                        if isinstance(elems, str):
                            elems = [elems]
                        elems = [str(e).strip() for e in (elems or []) if str(e or "").strip()]
                        if elems:
                            asset_desc = (
                                f"{asset_desc} Identity (locked elements — "
                                f"draw exactly, do not redesign): {'; '.join(elems)}"
                            )
                        break
    except Exception:
        pass
    asset_name = row["title"] or row["gen_label"] or f"gen{gen_id}"
    return asset_kind, asset_desc, asset_name


# --- SCENES-MP4 I-T01: identity matching (mirrors scenes._entry_matches) ---
# Same discipline as the library-match path so identity agrees with the rest
# of asset planning: exact -> substring (len>=4) -> sig-token subset -> >=2
# token overlap. Local copy (not an import) to keep generation.py
# self-contained; scenes.py owns the canonical version.

_IDENTITY_STOPWORDS = frozenset(
    "a an the of and or in on at to for with from by as is are was were be been "
    "this that these those its it s".split()
)


def _identity_norm(s: str) -> str:
    return re.sub(r"[^\w]+", " ", (s or "").lower(), flags=re.UNICODE).strip()


def _identity_sig_tokens(s: str) -> list[str]:
    return [t for t in _identity_norm(s).split() if t not in _IDENTITY_STOPWORDS and len(t) > 1]


def _identity_entry_matches(need_name: str, search_query: str, candidate: str) -> bool:
    n_name, n_query, n_cand = (
        _identity_norm(need_name), _identity_norm(search_query), _identity_norm(candidate))
    if not n_cand or (not n_name and not n_query):
        return False
    if n_name and n_name == n_cand:
        return True
    if n_query and n_query == n_cand:
        return True
    if n_name and len(n_name) >= 4 and (n_name in n_cand or n_cand in n_name):
        return True
    if n_query and len(n_query) >= 4 and (n_query in n_cand or n_cand in n_query):
        return True
    t_cand = set(n_cand.split())
    for sig in (_identity_sig_tokens(need_name), _identity_sig_tokens(search_query)):
        if sig and set(sig) <= t_cand:
            return True
    need_toks = set(_identity_sig_tokens(need_name)) | set(_identity_sig_tokens(search_query))
    if len(need_toks & t_cand) >= 2:
        return True
    return False


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
    async with proj_db.execute("SELECT gen_label, asset_ref, svg_path, status, file_path, source, license, source_url FROM generations WHERE id=? AND project_id=?",
                               (gen_id, project_id)) as cur:
        row = await cur.fetchone()
    await proj_db.close()
    if not row:
        raise HTTPException(404, "Generation not found")
    row = dict(row)
    clean = _sanitize_svg_base(row["gen_label"] or row["asset_ref"] or f"gen{gen_id}")
    vers = _list_svg_versions(svg_dir, clean)
    # SCENES-MP4 S-T04: version history covers BOTH lanes (AI/paste/upload SVG
    # versions + fetch/raster-upload user files). Replaced rows keep every
    # file on disk — this endpoint lists them (additive keys; existing
    # callers keep reading versions/current_svg_path/status untouched).
    fetch_dir = base / _FETCH_SUBDIR
    return {"gen_id": gen_id, "current_svg_path": row["svg_path"], "status": row["status"],
            "versions": [f"06_sheets/svg/{clean}_v{v}.svg" for v in vers],
            "fetch_versions": _list_fetch_versions(fetch_dir, clean),
            "current_file_path": row.get("file_path") or "",
            "source": row.get("source") or "",
            "license": row.get("license") or "",
            "source_url": row.get("source_url") or ""}


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


# --- SCENES-MP4 I-T03: local recolor (fill-swap, zero AI) ---
# POST .../generate/svg/{gen_id}/recolor {mapping}: parse the current SVG
# text's fills, map old->new, write a new versioned _vN.svg, move the newest
# pointer (history intact — same semantics as improve/paste). Approved/final
# rows demote to generated (needs re-approve, same as improve). Only
# svg_path + status move (file_path/source untouched — improve semantics, so
# the old raster stays until re-approve refreshes it). No AI calls here (no
# LLM jobs, no recipes, no schemas needed — §4 rule 4 applies to AI outputs;
# this lane transforms user-approved bytes only).
# GET .../generate/svg/{gen_id}/fills: read-only distinct-fill list for the
# Assets page swatches (no writes). Both endpoints are additive (no table
# changes, no renames).

_CSS_NAMED_COLORS = frozenset("""
aliceblue antiquewhite aqua aquamarine azure beige bisque black
blanchedalmond blue blueviolet brown burlywood cadetblue chartreuse
chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan
darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta
darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
darkslateblue darkslategray darkslategrey darkturquoise darkviolet
deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite
forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray green
greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender
lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon
lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue
lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue
mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen
mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
navajowhite navy oldlace olive olivedrab orange orangered orchid
palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff
peru pink plum powderblue purple rebeccapurple red rosybrown royalblue
saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue
slateblue slategray slategrey snow springgreen steelblue tan teal thistle
tomato turquoise violet wheat white whitesmoke yellow yellowgreen
""".split())

_SVG_FILL_KEYWORDS = frozenset({"none", "transparent", "currentcolor"})

_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

_FILL_ATTR_RE = re.compile(r"(fill\s*=\s*[\"'])([^\"']+)([\"'])", flags=re.IGNORECASE)

_STYLE_ATTR_RE = re.compile(r"(style\s*=\s*)([\"'])(.*?)\2", flags=re.IGNORECASE | re.DOTALL)

_STYLE_FILL_DECL_RE = re.compile(
    r"(?<![-\w])fill(?![-\w])(\s*:\s*)([^;\"'}]+?)(\s*(?:;|$))",
    flags=re.IGNORECASE)


def _is_valid_css_color(s: str) -> bool:
    """Layman-wheel guard: hex #RGB/#RRGGBB/#RRGGBBAA, SVG keywords, or a CSS
    named color (case-insensitive). Anything else (empty, URLs, functions,
    markup) is an invalid color -> 400, nothing written."""
    t = (s or "").strip()
    if not t:
        return False
    low = t.lower()
    if low in _SVG_FILL_KEYWORDS:
        return True
    if _HEX_COLOR_RE.match(t):
        return True
    if low in _CSS_NAMED_COLORS:
        return True
    return False


def _extract_svg_fills(svg_text: str) -> list[str]:
    """Distinct fill values in first-seen order (exact strings, no norm).

    Covers fill="..." attributes + fill:... declarations inside style="..."
    attributes (the shapes AI SVG actually emits). <style>-block classes are
    out of scope for v1 (honest no-match -> 400, never a silent half-swap)."""
    seen: list[str] = []
    for m in _FILL_ATTR_RE.finditer(svg_text or ""):
        v = (m.group(2) or "").strip()
        if not v:
            continue
        # Keep exact strings (case-sensitive distinct): #FF0000 vs #ff0000
        # are different bytes the round-trip must preserve — list both.
        if v not in seen:
            seen.append(v)
    for m in _STYLE_ATTR_RE.finditer(svg_text or ""):
        inner = m.group(3) or ""
        for d in _STYLE_FILL_DECL_RE.finditer(inner):
            v = (d.group(2) or "").strip()
            if v and v not in seen:
                seen.append(v)
    return seen


def _apply_fill_mapping(svg_text: str, norm: dict[str, str]) -> tuple[str, int]:
    """Single-pass fill swap (no cascading): every fill whose stripped-lower
    form sits in norm is replaced with norm[lower] verbatim; everything else
    (spacing, quotes, semicolons, non-fill attrs) is preserved byte-for-byte
    so red->blue->red round-trips exactly. Returns (new_text, swapped)."""

    swapped = 0

    def _attr_repl(m):
        nonlocal swapped
        prefix, val, quote = m.group(1), m.group(2), m.group(3)
        key = (val or "").strip().lower()
        if key in norm:
            swapped += 1
            return f"{prefix}{norm[key]}{quote}"
        return m.group(0)

    out = _FILL_ATTR_RE.sub(_attr_repl, svg_text)

    def _style_repl(m):
        nonlocal swapped
        head, quote, inner = m.group(1), m.group(2), m.group(3)

        def _decl_repl(d):
            nonlocal swapped
            colon, val, tail = d.group(1), d.group(2), d.group(3)
            key = (val or "").strip().lower()
            if key in norm:
                swapped += 1
                return f"fill{colon}{norm[key]}{tail}"
            return d.group(0)

        new_inner = _STYLE_FILL_DECL_RE.sub(_decl_repl, inner)
        return f"{head}{quote}{new_inner}{quote}"

    out = _STYLE_ATTR_RE.sub(_style_repl, out)
    return out, swapped


class SvgRecolorRequest(BaseModel):
    mapping: dict[str, str]


async def _recolor_svg_row(project_id, folder, ch_id, gen_id, mapping: dict):
    """Fill-swap transform on the current SVG text (I-T03).

    Validates every old/new color (invalid -> 400, nothing written), requires
    at least one real change, requires the current SVG to exist, swaps fills
    (fill= attrs + style= fill: decls, single-pass), re-validates through the
    real validate_svg_text path, writes versioned _vN.svg + pointer move
    (history intact), demotes to generated. Revert endpoint untouched.
    """
    if not isinstance(mapping, dict) or len(mapping) == 0:
        raise HTTPException(400, "mapping must be a non-empty object {old_color: new_color} (nothing written).")
    if len(mapping) > 20:
        raise HTTPException(400, "mapping holds at most 20 entries (nothing written).")
    norm: dict[str, str] = {}
    for raw_old, raw_new in mapping.items():
        old = (raw_old or "").strip() if isinstance(raw_old, str) else ""
        new = (raw_new or "").strip() if isinstance(raw_new, str) else ""
        if not old or not new:
            raise HTTPException(400, "mapping keys and values must be non-empty color strings (nothing written).")
        if not _is_valid_css_color(old):
            raise HTTPException(400, f"invalid color '{old[:60]}' (nothing written).")
        if not _is_valid_css_color(new):
            raise HTTPException(400, f"invalid color '{new[:60]}' (nothing written).")
        low = old.lower()
        if low in norm:
            raise HTTPException(400, f"duplicate mapping for '{old[:60]}' (nothing written).")
        if low == new.lower():
            continue  # no-op entry (same color) — skip, never mint identical versions
        norm[low] = new  # new stored verbatim (wheel hex preserved exactly)
    if not norm:
        raise HTTPException(400, "mapping changes nothing (old and new are the same color).")
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
        raise HTTPException(400, "No SVG version yet — generate once before recoloring.")
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
        raise HTTPException(400, "Previous SVG is empty — cannot recolor.")
    new_svg, swapped = _apply_fill_mapping(previous_svg, norm)
    if swapped == 0:
        have = _extract_svg_fills(previous_svg)
        await proj_db.close()
        raise HTTPException(
            400, f"no matching fills (have [{', '.join(have[:12])}]{'…' if len(have) > 12 else ''} — nothing written).")
    try:
        clean_svg = validate_svg_text(new_svg)
    except ValueError as e:
        await proj_db.close()
        raise HTTPException(400, f"{str(e)[:280]} (nothing written).")
    label = row["gen_label"] or row["asset_ref"] or f"gen{gen_id}"
    clean = _sanitize_svg_base(label)
    previous = row.get("svg_path") or ""
    try:
        ver = _next_svg_version(svg_dir, clean)
        rel = f"06_sheets/svg/{clean}_v{ver}.svg"
        (svg_dir / f"{clean}_v{ver}.svg").write_text(clean_svg, encoding="utf-8")
    except Exception as e:
        await proj_db.close()
        raise HTTPException(500, f"write failed: {type(e).__name__}: {str(e)[:200]}")
    await proj_db.execute(
        "UPDATE generations SET svg_path=?, status='generated', error='', updated_at=? WHERE id=?",
        (rel, _now(), gen_id))
    await proj_db.commit()
    await proj_db.close()
    return {"gen_id": gen_id, "status": "generated", "svg_path": rel,
            "version": ver, "previous_svg_path": previous or None,
            "swapped": swapped, "mapping": mapping}


@router.post("/projects/{project_id}/generate/svg/{gen_id}/recolor")
async def recolor_svg_one(project_id: str, gen_id: int, data: SvgRecolorRequest):
    folder, ch_id = await _proj(project_id)
    return await _recolor_svg_row(project_id, folder, ch_id, gen_id, data.mapping)


@router.get("/projects/{project_id}/generate/svg/{gen_id}/fills")
async def list_svg_fills(project_id: str, gen_id: int):
    """Distinct fills in the current SVG (read-only swatch source, no writes)."""
    folder, ch_id = await _proj(project_id)
    base = get_project_dir(ch_id, folder.split("_")[1])
    proj_db = await get_project_db(folder)
    try:
        async with proj_db.execute(
                "SELECT gen_label, asset_ref, svg_path, status FROM generations WHERE id=? AND project_id=?",
                (gen_id, project_id)) as cur:
            row = await cur.fetchone()
    finally:
        await proj_db.close()
    if not row:
        raise HTTPException(404, "Generation not found")
    row = dict(row)
    if not row.get("svg_path"):
        raise HTTPException(400, "No SVG version yet — generate once before listing fills.")
    svg_file = base / row["svg_path"]
    if not svg_file.exists():
        raise HTTPException(400, f"SVG file missing on disk: {row['svg_path']}")
    try:
        text = svg_file.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(400, f"Cannot read SVG: {type(e).__name__}")
    if not text.strip():
        raise HTTPException(400, "SVG is empty.")
    fills = _extract_svg_fills(text)
    return {"gen_id": gen_id, "svg_path": row["svg_path"], "status": row.get("status") or "",
            "fills": fills, "count": len(fills)}


# --- SCENES-MP4 S-T04: per-asset web-fetch + image upload (backend) ---
# Every asset already has regen/retry (P2-T04) + paste-code (D2-T02). This
# block adds the two NEW lanes, both per-generation (per asset):
#   fetch-through-web: GET .../fetch-search?q= (Wikimedia Commons search with
#     the download_desk license filter — ALLOWED/BLOCKED, same shape as the
#     World Desk autosearch) → user picks → POST .../fetch {file_url,
#     source_url, license, author} downloads the file, stores it versioned
#     under 06_sheets/fetch/<base>_vN.<ext>, points file_path at it (so the
#     scene preview + image endpoint show the real file immediately), and
#     records license + source_url on the row (source='fetched').
#   upload image: POST .../upload (multipart) accepts .svg/.png/.jpg/.jpeg
#     (an asset is not necessarily vector). SVG uploads validate through the
#     real validate_svg_text path and version like paste; raster uploads PIL-
#     validate and version under 06_sheets/fetch/ like fetch. Both move the
#     newest pointer only (history intact — old files never deleted, versions
#     endpoint lists both lanes). Manual always wins: source flips to
#     'fetched'/'uploaded', and approve keeps a fetch/ user file instead of
#     re-rastering stale AI SVG over it (see _approve_svg_row guard).
# No AI calls here (no LLM jobs, no recipes, no schemas needed — §4 rule 4
# applies to AI outputs; these lanes move user/chosen files only).

_FETCH_SUBDIR = "06_sheets/fetch"

_FETCH_CT_EXT = (
    ("image/png", ".png"),
    ("image/jpeg", ".jpg"),
    ("image/webp", ".webp"),
)

_UPLOAD_SVG_EXTS = frozenset({".svg"})
_UPLOAD_RASTER_EXTS = frozenset({".png", ".jpg", ".jpeg"})
_UPLOAD_MAX_BYTES = 15 * 1024 * 1024


def _next_fetch_version(fetch_dir, base: str) -> int:
    """Next user-file version: max over <base>_vN.<any-ext> + 1 (never reuse)."""
    pat = re.compile(rf"^{re.escape(base)}_v(\d+)\.[A-Za-z0-9]+$")
    best = 0
    try:
        for p in fetch_dir.iterdir():
            m = pat.match(p.name)
            if m:
                try:
                    best = max(best, int(m.group(1)))
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return best + 1


def _list_fetch_versions(fetch_dir, base: str) -> list[str]:
    """Versioned user files (fetch + raster uploads), oldest first."""
    pat = re.compile(rf"^{re.escape(base)}_v(\d+)\.[A-Za-z0-9]+$")
    hits: list[tuple[int, str]] = []
    try:
        for p in fetch_dir.iterdir():
            m = pat.match(p.name)
            if m:
                try:
                    hits.append((int(m.group(1)), p.name))
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    hits.sort()
    return [f"{_FETCH_SUBDIR}/{name}" for _, name in hits]


def _fetch_ext_for_content_type(ct: str, url: str) -> str | None:
    """Map a download's content-type to a stored extension (None = reject)."""
    c = (ct or "").split(";")[0].strip().lower()
    for prefix, ext in _FETCH_CT_EXT:
        if c == prefix or c.startswith(prefix + "+"):
            return ext
    # Fallback: URL suffix when the server sends a generic content-type.
    low = (url or "").split("?")[0].lower()
    if low.endswith(".png"):
        return ".png"
    if low.endswith(".jpg") or low.endswith(".jpeg"):
        return ".jpg"
    if low.endswith(".webp"):
        return ".webp"
    return None


def _validate_raster_bytes(raw: bytes) -> tuple[int, int, str]:
    """PIL-validate uploaded/fetched raster bytes. Returns (w, h, format)."""
    import io as _io

    from PIL import Image as _Image

    try:
        with _Image.open(_io.BytesIO(raw)) as im:
            im.load()
            return int(im.size[0]), int(im.size[1]), (im.format or "?")
    except Exception as e:
        raise ValueError(f"file is not a valid PNG/JPG image: {type(e).__name__}")


class SvgFetchRequest(BaseModel):
    file_url: str
    source_url: str = ""
    license: str = ""
    author: str = ""


@router.get("/projects/{project_id}/generate/svg/{gen_id}/fetch-search")
async def fetch_search_svg(project_id: str, gen_id: int, q: str | None = None):
    """Wikimedia Commons search for one asset (pick step of fetch-through-web).

    Default query is the linked scene need's search_query (the same text the
    asset planner wrote), else the generation title. Results carry the file
    URL + license + author the attach step records. Read-only: no writes.
    """
    import asyncio as _asyncio

    folder, _ch_id = await _proj(project_id)
    proj_db = await get_project_db(folder)
    try:
        async with proj_db.execute(
                "SELECT * FROM generations WHERE id=? AND project_id=?",
                (gen_id, project_id)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Generation not found")
        row = dict(row)
        if row["kind"] != "svg":
            raise HTTPException(400, "Only kind='svg' rows use the SVG pipeline.")
        query = (q or "").strip()
        if not query:
            try:
                async with proj_db.execute(
                        "SELECT search_query, name FROM scene_assets WHERE generation_id=?",
                        (gen_id,)) as cur:
                    need = await cur.fetchone()
                if need:
                    need = dict(need)
                    query = ((need.get("search_query") or need.get("name")) or "").strip()
            except Exception:
                pass
            if not query:
                query = (row["title"] or "").strip()
        if not query:
            raise HTTPException(400, "q must be non-empty (no search text for this asset).")
    finally:
        await proj_db.close()
    # Same license discipline as the World Desk autosearch (download_desk):
    # only freely reusable files, NC/ND blocked — one rule, two callers.
    from backend.api.download_desk import _clean_html, _license_ok

    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
           f"&gsrsearch=filetype:bitmap%20{query.replace(' ', '%20')}&gsrlimit=10&gsrnamespace=6"
           "&prop=imageinfo&iiprop=url%7Cextmetadata%7Csize&iiurlwidth=320")
    headers = {"User-Agent": "PixelPlatformer/1.0 (animation pipeline; localhost)"}
    r = None
    for attempt in range(3):
        async with httpx.AsyncClient(timeout=30) as cl:
            r = await cl.get(url, headers=headers)
        if r.status_code == 200:
            break
        if r.status_code not in (403, 429, 500, 502, 503, 504):
            break
        if attempt < 2:
            await _asyncio.sleep(1.0 * (attempt + 1))
    if r is None or r.status_code != 200:
        raise HTTPException(
            502, f"Wikimedia search failed HTTP {getattr(r, 'status_code', 'no response')} "
                 f"for query '{query[:80]}' (transient 403/429s are their rate-limit — retry shortly).")
    try:
        pages = (r.json().get("query") or {}).get("pages") or {}
    except Exception:
        raise HTTPException(502, "Wikimedia returned an unreadable response (retry shortly).")
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        lic = _clean_html((md.get("LicenseShortName") or {}).get("value"))
        if not _license_ok(lic):
            continue
        out.append({
            "title": p.get("title", ""),
            "thumb": ii.get("thumburl") or ii.get("url"),
            "file_url": ii.get("url"),
            "source_url": ii.get("descriptionurl"),
            "license": lic,
            "author": _clean_html((md.get("Artist") or {}).get("value"))[:120],
        })
    out.sort(key=lambda x: x["title"])
    return {"gen_id": gen_id, "query": query, "results": out[:8]}


@router.post("/projects/{project_id}/generate/svg/{gen_id}/fetch")
async def fetch_attach_svg(project_id: str, gen_id: int, data: SvgFetchRequest):
    """Attach a web file to one asset (attach step of fetch-through-web).

    Downloads file_url, validates it is a real raster image, stores it
    versioned under 06_sheets/fetch/ (never overwrite), points file_path at
    it (preview + image endpoint show the real file immediately), records
    license + source_url, flips source='fetched' (manual always wins).
    Nothing is deleted — replaced rows keep version history on disk.
    """
    file_url = (data.file_url or "").strip()
    if not (file_url.startswith("http://") or file_url.startswith("https://")):
        raise HTTPException(400, "file_url must be an http(s) URL (pick one from fetch-search).")
    folder, ch_id = await _proj(project_id)
    base = get_project_dir(ch_id, folder.split("_")[1])
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM generations WHERE id=? AND project_id=?",
                               (gen_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close()
        raise HTTPException(404, "Generation not found")
    row = dict(row)
    if row["kind"] != "svg":
        await proj_db.close()
        raise HTTPException(400, "Only kind='svg' rows use the SVG pipeline.")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as cl:
        r = await cl.get(file_url)
    if r.status_code != 200 or not r.content:
        await proj_db.close()
        raise HTTPException(502, f"Download failed HTTP {r.status_code} (nothing written).")
    raw = bytes(r.content)
    if len(raw) > _UPLOAD_MAX_BYTES:
        await proj_db.close()
        raise HTTPException(400, f"File too large ({len(raw)}B > 15MB — nothing written).")
    ext = _fetch_ext_for_content_type(r.headers.get("content-type", ""), file_url)
    if ext is None:
        await proj_db.close()
        raise HTTPException(
            400, f"Unsupported file type ({r.headers.get('content-type', '?') or '?'} — "
                 "fetch accepts PNG/JPG/WEBP bitmaps; SVG arrives via upload/paste).")
    try:
        _w, _h, _fmt = _validate_raster_bytes(raw)
    except ValueError as e:
        await proj_db.close()
        raise HTTPException(400, f"{e} (nothing written).")
    label = row["gen_label"] or row["asset_ref"] or f"gen{gen_id}"
    clean = _sanitize_svg_base(label)
    fetch_dir = base / _FETCH_SUBDIR
    fetch_dir.mkdir(parents=True, exist_ok=True)
    previous = row.get("file_path") or ""
    try:
        ver = _next_fetch_version(fetch_dir, clean)
        rel = f"{_FETCH_SUBDIR}/{clean}_v{ver}{ext}"
        (fetch_dir / f"{clean}_v{ver}{ext}").write_bytes(raw)
    except Exception as e:
        await proj_db.close()
        raise HTTPException(500, f"write failed: {type(e).__name__}: {str(e)[:200]}")
    await proj_db.execute(
        "UPDATE generations SET file_path=?, status='generated', source='fetched', "
        "license=?, source_url=?, error='', updated_at=? WHERE id=?",
        (rel, (data.license or "")[:200], (data.source_url or "")[:500], _now(), gen_id))
    await proj_db.commit()
    await proj_db.close()
    return {"gen_id": gen_id, "status": "generated", "file_path": rel,
            "version": ver, "source": "fetched",
            "license": (data.license or "")[:200],
            "source_url": (data.source_url or "")[:500],
            "previous_file_path": previous or None}


@router.post("/projects/{project_id}/generate/svg/{gen_id}/upload")
async def upload_svg_asset(project_id: str, gen_id: int, file: UploadFile = File(...)):
    """Upload an image for one asset (user file wins, history kept).

    Accepts .svg (validated through the real validate_svg_text path, versioned
    like paste → svg_path pointer) and .png/.jpg/.jpeg (PIL-validated,
    versioned under 06_sheets/fetch/ → file_path pointer so the preview shows
    it immediately). New version each upload, never overwrite; source flips to
    'uploaded'. Rejects anything else with a 400 and writes nothing.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Upload is empty (nothing written).")
    if len(raw) > _UPLOAD_MAX_BYTES:
        raise HTTPException(413, f"File too large ({len(raw)}B > 15MB — nothing written).")
    fname = (file.filename or "").lower()
    ext = None
    for cand in (".svg", ".png", ".jpg", ".jpeg"):
        if fname.endswith(cand):
            ext = cand
            break
    if ext is None:
        # Fallback: sniff the bytes (SVG text vs raster magic) when the
        # filename lies or is missing — same accept set either way.
        head = raw[:512].lstrip().lower()
        if head.startswith(b"<svg") or head.startswith(b"<?xml"):
            ext = ".svg"
        else:
            try:
                _validate_raster_bytes(raw)
                ext = ".png"
            except ValueError:
                ext = None
    if ext is None:
        raise HTTPException(400, "Upload accepts .svg/.png/.jpg/.jpeg only (nothing written).")
    folder, ch_id = await _proj(project_id)
    base = get_project_dir(ch_id, folder.split("_")[1])
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM generations WHERE id=? AND project_id=?",
                               (gen_id, project_id)) as cur:
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
    if ext in _UPLOAD_SVG_EXTS:
        try:
            clean_svg = validate_svg_text(raw.decode("utf-8", errors="strict"))
        except (ValueError, UnicodeDecodeError) as e:
            await proj_db.close()
            raise HTTPException(400, f"{str(e)[:280]} (nothing written).")
        svg_dir = base / "06_sheets" / "svg"
        svg_dir.mkdir(parents=True, exist_ok=True)
        previous = row.get("svg_path") or ""
        previous_file = row.get("file_path") or ""
        # Latest manual action wins: the new SVG supersedes an older
        # fetched/uploaded raster, so drop the fetch/ pointer (history file
        # stays on disk) — otherwise the approve guard below would keep
        # showing the stale user raster forever. AI raster caches
        # (06_sheets/raster/...) are kept: approve refreshes them from the
        # new SVG (same semantics as paste).
        drop_user_file = previous_file.startswith(_FETCH_SUBDIR + "/")
        try:
            ver = _next_svg_version(svg_dir, clean)
            rel = f"06_sheets/svg/{clean}_v{ver}.svg"
            (svg_dir / f"{clean}_v{ver}.svg").write_text(clean_svg, encoding="utf-8")
        except Exception as e:
            await proj_db.close()
            raise HTTPException(500, f"write failed: {type(e).__name__}: {str(e)[:200]}")
        await proj_db.execute(
            "UPDATE generations SET svg_path=?, file_path=?, status='generated', source='uploaded', "
            "error='', updated_at=? WHERE id=?",
            (rel, ("" if drop_user_file else previous_file), _now(), gen_id))
        await proj_db.commit()
        await proj_db.close()
        return {"gen_id": gen_id, "status": "generated", "svg_path": rel,
                "version": ver, "source": "uploaded",
                "file_path": ("" if drop_user_file else previous_file),
                "previous_svg_path": previous or None,
                "previous_file_path": previous_file or None}
    try:
        _validate_raster_bytes(raw)
    except ValueError as e:
        await proj_db.close()
        raise HTTPException(400, f"{e} (nothing written).")
    store_ext = ".jpg" if ext == ".jpeg" else ext
    fetch_dir = base / _FETCH_SUBDIR
    fetch_dir.mkdir(parents=True, exist_ok=True)
    previous = row.get("file_path") or ""
    try:
        ver = _next_fetch_version(fetch_dir, clean)
        rel = f"{_FETCH_SUBDIR}/{clean}_v{ver}{store_ext}"
        (fetch_dir / f"{clean}_v{ver}{store_ext}").write_bytes(raw)
    except Exception as e:
        await proj_db.close()
        raise HTTPException(500, f"write failed: {type(e).__name__}: {str(e)[:200]}")
    await proj_db.execute(
        "UPDATE generations SET file_path=?, status='generated', source='uploaded', "
        "error='', updated_at=? WHERE id=?",
        (rel, _now(), gen_id))
    await proj_db.commit()
    await proj_db.close()
    return {"gen_id": gen_id, "status": "generated", "file_path": rel,
            "version": ver, "source": "uploaded",
            "previous_file_path": previous or None}


# --- SCENES-MP4 P2-T06: approve -> raster PNG (hash-keyed cache) + finalize ---
# Status ladder: generated -> approved -> final. Approve rasterizes the current
# svg_path into 06_sheets/raster/<base>_<hash12>.png via Inkscape headless;
# identical SVG bytes = cache hit (no re-raster). file_path holds the PNG so
# the existing GET .../generations/{gen_id}/image endpoint serves the render.
# Approval UI shows that PNG, never the SVG source.

_RASTER_W, _RASTER_H = 1920, 1080


def _fit_export_size(svg_bytes: bytes) -> tuple[int, int]:
    """Aspect-fit export dims inside (_RASTER_W, _RASTER_H).

    The old code forced -w 1920 -h 1080 on every SVG, which baked a
    non-uniform squash into any non-16:9 art (3:4 characters looked
    flattened, square icons stretched). Fit instead: parse the SVG's own
    width/height (else viewBox), scale to fit, never exceed the cap.
    Falls back to the full cap when unparseable.
    """
    w = h = 0.0
    try:
        head = svg_bytes[:4000].decode("utf-8", "ignore")
        m = re.search(r"<svg[^>]*\bwidth\s*=\s*[\"']([\d.]+)", head, re.IGNORECASE)
        m2 = re.search(r"<svg[^>]*\bheight\s*=\s*[\"']([\d.]+)", head, re.IGNORECASE)
        if m and m2:
            w, h = float(m.group(1)), float(m2.group(1))
        else:
            m3 = re.search(
                r"<svg[^>]*\bviewBox\s*=\s*[\"']([\d.\-]+)[\s,]+([\d.\-]+)[\s,]+([\d.\-]+)[\s,]+([\d.\-]+)[\"']",
                head, re.IGNORECASE)
            if m3:
                w, h = float(m3.group(3)), float(m3.group(4))
    except Exception:
        w = h = 0.0
    if w <= 0 or h <= 0:
        return _RASTER_W, _RASTER_H
    scale = min(_RASTER_W / w, _RASTER_H / h)
    return max(1, int(round(w * scale))), max(1, int(round(h * scale)))


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
    # SCENES-MP4 S-T04: manual always wins — a fetched/uploaded raster under
    # 06_sheets/fetch/ IS the render (no SVG to rasterize). Approving keeps
    # the user file exactly as-is (status flip only, never re-raster stale AI
    # bytes over it). Uploaded SVGs (source='uploaded' + svg_path) fall
    # through to the normal raster path below.
    _user_fp = (row.get("file_path") or "").strip()
    if row.get("source") in ("fetched", "uploaded") and _user_fp.startswith(_FETCH_SUBDIR + "/"):
        _cand0 = base / _user_fp
        if _cand0.exists() and _cand0.stat().st_size > 0:
            target = "final" if row["status"] == "final" else "approved"
            await proj_db.execute(
                "UPDATE generations SET status=?, error='', updated_at=? WHERE id=?",
                (target, _now(), gen_id))
            await proj_db.commit()
            await proj_db.close()
            return {"gen_id": gen_id, "status": target, "svg_path": row["svg_path"],
                    "file_path": _user_fp, "cached": True, "user_file": True,
                    "raster_path": _user_fp}
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
    ew, eh = _fit_export_size(svg_bytes)
    cmd = [inkscape, str(svg_file), "--export-type=png",
           f"--export-filename={dest}", "-w", str(ew), "-h", str(eh)]
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
    ew, eh = _fit_export_size(clean_svg.encode("utf-8"))
    cmd = [inkscape, svg_tmp, "--export-type=png",
           f"--export-filename={png_tmp}", "-w", str(ew), "-h", str(eh)]
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
    # SCENES-MP4 S-T04: user files are PNG/JPG/WEBP beside SVG — serve the
    # real media type (was hardcoded image/png for the raster-only era).
    _media = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
              "webp": "image/webp", "svg": "image/svg+xml"}.get(
        p.suffix.lower().lstrip("."), "image/png")
    return FileResponse(p, media_type=_media)
