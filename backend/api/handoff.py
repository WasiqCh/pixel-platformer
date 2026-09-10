# backend/api/handoff.py
from datetime import datetime, timezone
import json

from fastapi import APIRouter, HTTPException

from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir
from backend.core.composer import classify_overlay, clean_text


router = APIRouter(tags=["handoff"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _get_proj_info(project_id: str):
    db = await get_app_db()
    async with db.execute("SELECT * FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404, "Project not found")
    r = dict(row)
    folder, ch_id = r["folder_name"], r["channel_id"]
    async with db.execute("SELECT descriptor FROM channels WHERE id=?", (ch_id,)) as cur:
        ch = await cur.fetchone()
    await db.close()
    descriptor = (ch["descriptor"] if ch and ch["descriptor"]
                  else "clean flat 2D animation, bold outlines, limited palette")
    return folder, ch_id, (r.get("name") or folder), descriptor


def _resolve(ref, lib_by_ref, char_titles, env_titles):
    lib = lib_by_ref.get(ref)
    return {
        "asset_ref": ref,
        "title": char_titles.get(ref) or env_titles.get(ref) or (lib["title"] if lib else ref),
        "status": lib["status"] if lib else "missing",
        "file_path": (lib["file_path"] or None) if lib else None,
    }


def _summary(pkg):
    unique = {}
    for b in pkg["beats"]:
        for a in b["assets"]:
            unique[a["asset_ref"]] = a
    ready = sum(1 for a in unique.values() if a["status"] == "ready")
    return {
        "built_at": pkg["built_at"], "project": pkg["project"],
        "beats": len(pkg["beats"]), "duration_sec": pkg["stats"]["duration_sec"],
        "cast": len(pkg["cast"]), "environments": len(pkg["environments"]),
        "world": len(pkg["world"]),
        "assets_ready": ready, "assets_total": len(unique),
        "missing": [{"asset_ref": a["asset_ref"], "title": a["title"]}
                    for a in unique.values() if a["status"] != "ready"],
        "files": pkg["files"],
    }


@router.post("/projects/{project_id}/handoff/build")
async def build_handoff(project_id: str):
    folder, ch_id, pname, descriptor = await _get_proj_info(project_id)
    proj_db = await get_project_db(folder)

    async with proj_db.execute(
        "SELECT * FROM scripts WHERE project_id=? AND locked=1 ORDER BY id DESC LIMIT 1", (project_id,)) as cur:
        script = await cur.fetchone()
    if not script:
        await proj_db.close()
        raise HTTPException(400, "Lock a script first.")
    script = dict(script)

    async with proj_db.execute("SELECT * FROM beats WHERE project_id=? AND stale=0 ORDER BY sort_order", (project_id,)) as cur:
        beats = [dict(b) for b in await cur.fetchall()]
    for b in beats:
        async with proj_db.execute("SELECT * FROM beat_elements WHERE beat_id=? ORDER BY sort_order", (b["id"],)) as cur:
            b["elements"] = [dict(e) for e in await cur.fetchall()]

    async with proj_db.execute("SELECT * FROM library WHERE project_id=?", (project_id,)) as cur:
        lib_rows = [dict(r) for r in await cur.fetchall()]
    lib_by_ref = {r["asset_ref"]: r for r in lib_rows if r["asset_ref"]}

    async with proj_db.execute(
        "SELECT id, names, appearance, kind, significance, render, green_conflict FROM characters WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        chars = [dict(c) for c in await cur.fetchall()]
    for c in chars:
        c["names"] = json.loads(c["names"])
        async with proj_db.execute("SELECT id, span, delta FROM variants WHERE character_id=? ORDER BY id", (c["id"],)) as cur:
            c["variants"] = [dict(v) for v in await cur.fetchall()]
    char_titles = {c["id"]: c["names"][0] for c in chars}

    async with proj_db.execute("SELECT * FROM environments WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        envs = [dict(e) for e in await cur.fetchall()]
    for e in envs:
        e["elements"] = json.loads(e["elements"] or "[]")
    env_titles = {e["id"]: e["name"] for e in envs}

    async with proj_db.execute("SELECT * FROM world_records WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        worlds = [dict(w) for w in await cur.fetchall()]
    await proj_db.close()

    total_dur = 0.0
    clock = 0.0
    pkg_beats = []
    for b in beats:
        total_dur += b["duration_sec"]
        assets = []
        for el in b["elements"]:
            r = _resolve(el["asset_ref"], lib_by_ref, char_titles, env_titles)
            r["layer"] = el["layer"]
            r["framing"] = el["framing"]
            assets.append(r)
        graphics = []
        if b["overlay_text"]:
            otext = clean_text(b["overlay_text"])
            graphics.append({"text": otext,
                             "type": classify_overlay(otext),
                             "in_point_sec": round(clock, 1),
                             "duration_sec": b["duration_sec"]})
        pkg_beats.append({
            "id": b["id"], "section": b["chunk_id"], "text": b["text"], "svo": b["svo"],
            "overlay_text": b["overlay_text"], "text_only": bool(b["text_only"]),
            "duration_sec": b["duration_sec"], "in_point_sec": round(clock, 1),
            "graphics_layer": graphics, "assets": assets,
        })
        clock += b["duration_sec"]

    pkg = {
        "project": pname, "project_id": project_id, "channel_id": ch_id,
        "style_kit": descriptor, "built_at": _now(),
        "script": {"version": script["version"], "word_count": script["word_count"],
                   "duration_sec": script["duration_sec"]},
        "stats": {"beats": len(pkg_beats), "duration_sec": total_dur},
        "beats": pkg_beats, "cast": chars, "environments": envs, "world": worlds,
        "files": ["09_handoff/episode_package.json", "09_handoff/episode_package.md"],
    }

    hand_dir = get_project_dir(ch_id, folder.split("_")[1]) / "09_handoff"
    hand_dir.mkdir(parents=True, exist_ok=True)
    (hand_dir / "episode_package.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- human-readable markdown ----
    L = [f"# EPISODE PACKAGE — {pname}", f"Built: {pkg['built_at']}",
         f"STYLE KIT: {descriptor}",
         f"SCRIPT: v{script['version']} · {script['word_count']} words · ~{round(script['duration_sec'] / 60, 1)} min",
         f"BEATS: {len(pkg_beats)} · ~{round(total_dur / 60, 1)} min", "", "## BEATS", ""]
    cur_sec = None
    for b in pkg_beats:
        if b["section"] != cur_sec:
            cur_sec = b["section"]
            L += [f"### {cur_sec}", ""]
        tags = []
        for a in b["assets"]:
            mark = "✅" if a["status"] == "ready" else "❌"
            tags.append(f"{a['asset_ref']}({a['layer']}/{a['framing']}){mark}")
        extra = " · TEXT-ONLY" if b["text_only"] else ""
        ov = f" · 🏷 {b['overlay_text']}" if b["overlay_text"] else ""
        L.append(f"- {b['id']} [{b['duration_sec']:.1f}s]{extra}{ov} \"{b['text']}\"")
        L.append(f"  svo: {b['svo']}" + (f" · assets: {', '.join(tags)}" if tags else ""))
    L += ["", "## CAST", ""]
    for c in chars:
        g = " · 🟢" if c["green_conflict"] else ""
        L.append(f"- {c['id']} {c['names'][0]} ({c['kind']}·{c['significance']}·{c['render']}){g} — {len(c['variants'])} variant(s)")
    L += ["", "## ENVIRONMENTS", ""]
    for e in envs:
        g = " · 🟢" if e["green_conflict"] else ""
        L.append(f"- {e['id']} {e['name']}{g}")
    L += ["", "## WORLD / REAL ASSETS", ""]
    for w in worlds:
        prov = f" · provenance: {w['provenance']}" if w["provenance"] else ""
        L.append(f"- {w['id']} [{w['type']}] {w['text']} ({w['status']}){prov}")
    (hand_dir / "episode_package.md").write_text("\n".join(L), encoding="utf-8")

    return _summary(pkg)


@router.get("/projects/{project_id}/handoff")
async def get_handoff(project_id: str):
    folder, ch_id, pname, descriptor = await _get_proj_info(project_id)
    p = get_project_dir(ch_id, folder.split("_")[1]) / "09_handoff" / "episode_package.json"
    if not p.exists():
        return {"package": None}
    return {"package": _summary(json.loads(p.read_text(encoding="utf-8")))}


@router.post("/projects/{project_id}/handoff/signoff")
async def signoff(project_id: str):
    from backend.api.checkpoint import checkpoint as run_checkpoint
    data = await run_checkpoint(project_id)
    if not data["can_advance"]:
        raise HTTPException(400, "Checkpoint gates failing — pass ✅ Checkpoint and Advance before sign-off.")

    folder, ch_id, pname, descriptor = await _get_proj_info(project_id)
    now = _now()
    hand_dir = get_project_dir(ch_id, folder.split("_")[1]) / "09_handoff"
    hand_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# HANDOFF — {pname}",
        f"Signed off: {now}",
        "Stage: handed_off",
        f"STYLE KIT: {descriptor}",
        "",
        "## Definition-of-Done at sign-off",
    ]
    for c in data["checks"]:
        mark = "✅" if c["ok"] else ("❌" if c["required"] else "⚠️")
        lines.append(f"- {mark} {c['label']} — {c['detail']}")
    lines += [
        "",
        "## Delivered files",
        "- 03_script/locked_v*.md — locked script versions",
        "- 04_cast/characters.md · mentions.md · variants.md",
        "- 05_world/environments.md · world_records.md",
        "- 06_assets/characters/*_sheet.md · environments/*_sheet.md · library/",
        "- 07_beats/beats.md",
        "- 09_handoff/episode_package.json · episode_package.md · HANDOFF.md",
        "",
        "This episode is ready for animation / render.",
        "The episode_package is the integration point for any render tool.",
    ]
    md = "\n".join(lines)
    (hand_dir / "HANDOFF.md").write_text(md, encoding="utf-8")

    db = await get_app_db()
    await db.execute("UPDATE projects SET stage='handed_off', updated_at=? WHERE id=?", (now, project_id))
    await db.commit()
    await db.close()
    return {"stage": "handed_off", "handoff_md": md}


@router.get("/projects/{project_id}/handoff/status")
async def handoff_status(project_id: str):
    db = await get_app_db()
    async with db.execute("SELECT stage FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    folder, ch_id, pname, descriptor = await _get_proj_info(project_id)
    p = get_project_dir(ch_id, folder.split("_")[1]) / "09_handoff" / "HANDOFF.md"
    return {
        "stage": (row["stage"] if row and row["stage"] else "script"),
        "signed": p.exists(),
        "handoff_md": p.read_text(encoding="utf-8") if p.exists() else None,
    }

