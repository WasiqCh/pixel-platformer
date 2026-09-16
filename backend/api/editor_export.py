# backend/api/editor_export.py
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["editor_export"])

FPS = 25


def _now():
    return datetime.now(timezone.utc).isoformat()


def _tc(frames):
    hh, rem = divmod(frames, FPS * 3600)
    mm, rem = divmod(rem, FPS * 60)
    ss, ff = divmod(rem, FPS)
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def _srt_time(sec):
    ms = int(round(sec * 1000))
    hh, rem = divmod(ms, 3600000)
    mm, rem = divmod(rem, 60000)
    ss, mss = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{mss:03d}"


async def _proj(project_id):
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


@router.post("/projects/{project_id}/export/editor")
async def export_editor(project_id: str):
    folder, ch_id = await _proj(project_id)
    base = get_project_dir(ch_id, folder.split("_")[1])
    proj_db = await get_project_db(folder)

    async with proj_db.execute("SELECT * FROM beats WHERE project_id=? AND stale=0 ORDER BY sort_order", (project_id,)) as cur:
        beats = [dict(b) for b in await cur.fetchall()]
    for b in beats:
        async with proj_db.execute("SELECT * FROM beat_elements WHERE beat_id=? ORDER BY sort_order", (b["id"],)) as cur:
            b["elements"] = [dict(e) for e in await cur.fetchall()]

    async with proj_db.execute("SELECT * FROM generations WHERE project_id=?", (project_id,)) as cur:
        gens = [dict(g) for g in await cur.fetchall()]
    master_file, pose_file = {}, {}
    for g in gens:
        if g["status"] == "ready" and g["file_path"]:
            if g["kind"] == "master":
                master_file[g["asset_ref"]] = g["file_path"]
            else:
                pose_file[(g["asset_ref"], g["beat_id"])] = g["file_path"]
    async with proj_db.execute("SELECT asset_ref, file_path FROM library WHERE project_id=? AND status='ready'", (project_id,)) as cur:
        for r in await cur.fetchall():
            master_file.setdefault(r["asset_ref"], r["file_path"])
    await proj_db.close()

    edl = ["TITLE: EPISODE " + project_id, "FCM: NON-DROP FRAME", ""]
    srt, manifest_beats, missing = [], [], []
    cursor, ev, srt_idx = 0, 0, 0

    for b in beats:
        dur_f = int(round(b["duration_sec"] * FPS))
        rec_in, rec_out = cursor, cursor + dur_f
        cursor = rec_out
        in_sec, out_sec = rec_in / FPS, rec_out / FPS

        bgs = [e for e in b["elements"] if e["layer"] == "background"]
        mids = [e for e in b["elements"] if e["layer"] == "midground"]
        ins = [e for e in b["elements"] if e["layer"] == "insert"]

        plate = None
        if bgs:
            plate = {"ref": bgs[0]["asset_ref"], "file": master_file.get(bgs[0]["asset_ref"])}
        clip = None
        if plate and plate["file"]:
            clip = plate
        elif mids:
            clip = {"ref": mids[0]["asset_ref"], "file": pose_file.get((mids[0]["asset_ref"], b["id"]))}
        elif ins:
            clip = {"ref": ins[0]["asset_ref"], "file": master_file.get(ins[0]["asset_ref"])}

        ev += 1
        reel = (clip["ref"] if clip else "BLACK")[:8].ljust(8)
        edl.append(f"{ev:03d}  {reel} V     C        00:00:00:00 {_tc(dur_f)}  {_tc(rec_in)} {_tc(rec_out)}")
        edl.append(f"* FROM CLIP NAME: {(clip['file'] if clip and clip['file'] else 'MISSING_' + (clip['ref'] if clip else 'BLACK'))}")
        if plate and not plate["file"]:
            missing.append(f"{b['id']}/{plate['ref']}")
        for e in mids:
            f = pose_file.get((e["asset_ref"], b["id"]))
            edl.append(f"* LAYER midground: {e['asset_ref']} {e['framing']} file={f or 'MISSING'}")
            if not f: missing.append(f"{b['id']}/{e['asset_ref']}")
        for e in ins:
            f = master_file.get(e["asset_ref"])
            edl.append(f"* LAYER insert: {e['asset_ref']} file={f or 'MISSING'}")
            if not f: missing.append(f"{b['id']}/{e['asset_ref']}")
        edl.append("")

        overlay = None
        if b["overlay_text"]:
            srt_idx += 1
            otype = b["overlay_spec"] or "graphic"
            srt.append(f"{srt_idx}\n{_srt_time(in_sec)} --> {_srt_time(out_sec)}\n{b['overlay_text']}\n[{otype}]\n")
            overlay = {"text": b["overlay_text"], "type": otype,
                       "in_sec": round(in_sec, 2), "out_sec": round(out_sec, 2)}

        manifest_beats.append({
            "id": b["id"], "in_sec": round(in_sec, 2), "out_sec": round(out_sec, 2),
            "in_tc": _tc(rec_in), "out_tc": _tc(rec_out), "plate": plate,
            "mid_actors": [{"ref": e["asset_ref"], "framing": e["framing"],
                            "file": pose_file.get((e["asset_ref"], b["id"]))} for e in mids],
            "inserts": [{"ref": e["asset_ref"], "file": master_file.get(e["asset_ref"])} for e in ins],
            "overlay": overlay,
            "voice": f"08_export/voiceover/{b['id']}.wav",
        })

    manifest = {"project": project_id, "fps": FPS, "total_sec": round(cursor / FPS, 2),
                "built_at": _now(), "beats": manifest_beats, "missing": sorted(set(missing)),
                "voiceover_dir": "08_export/voiceover"}

    out_dir = base / "08_export"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "episode.edl").write_text("\n".join(edl), encoding="utf-8")
    (out_dir / "overlays.srt").write_text("\n".join(srt), encoding="utf-8")
    (out_dir / "editor_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"files": ["08_export/episode.edl", "08_export/overlays.srt", "08_export/editor_manifest.json"],
            "clips": ev, "stickers": srt_idx, "total_sec": manifest["total_sec"],
            "missing": len(manifest["missing"])}
