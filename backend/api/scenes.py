# backend/api/scenes.py
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import DATA_DIR
from backend.core.llm_client import dispatch
from backend.db.connection import get_app_db, get_project_db
from backend.models.scene import AssetPlan, ScenePlan

router = APIRouter(tags=["scenes"])

# Sharding thresholds shared with backend/core/sharding.py::sharded_extract
# (long scripts split at >4000 words / 300 overlap). Per-beat planning is
# inherently sharded (one small dispatch per beat); only the shared
# full-script context below is capped at the same threshold.
_SHARD_THRESHOLD = 4000
_SHARD_OVERLAP = 300

_FALLBACK_DESCRIPTOR = "clean flat 2D animation, bold outlines, limited palette"


class SceneEdit(BaseModel):
    place_asset_ref: Optional[str] = None
    shot: Optional[str] = None
    reasoning: Optional[str] = None
    status: Optional[str] = None


def _now():
    return datetime.now(timezone.utc).isoformat()


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


async def _style_pack(ch_id: str) -> tuple[str, str]:
    from backend.api.channels import DEFAULT_AVOID
    db = await get_app_db()
    async with db.execute("SELECT descriptor, avoid_list FROM channels WHERE id=?", (ch_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    descriptor = (row["descriptor"] if row and row["descriptor"] else _FALLBACK_DESCRIPTOR)
    avoid = (row["avoid_list"] if row and row["avoid_list"] else DEFAULT_AVOID)
    return descriptor, avoid


async def _approved_registry(proj_db, project_id: str) -> list:
    """Reusable-art index: IDs + names only (never file paths or prefixes)."""
    registry = []
    async with proj_db.execute(
        "SELECT id, names FROM characters WHERE project_id=? AND stale=0 ORDER BY id",
        (project_id,)) as cur:
        for r in await cur.fetchall():
            names = json.loads(r["names"] or "[]")
            registry.append({"id": r["id"], "name": names[0] if names else r["id"]})
    async with proj_db.execute(
        "SELECT id, name FROM environments WHERE project_id=? AND stale=0 ORDER BY id",
        (project_id,)) as cur:
        for r in await cur.fetchall():
            registry.append({"id": r["id"], "name": r["name"]})
    async with proj_db.execute(
        "SELECT id, text FROM world_records WHERE project_id=? AND stale=0 ORDER BY id",
        (project_id,)) as cur:
        for r in await cur.fetchall():
            registry.append({"id": r["id"], "name": (r["text"] or "")[:80]})
    return registry


def _cap_script(script: str) -> str:
    words = script.split()
    if len(words) <= _SHARD_THRESHOLD:
        return script
    keep = _SHARD_THRESHOLD - _SHARD_OVERLAP
    return (" ".join(words[:keep])
            + f" ... [truncated {len(words) - keep} words; "
            + f"sharded_extract thresholds { _SHARD_THRESHOLD}/{_SHARD_OVERLAP}]")


@router.post("/projects/{project_id}/scenes/plan")
async def plan_scenes(project_id: str):
    try:
        return await _plan_scenes_inner(project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Scene plan crashed: {type(e).__name__}: {e}")


async def _plan_scenes_inner(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    script = await _get_locked_script(folder, project_id)
    if not script:
        raise HTTPException(400, "Lock a script first (Script Studio -> Lock).")

    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT id, text FROM beats WHERE project_id=? AND stale=0 ORDER BY sort_order",
        (project_id,)) as cur:
        beats = [dict(r) for r in await cur.fetchall()]
    if not beats:
        await proj_db.close()
        raise HTTPException(400, "Extract beats first (no beats to plan).")

    registry = await _approved_registry(proj_db, project_id)
    descriptor, avoid = await _style_pack(ch_id)
    full_script = _cap_script(script)

    planned, skipped_approved, failed = 0, 0, []
    now = _now()
    for i, beat in enumerate(beats):
        async with proj_db.execute("SELECT status FROM scenes WHERE beat_id=?", (beat["id"],)) as cur:
            existing = await cur.fetchone()
        if existing and existing["status"] == "approved":
            skipped_approved += 1
            continue

        context = {
            "beat_text": beat["text"],
            "prev_beat": beats[i - 1]["text"] if i > 0 else "",
            "next_beat": beats[i + 1]["text"] if i + 1 < len(beats) else "",
            "full_script": full_script,
            "approved_sheets": registry,
            "style_descriptor": descriptor,
            "avoid_list": avoid,
        }
        try:
            res = await dispatch("scene_plan", context, schema=ScenePlan,
                                 project_id=project_id, channel_id=ch_id)
        except Exception as e:
            # One beat's crash must not kill the batch (or leak past `failed`).
            failed.append({"beat_id": beat["id"],
                           "error": f"dispatch crashed: {type(e).__name__}: {str(e)[:150]}"})
            continue
        if not res["ok"]:
            failed.append({"beat_id": beat["id"], "error": str(res.get("error"))[:200]})
            continue

        parsed = res["parsed"]
        if existing:
            await proj_db.execute(
                "UPDATE scenes SET place_asset_ref=?, shot=?, reasoning=?, "
                "status='draft', stale=0, updated_at=? WHERE beat_id=?",
                (parsed["place_ref"], parsed["shot"], parsed["reasoning"], now, beat["id"]))
        else:
            await proj_db.execute(
                "INSERT INTO scenes (beat_id, place_asset_ref, shot, reasoning, "
                "status, stale, created_at, updated_at) VALUES (?,?,?,?, 'draft', 0, ?, ?)",
                (beat["id"], parsed["place_ref"], parsed["shot"],
                 parsed["reasoning"], now, now))
            planned += 1

    await proj_db.commit()
    await proj_db.close()
    return {"planned": planned, "skipped_approved": skipped_approved,
            "failed": failed, "total_beats": len(beats)}


@router.put("/projects/{project_id}/scenes/{beat_id}")
async def edit_scene(project_id: str, beat_id: str, data: SceneEdit):
    """Manual row write — always allowed, even on approved rows."""
    if data.status is not None and data.status not in ("draft", "approved"):
        raise HTTPException(422, "status must be 'draft' or 'approved'")
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT id FROM beats WHERE id=? AND project_id=?",
                               (beat_id, project_id)) as cur:
        beat = await cur.fetchone()
    if not beat:
        await proj_db.close()
        raise HTTPException(404, "Beat not found")
    async with proj_db.execute("SELECT * FROM scenes WHERE beat_id=?", (beat_id,)) as cur:
        existing = await cur.fetchone()
    now = _now()
    if existing:
        row = dict(existing)
        await proj_db.execute(
            "UPDATE scenes SET place_asset_ref=?, shot=?, reasoning=?, status=?, updated_at=? "
            "WHERE beat_id=?",
            (data.place_asset_ref if data.place_asset_ref is not None else row["place_asset_ref"],
             data.shot if data.shot is not None else row["shot"],
             data.reasoning if data.reasoning is not None else row["reasoning"],
             data.status if data.status is not None else row["status"],
             now, beat_id))
    else:
        await proj_db.execute(
            "INSERT INTO scenes (beat_id, place_asset_ref, shot, reasoning, "
            "status, stale, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (beat_id, data.place_asset_ref, data.shot or "", data.reasoning or "",
             data.status or "draft", 0, now, now))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "saved"}


