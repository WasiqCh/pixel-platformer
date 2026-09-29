# backend/api/scenes.py
from datetime import datetime, timezone
import hashlib
import json
import os
import random
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core.config import DATA_DIR
from backend.core.llm_client import dispatch
from backend.db.connection import get_app_db, get_project_db
from backend.models.scene import AssetPlan, OverlayPlan, ScenePlan

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


# --- SCENES-MP4 D9-T03: World Desk as asset source + map honesty ---
# Asset planning also matches world_records (photo/logo/meme kinds with files
# from the Download Desk) as photo/insert-layer assets; the compositor pastes
# them like any asset. Map-trigger (MT) records resolve to an honest labelled
# "map coming" box — never a silent blank, never a faked map.
# Shape: BE-driven injection (beat_elements RW/MT cites) + an MT guard on the
# LLM-need path (an LLM need that matches an MT world becomes an honesty row,
# never an SVG miss). No new tables, no new AI jobs, no frontend changes.
# World rows are kind='photo', library_ref set, needs_generate=0 — so the
# existing XOR CHECK holds and the trace query is a join through
# library.asset_ref = world_records.id.

_MAP_BOX_FILL = (48, 72, 110)
_MAP_BOX_EDGE = (77, 195, 255)


def _draw_map_coming_box(canvas, box: tuple[int, int, int, int],
                         world_id: str, world_text: str) -> None:
    """Honest MT box: filled + blue border + two centered lines.

    Called for EVERY map-trigger asset — never a silent blank, never a faked
    map. Uses the ONE shared TTF helper (_overlay_font) — never PIL's bitmap
    default silently (D9-T02 single-renderer rule)."""
    from PIL import ImageDraw as _Draw

    bx, by, bw, bh = (int(v) for v in box)
    d = _Draw.Draw(canvas)
    d.rectangle([bx, by, bx + bw, by + bh],
                fill=_MAP_BOX_FILL, outline=_MAP_BOX_EDGE, width=4)
    line1 = f"MAP COMING: {(world_id or 'map')[:30]}"
    line2 = (world_text or "map triggered — no auto map yet")[:46]
    font = _overlay_font(28)
    b1 = d.textbbox((0, 0), line1, font=font)
    b2 = d.textbbox((0, 0), line2, font=font)
    t1w, t1h = b1[2] - b1[0], b1[3] - b1[1]
    t2w, t2h = b2[2] - b2[0], b2[3] - b2[1]
    cx = bx + bw // 2
    cy = by + bh // 2
    d.text((cx - t1w // 2, cy - t1h - 2), line1, font=font, fill=(255, 255, 255),
           stroke_width=1, stroke_fill=(0, 0, 0))
    d.text((cx - t2w // 2, cy + 2), line2, font=font, fill=(255, 220, 120),
           stroke_width=1, stroke_fill=(0, 0, 0))


def _is_map_world(world: dict | None) -> bool:
    return bool(world) and (world.get("type") or "").strip().lower() == "map_trigger"


async def _load_world_index(proj_db, project_id: str):
    """World Desk index for D9-T03 matching. Worlds: stale=0, any status except
    dismissed (pending worlds with Download Desk files still count — approval
    is a review gate, not a file gate). Libraries: kind='world' slots."""
    async with proj_db.execute(
        "SELECT id, type, text, search_query FROM world_records "
        "WHERE project_id=? AND stale=0 AND status!='dismissed'",
        (project_id,)) as cur:
        worlds = [dict(r) for r in await cur.fetchall()]
    async with proj_db.execute(
        "SELECT id, asset_ref, title, file_path, status FROM library "
        "WHERE project_id=? AND kind='world'",
        (project_id,)) as cur:
        libs = [dict(r) for r in await cur.fetchall()]
    lib_by_ref = {l["asset_ref"]: l for l in libs if l.get("asset_ref")}
    world_by_id = {w["id"]: w for w in worlds if w.get("id")}
    return worlds, world_by_id, lib_by_ref


def _world_file_ready(base: Path, lib_row: dict | None) -> bool:
    if not lib_row:
        return False
    fp = (lib_row.get("file_path") or "").strip()
    if not fp:
        return False
    try:
        cand = base / fp
        return cand.exists() and cand.stat().st_size > 0
    except OSError:
        return False


def _need_matches_mt(need: dict, worlds: list[dict]):
    """LLM-need MT guard: does this need name/query match an MT world text or
    search_query (same _entry_matches the library path uses)? Returns the MT
    world dict or None. MT matches must NEVER become SVG misses (faked maps)."""
    for w in worlds:
        if (w.get("type") or "").strip().lower() != "map_trigger":
            continue
        if _entry_matches(need.get("name") or "", need.get("search_query") or "",
                           w.get("text") or ""):
            return w
        sq = (w.get("search_query") or "").strip()
        if sq and _entry_matches(need.get("name") or "", need.get("search_query") or "", sq):
            return w
    return None


async def _ensure_library_slot(proj_db, project_id: str, world: dict, now: str) -> dict:
    """Fetch-or-create the world library slot (scaffold shape). Created empty
    (no file) so MT honesty rows always have a library_ref to point at; RW
    rows only use it when a real file exists (caller checks)."""
    ref = world.get("id") or ""
    async with proj_db.execute(
        "SELECT id, asset_ref, title, file_path, status FROM library "
        "WHERE project_id=? AND asset_ref=?", (project_id, ref)) as cur:
        row = await cur.fetchone()
    if row:
        return dict(row)
    lib_id = await _next_library_id(proj_db)
    title = (world.get("text") or ref)[:200]
    await proj_db.execute(
        "INSERT INTO library (id, project_id, kind, asset_ref, title, file_path, source, "
        "status, notes, created_at, updated_at) VALUES (?,?, 'world', ?, ?, '', 'manual', "
        "'empty', '', ?, ?)",
        (lib_id, project_id, ref, title, now, now))
    return {"id": lib_id, "asset_ref": ref, "title": title,
            "file_path": "", "status": "empty"}


async def _ensure_beat_world_assets(proj_db, project_id: str, folder: str,
                                    beat_id: str, now: str):
    """BE-driven World Desk injection for one beat. For every beat_elements
    RW/MT cite: MT always gets a photo honesty row (library_ref, never SVG);
    RW (real_person/brand_logo/trademark/meme) gets a photo row ONLY when its
    library slot holds a real Download Desk file. Idempotent (insert-if-missing
    on library_ref) — re-runs never duplicate, never delete, never touch LLM
    rows or generations. Returns (added, mt_added, rw_added)."""
    base = Path(DATA_DIR) / "projects" / folder
    worlds, world_by_id, lib_by_ref = await _load_world_index(proj_db, project_id)
    if not worlds:
        return 0, 0, 0
    async with proj_db.execute(
        "SELECT DISTINCT asset_ref FROM beat_elements WHERE beat_id=?", (beat_id,)) as cur:
        be_refs = [r["asset_ref"] for r in await cur.fetchall() if r["asset_ref"]]
    # Only BE cites that are known worlds (RW/MT). Distinct per beat.
    be_worlds = [r for r in dict.fromkeys(be_refs) if r in world_by_id]
    if not be_worlds:
        return 0, 0, 0
    async with proj_db.execute(
        "SELECT library_ref FROM scene_assets WHERE beat_id=? AND library_ref IS NOT NULL",
        (beat_id,)) as cur:
        existing = {r["library_ref"] for r in await cur.fetchall() if r["library_ref"]}
    added, mt_added, rw_added = 0, 0, 0
    for ref in be_worlds:
        world = world_by_id[ref]
        lib = lib_by_ref.get(ref)
        if _is_map_world(world):
            if lib is None:
                lib = await _ensure_library_slot(proj_db, project_id, world, now)
                lib_by_ref[ref] = lib
            if lib["id"] in existing:
                continue
            name = (world.get("text") or ref)[:200]
            sq = ((world.get("search_query") or "").strip() or (world.get("text") or ref))[:200]
            reasoning = (
                f"World Desk match: beat {beat_id} cites {ref} ({name[:60]}); "
                "map trigger resolves to honesty box, never a faked map.")
            await proj_db.execute(
                "INSERT INTO scene_assets (beat_id, name, kind, search_query, reasoning, "
                "library_ref, needs_generate, generation_id, created_at, updated_at) "
                "VALUES (?,?, 'photo', ?,?,?,0,NULL,?,?)",
                (beat_id, name, sq, reasoning, lib["id"], now, now))
            existing.add(lib["id"])
            added += 1
            mt_added += 1
        else:
            # RW/logo/meme/photo kinds: photo/insert-layer ONLY with a real file.
            if not _world_file_ready(base, lib):
                continue
            if lib["id"] in existing:
                continue
            name = (world.get("text") or ref)[:200]
            sq = ((world.get("search_query") or "").strip() or (world.get("text") or ref))[:200]
            reasoning = (
                f"World Desk match: beat {beat_id} cites {ref} ({name[:60]}); "
                "Download Desk file renders as photo insert, like any asset.")
            await proj_db.execute(
                "INSERT INTO scene_assets (beat_id, name, kind, search_query, reasoning, "
                "library_ref, needs_generate, generation_id, created_at, updated_at) "
                "VALUES (?,?, 'photo', ?,?,?,0,NULL,?,?)",
                (beat_id, name, sq, reasoning, lib["id"], now, now))
            existing.add(lib["id"])
            added += 1
            rw_added += 1
    return added, mt_added, rw_added


@router.post("/projects/{project_id}/scenes/assets/plan")
async def plan_scene_assets(project_id: str, beat_id: Optional[str] = None):
    try:
        return await _plan_assets_inner(project_id, beat_id=beat_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Asset plan crashed: {type(e).__name__}: {e}")


async def _plan_assets_inner(project_id: str, beat_id: Optional[str] = None):
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
    # S-T02: per-beat re-plan filter (existing AI logic, scoped to one beat).
    # beat_id is an optional query param (?beat_id=B01) — no new AI job, just
    # a filter on the same loop. Validates the beat belongs to this project
    # so a typo 404s instead of silently planning zero beats.
    filter_beat: Optional[str] = None
    if beat_id is not None:
        filter_beat = (beat_id or "").strip()
        if not filter_beat:
            await proj_db.close()
            raise HTTPException(422, "beat_id must be non-empty when provided")
        async with proj_db.execute(
            "SELECT id FROM beats WHERE id=? AND project_id=?",
            (filter_beat, project_id)) as cur:
            beat_row = await cur.fetchone()
        if not beat_row:
            await proj_db.close()
            raise HTTPException(404, "Beat not found")
        filtered = [s for s in scenes if s["beat_id"] == filter_beat]
        if not filtered:
            await proj_db.close()
            raise HTTPException(400, "Plan scenes first (no scene row for this beat).")
        scenes = filtered

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

    # D9-T03 World Desk index (MT guard + BE injection below). Loaded once so
    # the per-beat loop stays a pure match/store (no N+1 world scans).
    world_list, _world_by_id, _lib_by_world = await _load_world_index(proj_db, project_id)

    planned_scenes, total_needs, matched, to_generate = 0, 0, 0, 0
    world_added_total, mt_added_total, rw_added_total = 0, 0, 0
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
                        # D9-T03 MT guard (vault miss path): an LLM need matching
                        # an MT world becomes an honesty row, never an SVG miss.
                        mt_world = _need_matches_mt(need, world_list)
                        if mt_world is not None:
                            lib_slot = _lib_by_world.get(mt_world["id"])
                            if lib_slot is None:
                                lib_slot = await _ensure_library_slot(
                                    proj_db, project_id, mt_world, now)
                                _lib_by_world[mt_world["id"]] = lib_slot
                            await proj_db.execute(
                                "INSERT INTO scene_assets (beat_id, name, kind, search_query, reasoning, "
                                "library_ref, needs_generate, generation_id, created_at, updated_at) "
                                "VALUES (?,?, 'photo', ?,?,?,0,NULL,?,?)",
                                (beat_id, need["name"], need["search_query"],
                                 f"LLM need '{need['name'][:60]}' matched {mt_world['id']} "
                                 "map trigger — honesty box, never a faked map.",
                                 lib_slot["id"], now, now))
                            matched += 1
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
                    # D9-T03 MT guard (no-match path): same honesty row, never SVG.
                    mt_world = _need_matches_mt(need, world_list)
                    if mt_world is not None:
                        lib_slot = _lib_by_world.get(mt_world["id"])
                        if lib_slot is None:
                            lib_slot = await _ensure_library_slot(
                                proj_db, project_id, mt_world, now)
                            _lib_by_world[mt_world["id"]] = lib_slot
                        await proj_db.execute(
                            "INSERT INTO scene_assets (beat_id, name, kind, search_query, reasoning, "
                            "library_ref, needs_generate, generation_id, created_at, updated_at) "
                            "VALUES (?,?, 'photo', ?,?,?,0,NULL,?,?)",
                            (beat_id, need["name"], need["search_query"],
                             f"LLM need '{need['name'][:60]}' matched {mt_world['id']} "
                             "map trigger — honesty box, never a faked map.",
                             lib_slot["id"], now, now))
                        matched += 1
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
            # D9-T03 BE-driven World Desk injection (RW with files + MT always).
            # Runs after the LLM needs so BE cites are covered even when the LLM
            # never proposes them; dedupes against just-inserted LLM rows via
            # library_ref, counts as matched (library_ref) to keep the
            # needs = matched + to_generate invariant.
            try:
                w_added, w_mt, w_rw = await _ensure_beat_world_assets(
                    proj_db, project_id, folder, beat_id, now)
                total_needs += w_added
                matched += w_added
                world_added_total += w_added
                mt_added_total += w_mt
                rw_added_total += w_rw
            except Exception as e:
                failed.append({"beat_id": beat_id,
                               "error": f"world-sync crashed: {type(e).__name__}: {str(e)[:150]}"})
                continue
            planned_scenes += 1
        except Exception as e:
            failed.append({"beat_id": beat_id,
                           "error": f"match/store crashed: {type(e).__name__}: {str(e)[:150]}"})
            continue

    await proj_db.commit()
    await proj_db.close()
    out = {"planned_scenes": planned_scenes, "total_needs": total_needs,
            "matched": matched, "to_generate": to_generate,
            "world_added": world_added_total, "mt_added": mt_added_total,
            "rw_added": rw_added_total,
            "failed": failed, "total_scenes": len(scenes)}
    # S-T02: echo the filter so the strip hook can confirm it re-planned one
    # beat (additive key — full-batch callers ignore it).
    if filter_beat is not None:
        out["beat_id"] = filter_beat
    return out


@router.post("/projects/{project_id}/scenes/assets/world-sync")
async def world_sync_scene_assets(project_id: str):
    """D9-T03 World Desk backfill (no LLM, additive-only).

    Ensures every beat_elements RW/MT cite has a scene_assets photo row:
    MT always (honesty box), RW only with a real Download Desk file.
    Idempotent insert-if-missing — never deletes, never touches generations,
    safe to run on projects with 107 final SVGs (unlike full re-plan).
    """
    try:
        folder, _ch_id = await _get_proj_info(project_id)
        proj_db = await get_project_db(folder)
        try:
            async with proj_db.execute(
                "SELECT b.id AS beat_id FROM scenes s JOIN beats b ON b.id=s.beat_id "
                "WHERE b.project_id=? ORDER BY b.sort_order", (project_id,)) as cur:
                beat_ids = [r["beat_id"] for r in await cur.fetchall()]
            if not beat_ids:
                raise HTTPException(400, "Plan scenes first (no scene rows to sync worlds for).")
            now = _now()
            synced, added, mt_added, rw_added = 0, 0, 0, 0
            failed: list[dict] = []
            for beat_id in beat_ids:
                try:
                    w_added, w_mt, w_rw = await _ensure_beat_world_assets(
                        proj_db, project_id, folder, beat_id, now)
                    synced += 1
                    added += w_added
                    mt_added += w_mt
                    rw_added += w_rw
                except Exception as e:
                    failed.append({"beat_id": beat_id,
                                   "error": f"world-sync crashed: {type(e).__name__}: {str(e)[:150]}"})
                    continue
            await proj_db.commit()
        finally:
            await proj_db.close()
        return {"synced_beats": synced, "world_added": added,
                "mt_added": mt_added, "rw_added": rw_added,
                "failed": failed, "total_scenes": len(beat_ids)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"World sync crashed: {type(e).__name__}: {e}")


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


# --- SCENES-MP4 S-T02: coverage lint + per-beat re-plan (backend, no AI) ---
# Local check only (zero LLM calls): entities named in the beat (distinct
# beat_elements.asset_ref — the beat breakdown's "who/what is in this beat")
# vs assets planned (scene_assets rows for that beat). Thin = planned < named
# with the reason "mentions {named} things, planned {planned}". Advisory only:
# never blocks planning/approval/render — the strip hook shows an amber flag
# with a one-click re-plan (POST .../assets/plan?beat_id=... above). Rich
# beats (planned >= named, incl. pure-narration 0/0) stay silent (thin=false,
# reason="").


def _coverage_reason(named: int, planned: int) -> str:
    thing = "thing" if named == 1 else "things"
    return f"mentions {named} {thing}, planned {planned}"


@router.get("/projects/{project_id}/scenes/coverage")
async def scene_coverage(project_id: str):
    """Advisory thin-beat lint (no AI, never blocks).

    Returns per-beat {named, planned, thin, reason} + thin_count/total_beats.
    """
    try:
        folder, _ = await _get_proj_info(project_id)
        proj_db = await get_project_db(folder)
        try:
            async with proj_db.execute(
                "SELECT id FROM beats WHERE project_id=? ORDER BY sort_order",
                (project_id,)) as cur:
                beat_ids = [r["id"] for r in await cur.fetchall()]
            async with proj_db.execute(
                "SELECT beat_id FROM scenes WHERE beat_id IN "
                "(SELECT id FROM beats WHERE project_id=?)",
                (project_id,)) as cur:
                scene_set = {r["beat_id"] for r in await cur.fetchall()}
            beats_out: list[dict] = []
            thin_count = 0
            for bid in beat_ids:
                async with proj_db.execute(
                    "SELECT DISTINCT asset_ref FROM beat_elements WHERE beat_id=?",
                    (bid,)) as cur:
                    refs = sorted(
                        [r["asset_ref"] for r in await cur.fetchall() if r["asset_ref"]])
                async with proj_db.execute(
                    "SELECT COUNT(*) AS c FROM scene_assets WHERE beat_id=?",
                    (bid,)) as cur:
                    row = await cur.fetchone()
                planned = int(row["c"]) if row else 0
                named = len(refs)
                thin = named > planned
                reason = _coverage_reason(named, planned) if thin else ""
                if thin:
                    thin_count += 1
                beats_out.append({
                    "beat_id": bid,
                    "named": named,
                    "named_refs": refs,
                    "planned": planned,
                    "has_scene": bid in scene_set,
                    "thin": thin,
                    "reason": reason,
                })
        finally:
            await proj_db.close()
        return {"beats": beats_out, "thin_count": thin_count,
                "total_beats": len(beat_ids)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Coverage check crashed: {type(e).__name__}: {e}")


# --- SCENES-MP4 D9-T01: overlay spec (data + AI propose, no rendering) ---
# Per scene the AI proposes 0+ text overlays (or explicit none = empty list).
# Re-plan is replace-on-success per beat (P1-T06 precedent): old rows are
# deleted only after a successful dispatch, so a failed beat keeps its
# previous items. Manual PUT/DELETE per row always allowed.

_OVERLAY_ROLES = frozenset({"name", "place", "date", "number", "quote", "warning"})


class OverlayEdit(BaseModel):
    text: Optional[str] = None
    role: Optional[str] = None
    color: Optional[str] = None
    position: Optional[str] = None
    reasoning: Optional[str] = None


@router.post("/projects/{project_id}/scenes/overlays/plan")
async def plan_scene_overlays(project_id: str):
    try:
        return await _plan_overlays_inner(project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Overlay plan crashed: {type(e).__name__}: {e}")


async def _plan_overlays_inner(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT b.id AS beat_id, b.text AS beat_text, s.place_asset_ref, s.shot, s.reasoning "
        "FROM scenes s JOIN beats b ON b.id=s.beat_id "
        "WHERE b.project_id=? ORDER BY b.sort_order", (project_id,)) as cur:
        scenes = [dict(r) for r in await cur.fetchall()]
    if not scenes:
        await proj_db.close()
        raise HTTPException(400, "Plan scenes first (no scene rows to plan overlays for).")

    planned_scenes, total_overlays, with_overlays = 0, 0, 0
    failed: list[dict] = []
    now = _now()
    for sc in scenes:
        beat_id = sc["beat_id"]
        context = {
            "scene": {"place_ref": sc["place_asset_ref"], "shot": sc["shot"],
                       "reasoning": sc["reasoning"]},
            "beat_text": sc["beat_text"],
        }
        try:
            res = await dispatch("overlay_text", context, schema=OverlayPlan,
                                 project_id=project_id, channel_id=ch_id)
        except Exception as e:
            # One scene's crash must not kill the batch (mirrors T05 per-beat guard).
            failed.append({"beat_id": beat_id,
                           "error": f"dispatch crashed: {type(e).__name__}: {str(e)[:150]}"})
            continue
        if not res["ok"]:
            failed.append({"beat_id": beat_id, "error": str(res.get("error"))[:200]})
            continue

        items = (res["parsed"] or {}).get("overlays") or []
        try:
            # Replace-on-success: delete this beat's old items only now that the
            # new plan validated, so re-runs never duplicate and failures keep
            # the previous items.
            await proj_db.execute("DELETE FROM scene_overlays WHERE beat_id=?", (beat_id,))
            for it in items:
                await proj_db.execute(
                    "INSERT INTO scene_overlays (beat_id, text, role, color, position, "
                    "reasoning, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (beat_id, it["text"], it["role"], it["color"], it["position"],
                     it["reasoning"], now, now))
            total_overlays += len(items)
            if items:
                with_overlays += 1
            planned_scenes += 1
        except Exception as e:
            failed.append({"beat_id": beat_id,
                           "error": f"store crashed: {type(e).__name__}: {str(e)[:150]}"})
            continue

    await proj_db.commit()
    await proj_db.close()
    return {"planned_scenes": planned_scenes, "total_overlays": total_overlays,
            "beats_with_overlays": with_overlays,
            "beats_without_overlays": planned_scenes - with_overlays,
            "failed": failed, "total_scenes": len(scenes)}


@router.get("/projects/{project_id}/scenes/overlays")
async def list_scene_overlays(project_id: str):
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT so.* FROM scene_overlays so JOIN beats b ON b.id=so.beat_id "
        "WHERE b.project_id=? ORDER BY b.sort_order, so.id", (project_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await proj_db.close()
    return rows


@router.put("/projects/{project_id}/scenes/overlays/{overlay_id}")
async def edit_scene_overlay(project_id: str, overlay_id: int, data: OverlayEdit):
    """Manual overlay edit — always allowed (human accepts/fixes per item)."""
    if data.text is not None and not data.text.strip():
        raise HTTPException(422, "text must be non-empty (DELETE the row to reject it)")
    if data.role is not None and data.role.strip().lower() not in _OVERLAY_ROLES:
        raise HTTPException(422, "role must be one of name|place|date|number|quote|warning")
    if data.reasoning is not None and not data.reasoning.strip():
        raise HTTPException(422, "reasoning must be non-empty")
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT so.* FROM scene_overlays so JOIN beats b ON b.id=so.beat_id "
        "WHERE so.id=? AND b.project_id=?", (overlay_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close()
        raise HTTPException(404, "Overlay not found")
    row = dict(row)
    await proj_db.execute(
        "UPDATE scene_overlays SET text=?, role=?, color=?, position=?, reasoning=?, "
        "updated_at=? WHERE id=?",
        (data.text.strip() if data.text is not None else row["text"],
         data.role.strip().lower() if data.role is not None else row["role"],
         data.color.strip() if data.color is not None else row["color"],
         data.position.strip() if data.position is not None else row["position"],
         data.reasoning.strip() if data.reasoning is not None else row["reasoning"],
         _now(), overlay_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "saved"}


@router.delete("/projects/{project_id}/scenes/overlays/{overlay_id}")
async def delete_scene_overlay(project_id: str, overlay_id: int):
    """Manual overlay reject — always allowed (human rejects per item)."""
    folder, _ = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT so.id FROM scene_overlays so JOIN beats b ON b.id=so.beat_id "
        "WHERE so.id=? AND b.project_id=?", (overlay_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close()
        raise HTTPException(404, "Overlay not found")
    await proj_db.execute("DELETE FROM scene_overlays WHERE id=?", (overlay_id,))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "deleted"}


# --- SCENES-MP4 P3-T01: server-side scene preview (Pillow composite, no new deps) ---
# Canvas is fixed 1920x1080. Place layer fills the canvas; each scene_asset
# draws into its x/y/scale box (0-1 fractions from beat_elements when a
# matching placement exists, else a deterministic default from framing/kind).
# Aspect rule (architect constraint from the T06 review): raster PNGs are
# fixed 1920x1080, so every paste is letterbox/fit — uniform scale,
# centered, NEVER stretched. Missing asset = honest labelled box, never a
# silent blank. Previews cache per scene-hash under 07_beats/previews/.

_PRE_W, _PRE_H = 1920, 1080
# SCENES-MP4 F1-T02: legacy canvas fallback (pre-wheel previews were dark
# navy). The live default is the channel chroma (green #00FF00) unless the
# project saves its own color — resolved per preview via _resolve_canvas_bg().
# Frames reuse scene_preview() by byte-copy (P4-T02), so they read the same bg.
_PRE_BG = (26, 29, 41)
_PRE_BG_FALLBACK_HEX = "#00FF00"
_MISSING_FILL = (58, 58, 64)
_MISSING_EDGE = (255, 85, 85)


async def _resolve_canvas_bg(project_id: str) -> tuple[str, tuple[int, int, int]]:
    """F1-T02 effective canvas background (hex + RGB). Project override wins;
    otherwise the channel chroma (channels.bg_default_hex); otherwise green.
    The green auto-white asset logic is untouched — this is the scene canvas
    only. Never raises: falls back to chroma green on any lookup failure."""
    try:
        from backend.api.projects import resolve_project_background
        bg = await resolve_project_background(project_id)
        hex_color = (bg.get("bg_color") or _PRE_BG_FALLBACK_HEX).strip().upper()
        rgb = tuple(bg.get("rgb") or (0, 255, 0))
        if (len(rgb) != 3 or
                not all(isinstance(c, int) and 0 <= c <= 255 for c in rgb)):
            rgb = (0, 255, 0)
        return hex_color, (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    except Exception:
        return _PRE_BG_FALLBACK_HEX, (0, 255, 0)

_FRAMING_SCALE = {
    "close": 0.55, "medium": 0.42, "wide": 0.32,
    "full": 0.85, "establishing": 0.85, "long": 0.32,
}
_LAYER_RANK = {"background": 0, "midground": 1, "foreground": 2, "insert": 3}


def _valid_frac(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= float(v) <= 1


def _framing_scale(framing: str, kind: str) -> float:
    f = (framing or "").strip().lower()
    if f in _FRAMING_SCALE:
        return _FRAMING_SCALE[f]
    # No framing hint (generated misses carry kind only): places read wide,
    # everything else reads medium.
    if (kind or "").lower() in ("place", "photo"):
        return _FRAMING_SCALE["wide"]
    return _FRAMING_SCALE["medium"]


def _default_box(i: int, n: int, framing: str, kind: str) -> tuple[float, float, float]:
    """Deterministic default box (fractions). Single asset centers; rows of
    2+ spread left-to-right, bottom-anchored so boxes never fully overlap.

    LEGACY (pre S-T01): kept for reference only — the live compositor default
    is now the seeded scatter below (_scatter_default). Do not call for new
    previews; do not delete (additive-only rule)."""
    scale = _framing_scale(framing, kind)
    # A lone place/photo is an establishing view — let it read large.
    if n == 1 and (kind or "").lower() in ("place", "photo"):
        scale = 0.85
    scale = min(max(float(scale), 0.05), 1.0)
    if n <= 1:
        x = (1.0 - scale) / 2.0
        y = (1.0 - scale) / 2.0
    else:
        span = max(0.92 - scale, 0.0)
        x = 0.04 + (span * i / (n - 1) if n > 1 else 0.0)
        y = 0.92 - scale
        x = min(max(float(x), 0.0), max(1.0 - scale, 0.0))
        y = min(max(float(y), 0.02), max(1.0 - scale, 0.02))
    return float(x), float(y), float(scale)


# --- SCENES-MP4 S-T01: seeded scatter default (Stein-quality, compositor only) ---
# Replaces bottom-row _default_box as the live default. Per-beat seed => stable
# re-renders (same beat => byte-identical PNG). Region-weighted positions +
# mixed scales, overlap allowed, nothing fully off-canvas, nothing fully
# covering another asset's face zone. Explicit x/y/scale always wins — scatter
# is the default, never the boss (the face-guard never moves explicit boxes).
# No new dependency (random + hashlib are stdlib); single-renderer rule kept
# (render.py reuses scene_preview, so frames inherit scatter automatically).

# ((x0,x1),(y0,y1),weight) in 0-1 fractions; weights sum to 100.
_SCATTER_REGIONS: tuple = (
    ((0.30, 0.62), (0.30, 0.58), 30),  # center
    ((0.04, 0.28), (0.30, 0.68), 20),  # left-mid
    ((0.68, 0.92), (0.30, 0.68), 20),  # right-mid
    ((0.18, 0.72), (0.04, 0.26), 15),  # upper
    ((0.18, 0.72), (0.66, 0.88), 15),  # lower
)
_SCATTER_JITTER_LO = 0.85
_SCATTER_JITTER_HI = 1.20


def _beat_seed(beat_id: str) -> int:
    """Stable per-beat seed (sha256 hex -> int). Never Python hash() (salted)."""
    return int(hashlib.sha256((beat_id or "").encode("utf-8")).hexdigest()[:8], 16)


def _scatter_default(beat_id: str, idx: int, framing: str, kind: str) -> tuple[float, float, float]:
    """Seeded scatter box (fractions). Deterministic in (beat_id, idx, framing,
    kind) — independent of sibling count so adding an asset never reshuffles
    existing ones. Overlap allowed by design; on-canvas guaranteed by clamp."""
    rng = random.Random((_beat_seed(beat_id) ^ (idx * 0x9E3779B1 + 0x85EBCA6B)) & 0xFFFFFFFF)
    base = _framing_scale(framing, kind)
    scale = float(base) * rng.uniform(_SCATTER_JITTER_LO, _SCATTER_JITTER_HI)
    scale = min(max(scale, 0.05), 1.0)
    total = sum(w for _, _, w in _SCATTER_REGIONS)
    pick = rng.random() * total
    acc = 0.0
    region = _SCATTER_REGIONS[0]
    for reg in _SCATTER_REGIONS:
        acc += reg[2]
        if pick < acc:
            region = reg
            break
    (rx0, rx1), (ry0, ry1), _w = region
    x = rng.uniform(min(rx0, rx1), max(rx0, rx1))
    y = rng.uniform(min(ry0, ry1), max(ry0, ry1))
    x = min(max(float(x), 0.0), max(1.0 - scale, 0.0))
    y = min(max(float(y), 0.0), max(1.0 - scale, 0.0))
    return float(x), float(y), float(scale)


def _face_zone_px(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Face zone: top-center 40% wide x top 25% tall of the asset box."""
    bx, by, bw, bh = box
    return (int(bx + bw * 0.30), int(by), int(max(bw * 0.40, 1)), int(max(bh * 0.25, 1)))


def _rect_covers(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (ox <= ix and oy <= iy and ox + ow >= ix + iw and oy + oh >= iy + ih)


def _scatter_deconflict(items: list[dict]) -> None:
    """Nudge scattered coverers off full face coverage, in place.

    For every pair (coverer C, victim V != C): if C's pixel box fully contains
    V's face zone, and C is movable (fully scattered — zero explicit coords),
    walk C by prime strides (+173,+149)px wrapping inside the canvas until it
    no longer covers THAT victim (max 60 steps), then continue. Up to 30 outer
    sweeps so chained pairs converge; deterministic, no RNG. Explicit boxes
    (any valid x/y/scale hint) NEVER move — explicit always wins, scatter is
    never the boss. Partial overlap stays allowed; only FULL face coverage is
    repaired."""
    for _ in range(30):
        boxes = []
        for it in items:
            bw, bh = int(it["scale"] * _PRE_W), int(it["scale"] * _PRE_H)
            bx, by = int(it["x"] * _PRE_W), int(it["y"] * _PRE_H)
            bx = min(max(bx, 0), max(_PRE_W - bw, 0))
            by = min(max(by, 0), max(_PRE_H - bh, 0))
            boxes.append([bx, by, bw, bh])
        moved = False
        for ci, c in enumerate(items):
            if not c.get("scatter_movable", True):
                continue
            bw, bh = boxes[ci][2], boxes[ci][3]
            span_x = max(_PRE_W - bw, 1)
            span_y = max(_PRE_H - bh, 1)
            for vi, v in enumerate(items):
                if vi == ci:
                    continue
                for _step in range(60):
                    cb = (boxes[ci][0], boxes[ci][1], bw, bh)
                    vb = (boxes[vi][0], boxes[vi][1], boxes[vi][2], boxes[vi][3])
                    if not _rect_covers(cb, _face_zone_px(vb)):
                        break
                    boxes[ci][0] = (boxes[ci][0] + 173) % span_x
                    boxes[ci][1] = (boxes[ci][1] + 149) % span_y
                    moved = True
        for it, b in zip(items, boxes):
            it["x"] = min(max(b[0] / _PRE_W, 0.0), max(1.0 - it["scale"], 0.0))
            it["y"] = min(max(b[1] / _PRE_H, 0.0), max(1.0 - it["scale"], 0.0))
        if not moved:
            break


def _paste_fit(canvas, img, box: tuple[int, int, int, int]) -> None:
    """Letterbox/fit paste: uniform scale to fit inside box, centered, never
    stretched. Box margins show whatever is behind (the place layer)."""
    from PIL import Image as _Image

    bx, by, bw, bh = (int(v) for v in box)
    if bw <= 0 or bh <= 0:
        return
    sw, sh = img.size
    if sw <= 0 or sh <= 0:
        return
    s = min(bw / sw, bh / sh)
    if s <= 0:
        return
    nw, nh = max(1, int(sw * s)), max(1, int(sh * s))
    resized = img.resize((nw, nh), _Image.LANCZOS)
    ox, oy = bx + (bw - nw) // 2, by + (bh - nh) // 2
    if resized.mode in ("RGBA", "LA"):
        canvas.paste(resized, (ox, oy), resized)
    else:
        if resized.mode == "P":
            resized = resized.convert("RGBA")
            canvas.paste(resized, (ox, oy), resized)
        else:
            if resized.mode != "RGB":
                resized = resized.convert("RGB")
            canvas.paste(resized, (ox, oy))


def _draw_labelled_box(canvas, box: tuple[int, int, int, int],
                       title: str, reason: str) -> None:
    """Honest missing-asset box: filled + red border + two centered lines.
    Called for EVERY unresolvable asset — never leave a silent blank.
    Uses the ONE shared TTF helper (_overlay_font) — never PIL's bitmap
    default silently (D9-T02 single-renderer rule)."""
    from PIL import ImageDraw as _Draw

    bx, by, bw, bh = (int(v) for v in box)
    d = _Draw.Draw(canvas)
    d.rectangle([bx, by, bx + bw, by + bh],
                fill=_MISSING_FILL, outline=_MISSING_EDGE, width=4)
    line1 = f"MISSING: {(title or 'asset')[:30]}"
    line2 = (reason or "no file")[:46]
    font = _overlay_font(28)
    b1 = d.textbbox((0, 0), line1, font=font)
    b2 = d.textbbox((0, 0), line2, font=font)
    t1w, t1h = b1[2] - b1[0], b1[3] - b1[1]
    t2w, t2h = b2[2] - b2[0], b2[3] - b2[1]
    cx = bx + bw // 2
    cy = by + bh // 2
    d.text((cx - t1w // 2, cy - t1h - 2), line1, font=font, fill=(255, 255, 255),
           stroke_width=1, stroke_fill=(0, 0, 0))
    d.text((cx - t2w // 2, cy + 2), line2, font=font, fill=(255, 220, 120),
           stroke_width=1, stroke_fill=(0, 0, 0))


# --- SCENES-MP4 D9-T02: overlay render (Pillow text, no image model) ---
# SINGLE-RENDERER RULE (locked): scene_preview + the P4 frame path share ONE
# Pillow text helper — _draw_overlays() below. render.py reuses
# scenes.scene_preview() + byte-copies the PNG (_write_beat_frames), so it
# must NEVER grow its own ImageFont/ImageDraw text path. Role colors come
# from the item's color field (recipe plate color); the font is a real TTF
# via _probe_overlay_font() with a LOUD failure (never PIL's bitmap default
# silently). Overlay content lives in the preview cache key — a one-letter
# text change MUST bust the cache (stale art on text change is a bug).

_OVERLAY_FONT_ENV = "OVERLAY_FONT_PATH"
# Bold-first: plates + missing boxes + beat tag all want bold for crispness.
_OVERLAY_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
)
_OVERLAY_FONT_SIZE = 44
_OVERLAY_PAD_X = 28
_OVERLAY_PAD_Y = 16
_OVERLAY_MARGIN = 36
_OVERLAY_TOP_CLEAR = 70  # clears the beat tag at (10,10) so top plates stay visible
_OVERLAY_GAP = 12


def _probe_overlay_font() -> tuple[str, str, list[str]]:
    """Probe for a real TTF for overlay plates. Returns (path, source, tried).

    Order: OVERLAY_FONT_PATH env -> well-known system bold/regular fonts.
    tried lists every location checked (Inkscape/ffmpeg probe discipline).
    Raises FileNotFoundError naming every location tried when not found —
    callers surface it as a loud 500, NEVER fall back to bitmap silently.
    """
    tried: list[str] = []
    env = (os.environ.get(_OVERLAY_FONT_ENV) or "").strip().strip('"')
    if env:
        tried.append(f"{_OVERLAY_FONT_ENV}={env}")
        if os.path.isfile(env):
            return env, "env", tried
        tried.append(f"{_OVERLAY_FONT_ENV} missing on disk: {env}")
    else:
        tried.append(f"{_OVERLAY_FONT_ENV}=(unset)")
    for cand in _OVERLAY_FONT_CANDIDATES:
        if os.path.isfile(cand):
            return cand, "system", tried + [f"system:{cand}=found"]
        tried.append(f"system:{cand}=missing")
    raise FileNotFoundError(
        "Overlay font not found. Tried: " + " | ".join(tried))


def _overlay_font(size: int):
    """Load the shared TTF at a size. Fails LOUD (FileNotFoundError with the
    tried list) — never ImageFont.load_default() silently."""
    from PIL import ImageFont as _Font

    path, _source, _tried = _probe_overlay_font()
    try:
        return _Font.truetype(path, size)
    except Exception as e:
        raise RuntimeError(
            f"Overlay font unreadable ({path}): {type(e).__name__}: {e}")


def _parse_plate_color(s: str) -> tuple[int, int, int]:
    """Role color FROM THE ITEM (recipe plate color). Accepts #RRGGBB / #RGB /
    PIL color names; invalid values fall back to white so one bad row never
    kills the preview (the text still renders — honest, not blank)."""
    raw = (s or "").strip()
    if raw.startswith("#"):
        h = raw[1:].strip()
        if len(h) == 3 and all(c in "0123456789abcdefABCDEF" for c in h):
            return (int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16))
        if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h):
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    try:
        from PIL import ImageColor as _Color
        return tuple(_Color.getrgb(raw))[:3]  # type: ignore[return-value]
    except Exception:
        return (255, 255, 255)


def _overlay_text_colors(plate: tuple[int, int, int]) -> tuple[tuple, tuple]:
    """Contrast pair for crisp text on the plate: dark text + white outline
    on light plates, white text + black outline on dark plates."""
    lum = 0.299 * plate[0] + 0.587 * plate[1] + 0.114 * plate[2]
    if lum > 150:
        return ((20, 20, 20), (255, 255, 255))
    return ((255, 255, 255), (0, 0, 0))


def _draw_overlays(canvas, overlays: list[dict]) -> None:
    """THE shared Pillow text renderer (D9-T02). Draws each overlay as a
    filled plate (role color from the item) + bold TTF text + outline at its
    box. Used by scene_preview; the P4 frame path reuses scene_preview, so
    this is the ONLY text renderer — never add a second one."""
    from PIL import ImageDraw as _Draw

    if not overlays:
        return
    d = _Draw.Draw(canvas)
    max_w = _PRE_W - _OVERLAY_MARGIN * 2
    # Separate vertical cursors per zone so mixed positions never overlap.
    top_cur = _OVERLAY_TOP_CLEAR
    low_cur = int(_PRE_H * 0.70)
    bot_cur = _PRE_H - _OVERLAY_MARGIN
    for ov in overlays:
        text = (ov.get("text") or "").strip()
        if not text:
            continue
        pos = (ov.get("position") or "lower-third").strip().lower()
        if pos not in ("top", "bottom", "lower-third", "top-left", "top-right"):
            pos = "lower-third"
        plate = _parse_plate_color(ov.get("color") or "")
        fg, stroke = _overlay_text_colors(plate)
        size = _OVERLAY_FONT_SIZE
        font = _overlay_font(size)
        # Shrink-to-fit so long quotes stay pixel-crisp inside 1920×1080.
        while size > 20:
            bb = d.textbbox((0, 0), text, font=font)
            if (bb[2] - bb[0]) + _OVERLAY_PAD_X * 2 <= max_w:
                break
            size -= 4
            font = _overlay_font(size)
        bb = d.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        pw, ph = tw + _OVERLAY_PAD_X * 2, th + _OVERLAY_PAD_Y * 2
        pw = min(pw, max_w)
        if pos in ("top", "top-left", "top-right"):
            y = top_cur
            top_cur += ph + _OVERLAY_GAP
        elif pos == "bottom":
            bot_cur -= ph
            y = bot_cur
            bot_cur -= _OVERLAY_GAP
        else:  # lower-third (default for names)
            y = low_cur
            low_cur += ph + _OVERLAY_GAP
        if pos in ("top", "bottom", "lower-third"):
            x = (_PRE_W - pw) // 2
        elif pos == "top-left":
            x = _OVERLAY_MARGIN
        else:  # top-right
            x = _PRE_W - pw - _OVERLAY_MARGIN
        x = min(max(int(x), 2), _PRE_W - pw - 2)
        y = min(max(int(y), 2), _PRE_H - ph - 2)
        d.rectangle([x, y, x + pw, y + ph], fill=plate, outline=(0, 0, 0), width=3)
        d.text((x + _OVERLAY_PAD_X, y + _OVERLAY_PAD_Y), text, font=font,
               fill=fg, stroke_width=2, stroke_fill=stroke)


def _file_hash(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return ""


@router.get("/projects/{project_id}/scenes/{beat_id}/preview")
async def scene_preview(project_id: str, beat_id: str,
                        hide: Optional[str] = None):
    # Phase 2 timed layers: ?hide=1,2,3 drops those scene_assets need IDs
    # from this render (variant stills). Empty/absent = full scene.
    # Included in the scene-hash canon below, so variants cache separately.
    from PIL import Image as _Image
    from PIL import ImageDraw as _Draw

    folder, _ch_id = await _get_proj_info(project_id)
    base = Path(DATA_DIR) / "projects" / folder
    proj_db = await get_project_db(folder)
    try:
        async with proj_db.execute(
                "SELECT * FROM beats WHERE id=? AND project_id=?",
                (beat_id, project_id)) as cur:
            beat = await cur.fetchone()
        if not beat:
            raise HTTPException(404, "Beat not found")
        beat = dict(beat)
        async with proj_db.execute(
                "SELECT * FROM scenes WHERE beat_id=?", (beat_id,)) as cur:
            scene = await cur.fetchone()
        if not scene:
            raise HTTPException(404, "No scene for this beat — plan scenes first.")
        scene = dict(scene)
        async with proj_db.execute(
                "SELECT * FROM scene_assets WHERE beat_id=? ORDER BY id",
                (beat_id,)) as cur:
            needs = [dict(r) for r in await cur.fetchall()]
        hide_set = {t for t in ((hide or "").split(",")) if t.strip()}
        if hide_set:
            needs = [n for n in needs if str(n["id"]) not in hide_set]
        async with proj_db.execute(
                "SELECT * FROM beat_elements WHERE beat_id=? ORDER BY sort_order",
                (beat_id,)) as cur:
            elements = [dict(r) for r in await cur.fetchall()]
        async with proj_db.execute(
                "SELECT id, asset_ref, title, file_path, status FROM library WHERE project_id=?",
                (project_id,)) as cur:
            lib_rows = [dict(r) for r in await cur.fetchall()]
        async with proj_db.execute(
                "SELECT id, text, role, color, position FROM scene_overlays "
                "WHERE beat_id=? ORDER BY id",
                (beat_id,)) as cur:
            overlay_rows = [dict(r) for r in await cur.fetchall()]
        # D9-T03: world index for MT honesty (map_trigger → "map coming" box).
        async with proj_db.execute(
                "SELECT id, type, text FROM world_records WHERE project_id=?",
                (project_id,)) as cur:
            world_rows = [dict(r) for r in await cur.fetchall()]
    finally:
        await proj_db.close()

    lib_by_id = {r["id"]: r for r in lib_rows}
    world_by_id = {r["id"]: r for r in world_rows if r.get("id")}
    els_by_asset: dict[str, dict] = {}
    for el in elements:
        els_by_asset.setdefault(el["asset_ref"], el)

    # --- resolve place layer ---
    place_ref = scene.get("place_asset_ref")
    place_title, place_rel, place_reason = "", "", ""
    place_path = None
    if place_ref:
        hit = next((r for r in lib_rows if r["asset_ref"] == place_ref), None)
        if hit and (hit["file_path"] or "").strip():
            cand = base / hit["file_path"]
            if cand.exists() and cand.stat().st_size > 0:
                place_path, place_rel = cand, hit["file_path"]
                place_title = hit["title"] or place_ref
            else:
                place_title = hit["title"] or place_ref
                place_reason = f"file missing: {hit['file_path'] or '(none)'}"
        else:
            # Title for the honest box even when no library row exists.
            proj_db2 = await get_project_db(folder)
            try:
                async with proj_db2.execute(
                        "SELECT name FROM environments WHERE id=? AND project_id=?",
                        (place_ref, project_id)) as cur:
                    er = await cur.fetchone()
                place_title = (er["name"] if er else place_ref) or place_ref
            finally:
                await proj_db2.close()
            place_reason = "no library file" if hit is None else "library empty"
    else:
        place_title, place_reason = "(none)", "no place ref on scene"

    # --- resolve + place each need ---
    # D9-T03: world photo assets paste like any asset (file paste when the
    # Download Desk file exists); MT rows ALWAYS resolve to the honesty box
    # (never a silent blank, never a faked map — even if a file ever lands in
    # an MT slot). World photo rows default to insert when no BE hint names a
    # layer (locked layer rule); BE hints are respected when present.
    items: list[dict] = []
    for idx, nd in enumerate(needs):
        kind = (nd.get("kind") or "prop").lower()
        hint = None
        lib = lib_by_id.get(nd.get("library_ref") or "") if nd.get("library_ref") else None
        if lib:
            hint = els_by_asset.get(lib.get("asset_ref") or "")
        world = world_by_id.get((lib.get("asset_ref") or "") if lib else "") if lib else None
        is_map = _is_map_world(world) or (
            lib is not None and (lib.get("asset_ref") or "").startswith("MT"))
        is_world = world is not None or (
            lib is not None and (lib.get("asset_ref") or "").startswith(("RW", "MT")))
        framing_eff = (hint.get("framing") if hint else "") or (
            "wide" if kind in ("place", "photo") else "medium")
        # S-T01: seeded scatter is the live default (replaces bottom-row
        # _default_box). Explicit x/y/scale always wins — scatter never bosses.
        dx, dy, ds = _scatter_default(beat_id, idx, framing_eff, kind)
        has_explicit = bool(hint and (
            _valid_frac(hint.get("x")) or _valid_frac(hint.get("y"))
            or _valid_frac(hint.get("scale"))))
        x = float(hint["x"]) if hint and _valid_frac(hint.get("x")) else dx
        y = float(hint["y"]) if hint and _valid_frac(hint.get("y")) else dy
        s = float(hint["scale"]) if hint and _valid_frac(hint.get("scale")) else ds
        s = min(max(s, 0.05), 1.0)
        x = min(max(x, 0.0), max(1.0 - s, 0.0))
        y = min(max(y, 0.0), max(1.0 - s, 0.0))
        layer = (hint.get("layer") if hint else "") or (
            "background" if kind in ("place", "photo") and not is_world else "midground")
        if is_world and not hint:
            # No BE placement to respect — world photos read as inserts.
            layer = "insert"

        rel, reason, path, fhash = "", "", None, ""
        if is_map:
            # MT honesty: live world text in the reason so a text change busts
            # the scene-hash cache (stale map box is a bug, same rule as D9-T02
            # overlay text). Path stays None so missing-count stays honest.
            world_id = (lib.get("asset_ref") if lib else "") or "MT"
            world_text = (world.get("text") if world else "") or (nd.get("name") or "")
            reason = f"map coming: {world_id} {world_text}"[:90]
        elif nd.get("library_ref"):
            if lib is None:
                reason = f"library {nd['library_ref']} missing"
            elif not (lib["file_path"] or "").strip():
                reason = f"library {lib['id']} empty"
            else:
                cand = base / lib["file_path"]
                if cand.exists() and cand.stat().st_size > 0:
                    path, rel, fhash = cand, lib["file_path"], _file_hash(cand)
                else:
                    reason = f"file missing: {lib['file_path']}"
        elif nd.get("needs_generate"):
            proj_db3 = await get_project_db(folder)
            try:
                async with proj_db3.execute(
                        "SELECT id, file_path, status, error FROM generations WHERE id=?",
                        (nd.get("generation_id"),)) as cur:
                    grow = await cur.fetchone()
            finally:
                await proj_db3.close()
            if not grow:
                reason = f"generation {nd.get('generation_id')} missing"
            else:
                grow = dict(grow)
                fp = (grow["file_path"] or "").strip()
                if fp:
                    cand = base / fp
                    if cand.exists() and cand.stat().st_size > 0:
                        path, rel, fhash = cand, fp, _file_hash(cand)
                    else:
                        reason = f"file missing: {fp} (gen {grow['id']}, {grow['status']})"
                else:
                    reason = f"svg {grow['status']} (gen {grow['id']})"
        else:
            reason = "unresolved (neither branch)"
        items.append({"need": nd, "kind": kind, "framing": framing_eff,
                      "x": x, "y": y, "scale": s, "layer": layer,
                      "path": path, "rel": rel, "reason": reason, "fhash": fhash,
                      "is_map": bool(is_map),
                      "scatter_movable": not has_explicit,
                      "world_id": ((lib.get("asset_ref") or "") if lib else "")})
    # S-T01 face-guard: repair full face coverage among scattered defaults only
    # (explicit boxes never move). Runs BEFORE the scene-hash so the guard is
    # part of the cached layout — same beat => byte-identical re-render.
    _scatter_deconflict(items)
    items.sort(key=lambda it: (_LAYER_RANK.get(it["layer"], 1), it["need"]["id"]))

    # F1-T02: effective canvas background (project override or channel
    # chroma). Resolved before the hash so the color is part of the key —
    # a bg change MUST bust the cache (stale art on bg change is a bug).
    bg_hex, bg_rgb = await _resolve_canvas_bg(project_id)

    # --- scene-hash cache key (D9-T02: overlay CONTENT is part of the key —
    # a one-letter text change MUST bust the cache; stale art is a bug) ---
    # D9-T03: MT honesty text + world linkage are part of the key — a world
    # text change or RW-file swap MUST bust the cache (fhash already covers
    # file bytes; reason covers live map text; is_map/world_id cover linkage).
    canon = {
        "beat_id": beat_id,
        "hide": sorted(hide_set) if hide_set else [],
        "place_asset_ref": place_ref,
        "shot": scene.get("shot") or "",
        "scene_updated_at": scene.get("updated_at") or "",
        "bg": bg_hex,
        "elements": [
            {"id": e["id"], "asset_ref": e["asset_ref"], "x": e.get("x"),
             "y": e.get("y"), "scale": e.get("scale"),
             "framing": e.get("framing"), "layer": e.get("layer")}
            for e in elements
        ],
        "needs": [
            {"id": it["need"]["id"], "name": it["need"]["name"],
             "kind": it["kind"], "library_ref": it["need"].get("library_ref"),
             "generation_id": it["need"].get("generation_id"),
             "rel": it["rel"], "fhash": it["fhash"], "reason": it["reason"],
             "x": it["x"], "y": it["y"], "scale": it["scale"],
             "is_map": it.get("is_map", False), "world_id": it.get("world_id", "")}
            for it in items
        ],
        "place": {"rel": place_rel, "fhash": _file_hash(place_path) if place_path else "",
                  "reason": place_reason},
        "overlays": [
            {"id": o["id"], "text": o.get("text") or "", "role": o.get("role") or "",
             "color": o.get("color") or "", "position": o.get("position") or ""}
            for o in overlay_rows
        ],
    }
    full_hash = hashlib.sha256(
        json.dumps(canon, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    short = full_hash[:12]
    prev_dir = base / "07_beats" / "previews"
    prev_dir.mkdir(parents=True, exist_ok=True)
    dest = prev_dir / f"{beat_id}_{short}.png"
    missing = sum(1 for it in items if it["path"] is None) + (1 if place_path is None else 0)
    map_count = sum(1 for it in items if it.get("is_map"))

    if dest.exists() and dest.stat().st_size > 0:
        return FileResponse(
            dest, media_type="image/png",
            headers={"X-Scene-Hash": full_hash, "X-Preview-Cached": "true",
                     "X-Missing-Count": str(missing),
                     "X-Assets-Total": str(len(items) + 1),
                     "X-Overlays-Total": str(len(overlay_rows)),
                     "X-Map-Count": str(map_count),
                     "X-Background-Color": bg_hex,
                     "X-World-Total": str(sum(1 for it in items if it.get("world_id")))} )

    # --- render ---
    # Fail fast LOUD when no TTF is available (never silent bitmap): probe
    # once before any text is drawn so missing-asset boxes, the beat tag,
    # and overlay plates all share the same fate.
    try:
        _probe_overlay_font()
    except FileNotFoundError as e:
        raise HTTPException(500, f"Overlay font missing (loud fallback): {e}")
    canvas = _Image.new("RGB", (_PRE_W, _PRE_H), bg_rgb)
    if place_path is not None:
        try:
            with _Image.open(place_path) as pim:
                pim = pim.convert("RGB")
                _paste_fit(canvas, pim, (0, 0, _PRE_W, _PRE_H))
        except Exception as e:
            _draw_labelled_box(
                canvas, (int(_PRE_W * 0.04), int(_PRE_H * 0.04),
                         int(_PRE_W * 0.92), int(_PRE_H * 0.92)),
                f"PLACE {place_ref or ''} {place_title or ''}".strip(),
                f"unreadable PNG: {type(e).__name__}"[:46])
            missing += 0  # already counted as present-path; keep honest box instead
    else:
        _draw_labelled_box(
            canvas, (int(_PRE_W * 0.04), int(_PRE_H * 0.04),
                     int(_PRE_W * 0.92), int(_PRE_H * 0.92)),
            f"PLACE {place_ref or '(none)'} {place_title or ''}".strip(),
            place_reason[:46] or "no file")

    for it in items:
        bw, bh = int(it["scale"] * _PRE_W), int(it["scale"] * _PRE_H)
        bx, by = int(it["x"] * _PRE_W), int(it["y"] * _PRE_H)
        # Clamp inside canvas (x/y already clamped as fractions; belt-and-braces).
        bx = min(max(bx, 0), _PRE_W - 1)
        by = min(max(by, 0), _PRE_H - 1)
        bw = min(bw, _PRE_W - bx)
        bh = min(bh, _PRE_H - by)
        # D9-T03 MT honesty: map rows NEVER paste a file and NEVER go blank —
        # always the labelled "map coming" box (even if a file ever lands).
        if it.get("is_map"):
            world_id = it.get("world_id") or "MT"
            world_text = (world_by_id.get(world_id, {}).get("text")
                          or it["need"].get("name") or "")
            _draw_map_coming_box(canvas, (bx, by, bw, bh), world_id, world_text)
            continue
        if it["path"] is not None:
            try:
                with _Image.open(it["path"]) as aim:
                    if aim.mode in ("RGBA", "LA", "P"):
                        aim = aim.convert("RGBA")
                    else:
                        aim = aim.convert("RGB")
                    _paste_fit(canvas, aim, (bx, by, bw, bh))
                continue
            except Exception as e:
                it["reason"] = f"unreadable PNG: {type(e).__name__}"[:46]
        _draw_labelled_box(canvas, (bx, by, bw, bh),
                           it["need"]["name"] or "asset", it["reason"])

    # Beat tag (top-left) so the PNG is traceable without its filename.
    # Uses the ONE shared TTF helper (never bitmap silently); top overlay
    # plates start below it (_OVERLAY_TOP_CLEAR) so both stay visible.
    try:
        tag_font = _overlay_font(28)
    except (FileNotFoundError, RuntimeError) as e:
        raise HTTPException(500, f"Overlay font missing (loud fallback): {e}")
    d = _Draw.Draw(canvas)
    tag = f"{beat_id} — {(scene.get('shot') or '')[:90]}"
    tb = d.textbbox((0, 0), tag, font=tag_font)
    pad = 8
    d.rectangle([10, 10, 10 + (tb[2] - tb[0]) + pad * 2,
                 10 + (tb[3] - tb[1]) + pad * 2], fill=(0, 0, 0))
    d.text((10 + pad, 10 + pad), tag, font=tag_font, fill=(255, 255, 255))

    # D9-T02 overlays on top of art, under nothing (beat tag already drawn
    # above is small; top plates clear it via _OVERLAY_TOP_CLEAR).
    try:
        _draw_overlays(canvas, overlay_rows)
    except (FileNotFoundError, RuntimeError) as e:
        raise HTTPException(500, f"Overlay font missing (loud fallback): {e}")

    canvas.save(dest, "PNG")
    return FileResponse(
        dest, media_type="image/png",
        headers={"X-Scene-Hash": full_hash, "X-Preview-Cached": "false",
                 "X-Missing-Count": str(missing),
                 "X-Assets-Total": str(len(items) + 1),
                 "X-Overlays-Total": str(len(overlay_rows)),
                 "X-Map-Count": str(map_count),
                 "X-Background-Color": bg_hex,
                 "X-World-Total": str(sum(1 for it in items if it.get("world_id")))})
