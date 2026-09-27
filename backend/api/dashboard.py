# backend/api/dashboard.py
"""One-call summary of where an episode stands.

Everything here is already stored somewhere (project.db, job_log, the stale
flags) - the point is to answer "what do I do next" without visiting every
stage to work it out.
"""
from fastapi import APIRouter, HTTPException

import hashlib
import json

from backend.db.connection import get_app_db, get_project_db
from backend.api.stale import stale_counts

router = APIRouter(tags=["dashboard"])

# Tables that carry project_id; the rest live in a per-project database.
_WITH_PID = {"characters", "environments", "world_records", "beats", "generations", "scripts", "library"}


async def _proj(project_id: str):
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id, stage, slug FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(row)


async def _n(proj_db, project_id: str, table: str, where: str = "") -> int:
    if table in _WITH_PID:
        sql, args = f"SELECT COUNT(*) c FROM {table} WHERE project_id=?{where}", (project_id,)
    else:
        sql, args = f"SELECT COUNT(*) c FROM {table} WHERE 1=1{where}", ()
    async with proj_db.execute(sql, args) as cur:
        return (await cur.fetchone())["c"]


@router.get("/projects/{project_id}/dashboard")
async def dashboard(project_id: str):
    proj = await _proj(project_id)
    folder = proj["folder_name"]
    proj_db = await get_project_db(folder)

    counts = {
        "characters": await _n(proj_db, project_id, "characters"),
        "variants": await _n(proj_db, project_id, "variants"),
        "environments": await _n(proj_db, project_id, "environments"),
        "world_records": await _n(proj_db, project_id, "world_records"),
        "beats": await _n(proj_db, project_id, "beats"),
        "generations": await _n(proj_db, project_id, "generations"),
        "sheets": await _n(proj_db, project_id, "sheets"),
    }

    lib_total = await _n(proj_db, project_id, "library")
    lib_ready = await _n(proj_db, project_id, "library", " AND status='ready'")

    async with proj_db.execute(
        "SELECT version, word_count FROM scripts WHERE project_id=? AND locked=1 "
        "ORDER BY id DESC LIMIT 1", (project_id,)) as cur:
        script = await cur.fetchone()
    await proj_db.close()

    stale = await stale_counts(project_id)
    stale_total = stale.get("total", 0)

    locked = script is not None
    script_words = script["word_count"] if script else 0
    script_version = script["version"] if script else None

    # What to do next, and where to do it.
    if not locked:
        next_action = {"label": "Write and lock a script", "screen": "script", "why": "Nothing downstream can run until the script is locked."}
    elif stale_total:
        next_action = {"label": f"Re-extract {stale_total} stale artifact{'s' if stale_total != 1 else ''}",
                       "screen": "cast", "action": "reextract",
                       "why": "The locked script changed, so these no longer match it."}
    elif not counts["characters"]:
        next_action = {"label": "Extract the cast", "screen": "cast", "why": "No characters found yet."}
    elif not counts["environments"]:
        next_action = {"label": "Extract locations", "screen": "locations", "why": "No locations found yet."}
    elif not counts["beats"]:
        next_action = {"label": "Cut the script into beats", "screen": "beats", "why": "Beats are the shots you will generate."}
    elif not counts["generations"]:
        next_action = {"label": "Compose shot prompts", "screen": "beats", "why": "No prompts built yet."}
    elif lib_ready < lib_total:
        next_action = {"label": f"Attach {lib_total - lib_ready} remaining asset{'s' if lib_total - lib_ready != 1 else ''}",
                       "screen": "library", "why": "Export waits until every library slot is ready."}
    else:
        next_action = {"label": "Export the episode package", "screen": "export", "why": "Everything is ready."}

    blockers = []
    if not locked:
        blockers.append({"label": "No locked script", "done": False})
    if stale_total:
        blockers.append({"label": f"{stale_total} stale artifacts not re-extracted", "done": False})
    if not counts["generations"]:
        blockers.append({"label": "Shot prompts not composed", "done": False})
    else:
        blockers.append({"label": f"{counts['generations']} shot prompts composed", "done": True})
    if lib_ready < lib_total:
        blockers.append({"label": f"{lib_ready} of {lib_total} assets ready", "done": False})
    else:
        blockers.append({"label": f"All {lib_total} assets ready", "done": True})

    return {
        "project_id": project_id,
        "slug": proj["slug"],
        "stage": proj["stage"],
        "script": {"locked": locked, "version": script_version, "words": script_words},
        "counts": counts,
        "library": {"total": lib_total, "ready": lib_ready},
        "stale": stale,
        "next_action": next_action,
        "blockers": blockers,
    }


