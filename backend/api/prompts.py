# backend/api/prompts.py
from datetime import datetime, timezone
from typing import Optional
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.composer import (clean_text, classify_overlay, pacing_flags, parse_directives,
    split_note, base_class, variant_for, master_prompt_env, master_prompt_map,
    master_prompt_insert, master_prompt_world_plate, pose_prompt)
from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir

# Sprite-sheet layout constants now live in one place (backend/core/sheet_layout.py).
# They used to be copy-pasted here and in sheets.py, which let the sheet builder
# and the prompt composer disagree on sheet numbering.
from backend.core.sheet_layout import CHAR_ACTIONS_PER_SHEET, CHAR_CELLS

router = APIRouter(tags=["prompts"])


class NoteUpdate(BaseModel):
    editor_note: Optional[str] = None
    improv_note: Optional[str] = None


async def _proj(project_id):
    db = await get_app_db()
    async with db.execute("SELECT * FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404, "Project not found")
    r = dict(row)
    async with db.execute("SELECT descriptor FROM channels WHERE id=?", (r["channel_id"],)) as cur:
        ch = await cur.fetchone()
    await db.close()
    desc = (ch["descriptor"] if ch and ch["descriptor"]
            else "clean flat 2D animation, bold outlines, limited palette")
    return r["folder_name"], r["channel_id"], desc


async def _compose_all(project_id, update_db, write):
    folder, ch_id, descriptor = await _proj(project_id)
    proj_db = await get_project_db(folder)

    async with proj_db.execute("SELECT * FROM beats WHERE project_id=? AND stale=0 ORDER BY sort_order", (project_id,)) as cur:
        beats = [dict(b) for b in await cur.fetchall()]
    for b in beats:
        async with proj_db.execute("SELECT * FROM beat_elements WHERE beat_id=? ORDER BY sort_order", (b["id"],)) as cur:
            b["elements"] = [dict(e) for e in await cur.fetchall()]

    async with proj_db.execute("SELECT id, names, appearance FROM characters WHERE project_id=? AND stale=0", (project_id,)) as cur:
        chars = {r["id"]: {"name": json.loads(r["names"])[0], "appearance": r["appearance"]} for r in await cur.fetchall()}
    for cid in chars:
        async with proj_db.execute("SELECT * FROM variants WHERE character_id=? ORDER BY id", (cid,)) as cur:
            chars[cid]["variants"] = [dict(v) for v in await cur.fetchall()]
    async with proj_db.execute("SELECT id, name, elements, green_conflict FROM environments WHERE project_id=? AND stale=0", (project_id,)) as cur:
        envs = {r["id"]: dict(r) for r in await cur.fetchall()}
    for e in envs.values():
        e["elements"] = json.loads(e["elements"] or "[]")
    async with proj_db.execute("SELECT * FROM world_records WHERE project_id=? AND stale=0", (project_id,)) as cur:
        worlds = {r["id"]: dict(r) for r in await cur.fetchall()}
    async with proj_db.execute("SELECT asset_ref, status, file_path FROM library WHERE project_id=?", (project_id,)) as cur:
        lib = {r["asset_ref"]: (r["status"], r["file_path"]) for r in await cur.fetchall() if r["asset_ref"]}

    cleaned = 0
    for b in beats:
        fixed = clean_text(b["overlay_text"])
        if fixed != b["overlay_text"]:
            b["overlay_text"] = fixed
            cleaned += 1
        if b["overlay_text"]:
            b["overlay_spec"] = classify_overlay(b["overlay_text"])
            if update_db:
                await proj_db.execute("UPDATE beats SET overlay_text=?, overlay_spec=? WHERE id=?",
                                      (b["overlay_text"], b["overlay_spec"], b["id"]))

    def ref_info(ref):
        st, fp = lib.get(ref, ("", ""))
        return (fp if st == "ready" else "")

    def ref_line(ref):
        fp = ref_info(ref)
        if fp:
            return fp
        if ref.startswith("C"):
            return f"06_assets/characters/{ref}_sheet.md"
        if ref.startswith("E"):
            return f"06_assets/environments/{ref}_sheet.md"
        return "master generation pending"

    # Environment sheet numbers (one per environment, ordered by id)
    env_sheet_num = {ref: i + 1 for i, ref in enumerate(sorted(envs.keys()))}

    # Character action counters: track how many poses generated per character
    # to assign sheet.action numbers (1.1, 1.2... 2.1, 2.2...)
    char_action_counter = {cid: 0 for cid in chars}

    # master prompts per static asset
    masters = {}
    def master_for(ref):
        if ref in masters:
            return masters[ref]
        if ref.startswith("E"):
            e = envs.get(ref)
            # Include environment sheet number
            env_num = env_sheet_num.get(ref, 1)
            base = master_prompt_env(descriptor, e["name"], e["elements"], e["green_conflict"]) if e else f"{descriptor} Environment plate."
            p = f"{base} [E{env_num}]"
        elif ref.startswith("MT"):
            w = worlds.get(ref, {})
            p = master_prompt_map(descriptor, w.get("text", ref), w.get("map_template"), w.get("era_hint"))
        else:
            w = worlds.get(ref, {})
            layers = {el["layer"] for b in beats for el in b["elements"] if el["asset_ref"] == ref}
            if layers == {"background"} or "background" in layers:
                p = master_prompt_world_plate(descriptor, w.get("text", ref), w.get("era_hint"))
            else:
                p = master_prompt_insert(descriptor, w.get("text", ref), w.get("era_hint"), "")
        masters[ref] = p
        return p

    generations = []
    scenes = []
    counts = {"dynamic": 0, "static_rows": 0, "skipped": 0}
    master_seq = 0
    pose_seq = 0
    seen_master = set()
    clock = 0.0
    last_plate_a = None

    for b in beats:
        bgs = [el for el in b["elements"] if el["layer"] == "background"]
        plate_a = bgs[0]["asset_ref"] if len(bgs) >= 1 else None
        plate_b = bgs[1]["asset_ref"] if len(bgs) >= 2 else None
        inherited = False
        if not plate_a:
            plate_a = last_plate_a
            inherited = True
        else:
            last_plate_a = plate_a
        warnings = []
        if len(bgs) > 2:
            warnings.append(f"{len(bgs)} backgrounds — extra plates ignored, review manually")

        scene = {"beat_id": b["id"], "section": b["chunk_id"], "in_point": round(clock, 1),
                 "duration_sec": b["duration_sec"], "text_only": bool(b["text_only"]),
                 "overlay": None, "plate_a": plate_a, "plate_b": plate_b,
                 "plate_inherited": inherited, "mid_actors": [], "mid_plates": [],
                 "inserts": [], "flags": pacing_flags(b["duration_sec"]), "warnings": warnings}
        if b["overlay_text"]:
            scene["overlay"] = {"text": b["overlay_text"], "type": classify_overlay(b["overlay_text"]),
                                "in_point": round(clock, 1), "duration_sec": b["duration_sec"]}
        clock += b["duration_sec"]

        for el in b["elements"]:
            ref, layer = el["asset_ref"], el["layer"]
            directives = parse_directives(el["improv_note"])
            if "lock" in directives:
                counts["skipped"] += 1
                continue
            cls = base_class(ref, layer)
            if "static" in directives:
                cls = "static"
            if "dynamic" in directives:
                cls = "dynamic"
            diegetic, director = split_note(el["editor_note"])

            if cls == "static":
                prompt = master_for(ref)
                if ref.startswith("E") and layer == "midground":
                    prompt += f" Crop framing: {el['framing']}."
                if ref not in seen_master:
                    seen_master.add(ref)
                    master_seq += 1
                    generations.append({"gen_id": f"M{master_seq:02d}", "kind": "master", "asset_ref": ref,
                                        "beat_id": None, "title": ref, "prompt": prompt, "refs": ref_info(ref)})
                counts["static_rows"] += 1
            else:
                ch = chars.get(ref)
                name = ch["name"] if ch else ref
                var = variant_for(ch["variants"], b["text"], b["chunk_text"]) if ch else None
                identity = (var["delta"] if var else (ch["appearance"] if ch else "as described in script"))
                snip = " ".join(b["text"].split()[:12])
                
                # Increment action counter for this asset.
                # Counter is seeded from characters only, but world records
                # (RW*/MT*) can also be classified dynamic -> use .get() so
                # non-character assets don't raise KeyError.
                char_action_counter[ref] = char_action_counter.get(ref, 0) + 1
                action_idx = char_action_counter[ref]
                sheet_num = ((action_idx - 1) // CHAR_ACTIONS_PER_SHEET) + 1
                action_num = ((action_idx - 1) % CHAR_ACTIONS_PER_SHEET) + 1
                sheet_action = f"{sheet_num}.{action_num}"
                
                # Get environment sheet number for this beat (first background)
                env_num = ""
                if bgs:
                    env_num = f"E{env_sheet_num.get(bgs[0]['asset_ref'], 1)}"
                
                # Build prompt with sheet/action numbering
                base_prompt = pose_prompt(descriptor, name, identity, b["svo"], snip, el["framing"], diegetic, director)
                tag = f" [E{env_sheet_num.get(bgs[0]['asset_ref'], 1) if bgs else 1}, C{sheet_action}]"
                prompt = base_prompt + tag
                
                pose_seq += 1
                generations.append({"gen_id": f"P{pose_seq:02d}", "kind": "pose", "asset_ref": ref,
                                    "beat_id": b["id"], "title": f"{b['id']}/{ref}", "prompt": prompt,
                                    "refs": ref_info(ref)})
                counts["dynamic"] += 1

            if update_db:
                await proj_db.execute("UPDATE beat_elements SET prompt_text=?, refs_to_attach=? WHERE id=?",
                                      (prompt, ref_info(ref), el["id"]))
            el["prompt_text"] = prompt

            if layer == "midground" and cls == "dynamic":
                scene["mid_actors"].append(ref)
            elif layer == "midground":
                scene["mid_plates"].append(ref)
            elif layer == "insert":
                scene["inserts"].append(ref)
        scenes.append(scene)

    if update_db:
        await proj_db.commit()
        now = datetime.now(timezone.utc).isoformat()
        async with proj_db.execute("SELECT * FROM generations WHERE project_id=?", (project_id,)) as cur:
            existing = {(r["kind"], r["asset_ref"], r["beat_id"] or ""): dict(r) for r in await cur.fetchall()}
        seen = set()
        for g in generations:
            key = (g["kind"], g["asset_ref"], g["beat_id"] or "")
            seen.add(key)
            ex = existing.get(key)
            if ex:
                await proj_db.execute(
                    "UPDATE generations SET gen_label=?, title=?, prompt=?, updated_at=? WHERE id=?",
                    (g["gen_id"], g["title"], g["prompt"], now, ex["id"]))
                g["db_id"], g["file_path"], g["status"] = ex["id"], ex["file_path"], ex["status"]
            else:
                await proj_db.execute(
                    "INSERT INTO generations (project_id, gen_label, kind, asset_ref, beat_id, title, prompt, "
                    "file_path, status, error, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'','pending','',?,?)",
                    (project_id, g["gen_id"], g["kind"], g["asset_ref"], g["beat_id"], g["title"], g["prompt"], now, now))
                async with proj_db.execute("SELECT id FROM generations WHERE project_id=? AND gen_label=?", (project_id, g["gen_id"])) as cur:
                    g["db_id"] = (await cur.fetchone())["id"]
                g["file_path"], g["status"] = "", "pending"
        for key, ex in existing.items():
            if key not in seen:
                await proj_db.execute("DELETE FROM generations WHERE id=?", (ex["id"],))
        await proj_db.commit()
    await proj_db.close()

    if write:
        pdir = get_project_dir(ch_id, folder.split("_")[1]) / "07_beats" / "prompts"
        pdir.mkdir(parents=True, exist_ok=True)
        lines = ["# GENERATION LIST (masters first, then poses)", ""]
        for g in generations:
            lines.append(f"## {g['gen_id']} · {g['title']} · {g['kind']} · refs: {g['refs'] or '-'}")
            lines.append(g["prompt"])
            lines.append("")
        (pdir / "GENERATIONS.md").write_text("\n".join(lines), encoding="utf-8")
        (pdir / "scenes.json").write_text(json.dumps(scenes, indent=2, ensure_ascii=False), encoding="utf-8")

    counts["masters"] = len(seen_master)
    counts["generations"] = len(generations)
    counts["cleaned_overlays"] = cleaned
    return counts, generations, scenes


@router.post("/projects/{project_id}/prompts/compose")
async def compose(project_id: str):
    counts, _, _ = await _compose_all(project_id, update_db=True, write=True)
    return counts


@router.get("/projects/{project_id}/prompts/pack")
async def pack(project_id: str):
    counts, generations, scenes = await _compose_all(project_id, update_db=False, write=False)
    return {"counts": counts, "generations": generations, "scenes": scenes}


@router.put("/projects/{project_id}/beats/elements/{be_id}/note")
async def update_note(project_id: str, be_id: str, data: NoteUpdate):
    folder, ch_id, desc = await _proj(project_id)
    proj_db = await get_project_db(folder)
    if data.editor_note is not None:
        await proj_db.execute("UPDATE beat_elements SET editor_note=? WHERE id=?", (data.editor_note, be_id))
    if data.improv_note is not None:
        await proj_db.execute("UPDATE beat_elements SET improv_note=? WHERE id=?", (data.improv_note, be_id))
    await proj_db.commit()
    await proj_db.close()
    return {"status": "updated"}