@router.get("/projects/{project_id}/scenes")
async def list_scenes(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT s.* FROM scenes s JOIN beats b ON b.id=s.beat_id "
        "WHERE b.project_id=? ORDER BY b.sort_order", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    return rows


# --- SCENES-MP4 P1-T06: asset-plan + library match (misses -> kind='svg' generations) ---

_STOPWORDS = frozenset(
    "a an the of and or in on at to for with from by as is are was were be been "
    "this that these those its it s".split()
)


def _norm(s: str) -> str:
    return re.sub(r"[^\w]+", " ", (s or "").lower(), flags=re.UNICODE).strip()


def _sig_tokens(s: str) -> list[str]:
    return [t for t in _norm(s).split() if t not in _STOPWORDS and len(t) > 1]


def _entry_matches(need_name: str, search_query: str, title: str) -> bool:
    n_name, n_query, n_title = _norm(need_name), _norm(search_query), _norm(title)
    if not n_title or (not n_name and not n_query):
        return False
    if n_name and n_name == n_title:
        return True
    if n_query and n_query == n_title:
        return True
    # Substring either way (min len 4 guards single-letter noise).
    if n_name and len(n_name) >= 4 and (n_name in n_title or n_title in n_name):
        return True
    if n_query and len(n_query) >= 4 and (n_query in n_title or n_title in n_query):
        return True
    t_title = set(n_title.split())
    for sig in (_sig_tokens(need_name), _sig_tokens(search_query)):
        if sig and set(sig) <= t_title:
            return True
    # Fallback: >=2 significant tokens overlap.
    need_toks = set(_sig_tokens(need_name)) | set(_sig_tokens(search_query))
    if len(need_toks & t_title) >= 2:
        return True
    return False


def _match_need(need: dict, lib_entries: list, vault_entries: list):
    for e in lib_entries:
        if _entry_matches(need.get("name") or "", need.get("search_query") or "",
                           e.get("title") or ""):
            return "library", e
    for e in vault_entries:
        if _entry_matches(need.get("name") or "", need.get("search_query") or "",
                           e.get("title") or ""):
            return "vault", e
    return None, None


async def _next_library_id(proj_db) -> str:
    async with proj_db.execute("SELECT id FROM library WHERE id LIKE 'LIB%'") as cur:
        ids = [r["id"] for r in await cur.fetchall()]
    nums = [int(x[3:]) for x in ids if x[3:].isdigit()]
    return f"LIB{(max(nums) + 1) if nums else 1:02d}"


def _map_need_kind_to_library(kind: str) -> str:
    k = (kind or "").lower()
    if k == "character":
        return "character"
    if k == "place":
        return "environment"
    return "world"


@router.post("/projects/{project_id}/scenes/assets/plan")
async def plan_scene_assets(project_id: str):
    try:
        return await _plan_assets_inner(project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Asset plan crashed: {type(e).__name__}: {e}")


async def _plan_assets_inner(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT b.id AS beat_id, b.text AS beat_text, s.place_asset_ref, s.shot, s.reasoning "
        "FROM scenes s JOIN beats b ON b.id=s.beat_id "
        "WHERE b.project_id=? ORDER BY b.sort_order", (project_id,)) as cur:
        scenes = [dict(r) for r in await cur.fetchall()]
    if not scenes:
        await proj_db.close()
        raise HTTPException(400, "Plan scenes first (no scene rows to plan assets for).")

    async with proj_db.execute(
        "SELECT id, kind, title FROM library WHERE project_id=? AND status='ready' ORDER BY id",
        (project_id,)) as cur:
        lib_entries = [dict(r) for r in await cur.fetchall()]

    app_db = await get_app_db()
    async with app_db.execute(
        "SELECT id, kind, title, file_path FROM channel_library WHERE channel_id=? ORDER BY title",
        (ch_id,)) as cur:
        vault_entries = [dict(r) for r in await cur.fetchall()]
    await app_db.close()

    # Library index for the LLM: IDs + tags only, never file paths / export prefixes.
    library_index = (
        [{"id": e["id"], "tags": e["title"]} for e in lib_entries]
        + [{"id": f"vault:{e['id']}", "tags": e["title"]} for e in vault_entries]
    )

    planned_scenes, total_needs, matched, to_generate = 0, 0, 0, 0
    failed: list[dict] = []
    now = _now()
    for sc in scenes:
        beat_id = sc["beat_id"]
        context = {
            "scene": {"place_ref": sc["place_asset_ref"], "shot": sc["shot"],
                       "reasoning": sc["reasoning"]},
            "beat_text": sc["beat_text"],
            "library_index": library_index,
        }
        try:
            res = await dispatch("asset_plan", context, schema=AssetPlan,
                                 project_id=project_id, channel_id=ch_id)
        except Exception as e:
            # One scene's crash must not kill the batch (mirrors T05 per-beat guard).
            failed.append({"beat_id": beat_id,
                           "error": f"dispatch crashed: {type(e).__name__}: {str(e)[:150]}"})
            continue
        if not res["ok"]:
            failed.append({"beat_id": beat_id, "error": str(res.get("error"))[:200]})
            continue

        needs = (res["parsed"] or {}).get("needs") or []
        try:
            # Re-plan is replace (delete old needs + old pending svg gens for this
            # beat first) so re-runs never duplicate; only on success, so a failed
            # beat keeps its previous needs instead of losing them.
            await proj_db.execute(
                "DELETE FROM generations WHERE project_id=? AND beat_id=? "
                "AND kind='svg' AND status='pending'", (project_id, beat_id))
            await proj_db.execute("DELETE FROM scene_assets WHERE beat_id=?", (beat_id,))
            for idx, need in enumerate(needs, start=1):
                src, entry = _match_need(need, lib_entries, vault_entries)
                if src == "library":
                    await proj_db.execute(
                        "INSERT INTO scene_assets (beat_id, name, kind, search_query, reasoning, "
                        "library_ref, needs_generate, generation_id, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,NULL,?,?)",
                        (beat_id, need["name"], need["kind"], need["search_query"],
                         need["reasoning"], entry["id"], 0, now, now))
                    matched += 1
                elif src == "vault":
                    lib_id = await _materialise_vault_hit(
                        proj_db, project_id, folder, ch_id, entry, now)
                    if lib_id is not None:
                        await proj_db.execute(
                            "INSERT INTO scene_assets (beat_id, name, kind, search_query, reasoning, "
                            "library_ref, needs_generate, generation_id, created_at, updated_at) "
                            "VALUES (?,?,?,?,?,?,?,NULL,?,?)",
                            (beat_id, need["name"], need["kind"], need["search_query"],
                             need["reasoning"], lib_id, 0, now, now))
                        matched += 1
                        # Later beats in this run can reuse the new library row.
                        lib_entries.append({"id": lib_id, "kind": entry.get("kind") or "world",
                                            "title": entry.get("title") or need["name"]})
                    else:
                        gen_id = await _insert_svg_miss(
                            proj_db, project_id, beat_id, sc, need, idx, now)
                        await proj_db.execute(
                            "INSERT INTO scene_assets (beat_id, name, kind, search_query, reasoning, "
                            "library_ref, needs_generate, generation_id, created_at, updated_at) "
                            "VALUES (?,?,?,?,?,NULL,1,?,?,?)",
                            (beat_id, need["name"], need["kind"], need["search_query"],
                             need["reasoning"], gen_id, now, now))
                        to_generate += 1
                else:
                    gen_id = await _insert_svg_miss(
                        proj_db, project_id, beat_id, sc, need, idx, now)
                    await proj_db.execute(
                        "INSERT INTO scene_assets (beat_id, name, kind, search_query, reasoning, "
                        "library_ref, needs_generate, generation_id, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,NULL,1,?,?,?)",
                        (beat_id, need["name"], need["kind"], need["search_query"],
                         need["reasoning"], gen_id, now, now))
                    to_generate += 1
            total_needs += len(needs)
            planned_scenes += 1
        except Exception as e:
            failed.append({"beat_id": beat_id,
                           "error": f"match/store crashed: {type(e).__name__}: {str(e)[:150]}"})
            continue

    await proj_db.commit()
    await proj_db.close()
    return {"planned_scenes": planned_scenes, "total_needs": total_needs,
            "matched": matched, "to_generate": to_generate,
            "failed": failed, "total_scenes": len(scenes)}


async def _materialise_vault_hit(proj_db, project_id: str, folder: str,
                                 ch_id: str, vault_entry: dict, now: str):
    """Copy a vault hit into the project library (source='channel') so every
    match resolves to a single library_ref. Returns the library id, or None
    when the vault file is missing on disk (caller falls back to svg miss)."""
    title = vault_entry.get("title") or ""
    async with proj_db.execute(
        "SELECT id FROM library WHERE project_id=? AND LOWER(title)=LOWER(?) AND status='ready'",
        (project_id, title)) as cur:
        row = await cur.fetchone()
    if row:
        return row["id"]
    src = Path(DATA_DIR) / (vault_entry.get("file_path") or "")
    if not vault_entry.get("file_path") or not src.exists():
        return None
    lib_id = await _next_library_id(proj_db)
    dest_dir = Path(DATA_DIR) / "projects" / folder / "06_assets" / "library"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{lib_id}_vault{src.suffix or '.png'}"
    dest.write_bytes(src.read_bytes())
    rel = f"06_assets/library/{dest.name}"
    vkind = (vault_entry.get("kind") or "").lower()
    kind = vkind if vkind in ("character", "environment", "world") else "world"
    await proj_db.execute(
        "INSERT INTO library (id, project_id, kind, asset_ref, title, file_path, source, "
        "status, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'ready','',?,?)",
        (lib_id, project_id, kind, "", title, rel, "channel", now, now))
    return lib_id


async def _insert_svg_miss(proj_db, project_id: str, beat_id: str,
                           scene: dict, need: dict, idx: int, now: str) -> int:
    gen_label = f"SVG-{beat_id}-{idx:02d}"
    prompt = (
        f"{need['name']} ({need['kind']}) — {need['search_query']}. "
        f"Scene: {scene.get('shot') or ''} Place: {scene.get('place_asset_ref') or 'none'}. "
        f"Why: {need['reasoning']}"
    )
    cur = await proj_db.execute(
        "INSERT INTO generations (project_id, gen_label, kind, asset_ref, beat_id, title, "
        "prompt, file_path, status, error, created_at, updated_at) "
        "VALUES (?,?,'svg',?,?,?,?,?,'pending','',?,?)",
        (project_id, gen_label, gen_label, beat_id, need["name"], prompt, "", now, now))
    return cur.lastrowid


@router.get("/projects/{project_id}/scenes/assets")
async def list_scene_assets(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT sa.* FROM scene_assets sa JOIN beats b ON b.id=sa.beat_id "
        "WHERE b.project_id=? ORDER BY b.sort_order, sa.id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    return rows