# --- SCENES-MP4 ST-T01: one-call project status (runbook fuel, read-only). ---
# Aggregates what today takes six queries: beats, voice WAVs, scenes, assets,
# gens, overlays, plus the render gate and the latest render job. Composes
# existing queries only — no new logic, no writes (SELECTs + stat() checks;
# no INSERT/UPDATE/DELETE, no commit, no mkdir). Gate + job payload are reused
# from backend.api.render (render_gate / _latest_job_row / _job_status_payload)
# via deferred import so no import cycle can form. Unknown project 404s via
# _proj before any other work.
@router.get("/projects/{project_id}/status")
async def project_status(project_id: str):
    from pathlib import Path as _Path

    from backend.core.config import DATA_DIR as _DATA_DIR
    from backend.api import render as _render_api

    proj = await _proj(project_id)
    folder = proj["folder_name"]
    proj_db = await get_project_db(folder)
    try:
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM beats WHERE project_id=?", (project_id,)
        ) as cur:
            beats_total = (await cur.fetchone())["c"]
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM beats WHERE project_id=? AND stale=1",
            (project_id,),
        ) as cur:
            beats_stale = (await cur.fetchone())["c"]
        async with proj_db.execute(
            "SELECT id FROM beats WHERE project_id=? AND stale=1 ORDER BY sort_order",
            (project_id,),
        ) as cur:
            stale_beat_ids = [r["id"] for r in await cur.fetchall()]
        # Scenes are keyed by beat_id (no project_id) — scope via beats JOIN,
        # same shape as GET .../scenes (scenes.py::list_scenes).
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scenes s JOIN beats b ON b.id=s.beat_id "
            "WHERE b.project_id=?",
            (project_id,),
        ) as cur:
            scenes_total = (await cur.fetchone())["c"]
        # Assets: matched = library_ref set / pending = needs_generate set
        # (P1-T06 XOR invariant) — same scope shape as GET .../scenes/assets.
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scene_assets sa JOIN beats b ON b.id=sa.beat_id "
            "WHERE b.project_id=?",
            (project_id,),
        ) as cur:
            assets_total = (await cur.fetchone())["c"]
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scene_assets sa JOIN beats b ON b.id=sa.beat_id "
            "WHERE b.project_id=? AND sa.library_ref IS NOT NULL",
            (project_id,),
        ) as cur:
            assets_matched = (await cur.fetchone())["c"]
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scene_assets sa JOIN beats b ON b.id=sa.beat_id "
            "WHERE b.project_id=? AND sa.needs_generate=1",
            (project_id,),
        ) as cur:
            assets_pending = (await cur.fetchone())["c"]
        # Gens carry project_id — same filter as GET .../generations.
        async with proj_db.execute(
            "SELECT status, COUNT(*) c FROM generations WHERE project_id=? "
            "GROUP BY status",
            (project_id,),
        ) as cur:
            gen_rows = [dict(r) for r in await cur.fetchall()]
        # Overlays scoped via beats JOIN, same shape as GET .../scenes/overlays.
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scene_overlays so JOIN beats b ON b.id=so.beat_id "
            "WHERE b.project_id=?",
            (project_id,),
        ) as cur:
            overlays_total = (await cur.fetchone())["c"]
        # Voice WAV presence uses the same vo_dir layout render_gate reads
        # (08_export/voiceover/<beat>.wav); non-empty file + measured duration.
        async with proj_db.execute(
            "SELECT id, duration_sec FROM beats WHERE project_id=? AND stale=0 "
            "ORDER BY sort_order",
            (project_id,),
        ) as cur:
            fresh_beats = [dict(r) for r in await cur.fetchall()]
        latest_job = await _render_api._latest_job_row(proj_db, project_id)
    finally:
        await proj_db.close()

    vo_dir = _Path(_DATA_DIR) / "projects" / folder / "08_export" / "voiceover"
    voice_missing: list[str] = []
    for b in fresh_beats:
        wav = vo_dir / f"{b['id']}.wav"
        try:
            ok_file = wav.is_file() and wav.stat().st_size > 0
        except OSError:
            ok_file = False
        try:
            ok_dur = b.get("duration_sec") is not None and float(b["duration_sec"]) > 0
        except (TypeError, ValueError):
            ok_dur = False
        if not (ok_file and ok_dur):
            voice_missing.append(b["id"])
    voice_present = len(fresh_beats) - len(voice_missing)

    # Gate is the shared check (pure read) — blocker lists included verbatim.
    gate = await _render_api.render_gate(project_id)

    task = _render_api._TASKS.get(project_id)
    alive = task is not None and not task.done()
    job_payload = _render_api._job_status_payload(latest_job, alive)

    gens_by_status = {r["status"]: int(r["c"]) for r in gen_rows}
    gens_total = sum(gens_by_status.values())

    return {
        "project_id": project_id,
        "beats": {
            "total": beats_total,
            "fresh": len(fresh_beats),
            "stale": beats_stale,
            "stale_ids": stale_beat_ids,
        },
        "voice": {
            "present": voice_present,
            "missing": len(voice_missing),
            "missing_ids": voice_missing,
        },
        "scenes": {
            "total": scenes_total,
            "approved": gate["approved"],
            "unapproved": len(gate["unapproved"]),
            "unapproved_ids": gate["unapproved"],
            "stale": len(gate["stale_scenes"]),
            "stale_ids": gate["stale_scenes"],
        },
        "assets": {
            "total": assets_total,
            "matched": assets_matched,
            "pending": assets_pending,
        },
        "gens": {"total": gens_total, "by_status": gens_by_status},
        "overlays": {"total": overlays_total},
        "gate": gate,
        "render_job": job_payload,
    }


# --- SCENES-MP4 I-T02: cast consistency check (report-only, never blocks). ---
# GET /projects/{project_id}/cast-consistency: per character across beats,
# palette hash + silhouette hash of approved PNGs; outliers listed with
# distances. No AI, no writes (SELECTs + PNG file reads only — no
# INSERT/UPDATE/DELETE, no commit, no mkdir). Nothing else reads this output
# (the render gate never consults it), so it can never block
# planning/approval/render — it only REPORTS drift for a human to fix
# (recolor in I-T03, or regenerate). Unknown project 404s via _proj first.
#
# Identity rule (owner catch): draw calls now carry the locked appearance
# text (I-T01), but drift can still creep across beats. This endpoint hashes
# what actually got approved so cousins get spotted.
#
# Need->character mapping uses the same discipline as scenes._entry_matches
# (exact -> substring len>=4 -> sig-token subset -> >=2 token overlap).
# Local copy here (generation.py I-T01 precedent) keeps dashboard.py
# self-contained — I-T03 works in generation.py in parallel, no merge
# friction. Characters are stale=0 rows (same scope as I-T01 identity).
#
# Hashes (Pillow only, no new deps):
#   palette: 64-bin RGB histogram (4 levels/channel) over the OPAQUE pixels
#     of a 64x36 thumb (transparent SVG exports must not let clear pixels
#     vote); hash = sha256 of packed bins, 16 hex.
#   silhouette: 32x32 foreground mask — alpha when the PNG carries real
#     transparency, else pixels >48 (euclidean RGB) from the corner-median
#     background (opaque Inkscape exports carry no alpha shape); hash =
#     sha256 of mask bits, 16 hex.
# Outlier = combined distance to the character centroid
#   (0.5 * palette-euclidean + 0.5 * silhouette-meanabs). Flagged only with
#   >=3 readable approved PNGs AND distance > 0.35. Byte-identical copies sit
#   at 0.0 and stay silent; a deliberately-off asset lands farthest.

_CAST_MIN_ASSETS = 3
_CAST_OUTLIER_THRESHOLD = 0.35
_CAST_PALETTE_W = 0.5
_CAST_SIL_W = 0.5
_CAST_PAL_W, _CAST_PAL_H = 64, 36
_CAST_SIL_SIZE = 32
_CAST_BG_DIST = 48.0

_CAST_STOPWORDS = frozenset(
    "a an the of and or in on at to for with from by as is are was were be been "
    "this that these those its it s".split()
)


def _cast_norm(s: str) -> str:
    import re as _re

    return _re.sub(r"[^\w]+", " ", (s or "").lower(), flags=_re.UNICODE).strip()


def _cast_sig_tokens(s: str) -> list[str]:
    return [t for t in _cast_norm(s).split() if t not in _CAST_STOPWORDS and len(t) > 1]


def _cast_entry_matches(need_name: str, search_query: str, candidate: str) -> bool:
    """Same discipline as scenes._entry_matches (canonical) — local copy."""
    n_name, n_query, n_cand = (
        _cast_norm(need_name), _cast_norm(search_query), _cast_norm(candidate))
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
    for sig in (_cast_sig_tokens(need_name), _cast_sig_tokens(search_query)):
        if sig and set(sig) <= t_cand:
            return True
    need_toks = set(_cast_sig_tokens(need_name)) | set(_cast_sig_tokens(search_query))
    if len(need_toks & t_cand) >= 2:
        return True
    return False


def _cast_hash_png(path):
    """Hash one approved PNG.

    Returns (palette_hash, silhouette_hash, palette_vec, silhouette_vec).
    Raises OSError when the file is missing/unreadable — the caller marks
    that asset unreadable and continues (report-only never crashes the
    whole check). PIL's UnidentifiedImageError subclasses OSError.
    """
    from PIL import Image as _Image

    with _Image.open(path) as im:
        rgba = im.convert("RGBA")
        thumb = rgba.resize((_CAST_PAL_W, _CAST_PAL_H), _Image.BILINEAR)
        raw = thumb.tobytes()
        bins = [0] * 64
        opaque = 0
        for i in range(0, len(raw), 4):
            if raw[i + 3] < 128:
                continue
            bins[(min(raw[i] // 64, 3) * 16)
                 + (min(raw[i + 1] // 64, 3) * 4)
                 + min(raw[i + 2] // 64, 3)] += 1
            opaque += 1
        if opaque:
            palette_vec = [c / opaque for c in bins]
        else:
            palette_vec = [0.0] * 64
        pal_pack = b"".join(int(v * 1000000).to_bytes(4, "big") for v in palette_vec)
        palette_hash = hashlib.sha256(pal_pack).hexdigest()[:16]
        small = rgba.resize((_CAST_SIL_SIZE, _CAST_SIL_SIZE), _Image.BILINEAR)
        sraw = small.tobytes()
        px = [(sraw[i], sraw[i + 1], sraw[i + 2], sraw[i + 3])
              for i in range(0, len(sraw), 4)]
        alphas = [p[3] for p in px]
        transparent = sum(1 for a in alphas if a < 128)
        if 0 < transparent < len(px):
            sil_vec = [1.0 if a >= 128 else 0.0 for a in alphas]
        else:
            n = _CAST_SIL_SIZE
            corners = [px[0], px[n - 1], px[(n - 1) * n], px[n * n - 1]]
            br = sum(c[0] for c in corners) / 4.0
            bg = sum(c[1] for c in corners) / 4.0
            bb = sum(c[2] for c in corners) / 4.0
            sil_vec = []
            for r, g, b, _a in px:
                d = ((r - br) ** 2 + (g - bg) ** 2 + (b - bb) ** 2) ** 0.5
                sil_vec.append(1.0 if d > _CAST_BG_DIST else 0.0)
        sil_pack = bytes(1 if v >= 0.5 else 0 for v in sil_vec)
        silhouette_hash = hashlib.sha256(sil_pack).hexdigest()[:16]
    return palette_hash, silhouette_hash, palette_vec, sil_vec


def _cast_centroid(vecs: list[list[float]]) -> list[float]:
    dim = len(vecs[0])
    return [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]


def _cast_combined(palette_vec, sil_vec, centroid_pal, centroid_sil):
    """Component + combined distances of one asset to its cast centroid."""
    import math as _math

    pal_d = _math.sqrt(sum((a - b) ** 2 for a, b in zip(palette_vec, centroid_pal)))
    sil_d = sum(abs(a - b) for a, b in zip(sil_vec, centroid_sil)) / len(sil_vec)
    return pal_d, sil_d, _CAST_PALETTE_W * pal_d + _CAST_SIL_W * sil_d


@router.get("/projects/{project_id}/cast-consistency")
async def cast_consistency(project_id: str):
    from pathlib import Path as _Path

    from backend.core.config import DATA_DIR as _DATA_DIR

    proj = await _proj(project_id)
    folder = proj["folder_name"]
    proj_db = await get_project_db(folder)
    try:
        async with proj_db.execute(
            "SELECT id, names FROM characters WHERE project_id=? AND stale=0 ORDER BY id",
            (project_id,),
        ) as cur:
            characters = [dict(r) for r in await cur.fetchall()]
        # Approved PNGs behind character needs: svg lane (file_path = P2-T06
        # raster) plus any fetched/uploaded lane once approved — anything with
        # an approved/final PNG on its row counts. Pending/generated rows are
        # not yet judged, so they never vote.
        async with proj_db.execute(
            "SELECT sa.beat_id AS beat_id, sa.name AS need_name, "
            "sa.search_query AS search_query, g.id AS gen_id, g.title AS title, "
            "g.file_path AS file_path, g.status AS status "
            "FROM scene_assets sa JOIN generations g ON g.id=sa.generation_id "
            "WHERE sa.kind='character' AND sa.generation_id IS NOT NULL "
            "AND g.project_id=? AND g.status IN ('approved','final') "
            "AND g.file_path IS NOT NULL AND g.file_path != '' "
            "AND sa.beat_id IN (SELECT id FROM beats WHERE project_id=?) "
            "ORDER BY sa.beat_id, g.id",
            (project_id, project_id),
        ) as cur:
            approved = [dict(r) for r in await cur.fetchall()]
        async with proj_db.execute(
            "SELECT COUNT(*) c FROM scene_assets WHERE kind='character' "
            "AND beat_id IN (SELECT id FROM beats WHERE project_id=?)",
            (project_id,),
        ) as cur:
            char_needs_total = (await cur.fetchone())["c"]
    finally:
        await proj_db.close()

    base = _Path(_DATA_DIR) / "projects" / folder
    out_chars: list[dict] = []
    used_gen_ids: set[int] = set()
    for ch in characters:
        try:
            aliases = json.loads(ch.get("names") or "[]")
        except Exception:
            aliases = []
        if not isinstance(aliases, list):
            aliases = [aliases]
        aliases = [str(a or "").strip() for a in aliases if str(a or "").strip()]
        display = aliases[0] if aliases else ch["id"]
        matched = [
            a for a in approved
            if any(_cast_entry_matches(a["need_name"] or "", a["search_query"] or "", alias)
                   for alias in aliases)
        ]
        assets: list[dict] = []
        for a in matched:
            entry: dict = {
                "gen_id": a["gen_id"],
                "beat_id": a["beat_id"],
                "title": a["title"],
                "file_path": a["file_path"],
                "status": a["status"],
            }
            try:
                ph, sh, pv, sv = _cast_hash_png(base / (a["file_path"] or ""))
            except OSError:
                entry.update(palette_hash="", silhouette_hash="", readable=False,
                             palette_distance=0.0, silhouette_distance=0.0,
                             distance=0.0, outlier=False)
                assets.append(entry)
                continue
            entry.update(palette_hash=ph, silhouette_hash=sh, readable=True)
            entry["_pv"], entry["_sv"] = pv, sv
            assets.append(entry)
        readable = [e for e in assets if e["readable"]]
        if len(readable) >= 2:
            cpal = _cast_centroid([e["_pv"] for e in readable])
            csil = _cast_centroid([e["_sv"] for e in readable])
            for e in readable:
                pal_d, sil_d, combo = _cast_combined(e["_pv"], e["_sv"], cpal, csil)
                e["palette_distance"] = round(pal_d, 4)
                e["silhouette_distance"] = round(sil_d, 4)
                e["distance"] = round(combo, 4)
        else:
            for e in readable:
                e["palette_distance"] = 0.0
                e["silhouette_distance"] = 0.0
                e["distance"] = 0.0
        outliers: list[dict] = []
        note = ""
        if len(readable) >= _CAST_MIN_ASSETS:
            for e in sorted(readable, key=lambda x: x["distance"], reverse=True):
                if e["distance"] > _CAST_OUTLIER_THRESHOLD:
                    outliers.append({
                        "gen_id": e["gen_id"],
                        "beat_id": e["beat_id"],
                        "title": e["title"],
                        "file_path": e["file_path"],
                        "palette_hash": e["palette_hash"],
                        "silhouette_hash": e["silhouette_hash"],
                        "palette_distance": e["palette_distance"],
                        "silhouette_distance": e["silhouette_distance"],
                        "distance": e["distance"],
                    })
        elif readable:
            note = (f"needs >={_CAST_MIN_ASSETS} readable approved PNGs for outlier "
                    f"flags (has {len(readable)})")
        else:
            note = "no readable approved PNGs for this character yet"
        flagged = {o["gen_id"] for o in outliers}
        for e in assets:
            e.pop("_pv", None)
            e.pop("_sv", None)
            e["outlier"] = e["gen_id"] in flagged
        out_chars.append({
            "character_id": ch["id"],
            "name": display,
            "asset_count": len(assets),
            "readable_count": len(readable),
            "assets": assets,
            "outliers": outliers,
            "outlier_count": len(outliers),
            "note": note,
        })
        used_gen_ids.update(a["gen_id"] for a in matched)

    unmatched = [
        {"gen_id": a["gen_id"], "beat_id": a["beat_id"], "name": a["need_name"],
         "title": a["title"], "file_path": a["file_path"]}
        for a in approved if a["gen_id"] not in used_gen_ids
    ]
    total_outliers = sum(c["outlier_count"] for c in out_chars)
    return {
        "project_id": project_id,
        "report_only": True,
        "blocks": [],
        "method": {
            "palette": "64-bin RGB histogram over opaque pixels (16 hex sha256)",
            "silhouette": "32x32 foreground mask, alpha-or-background-subtracted (16 hex sha256)",
            "distance": f"{_CAST_PALETTE_W}*palette-euclidean + {_CAST_SIL_W}*silhouette-meanabs to centroid",
            "min_assets": _CAST_MIN_ASSETS,
            "threshold": _CAST_OUTLIER_THRESHOLD,
        },
        "characters": out_chars,
        "summary": {
            "characters": len(out_chars),
            "character_needs": char_needs_total,
            "approved_assets": len(approved),
            "readable_assets": sum(c["readable_count"] for c in out_chars),
            "outliers": total_outliers,
            "unmatched_approved": len(unmatched),
        },
        "unmatched_approved": unmatched,
    }
