# backend/api/render.py
# SCENES-MP4 P3-T03: checkpoint render gate (backend-only; no MP4 work — P4 builds it).
#
# S13 gains ONE blocking gate: render is refused while any scene is unapproved
# (missing row or status != 'approved', or stale=1 which also needs re-review)
# or any beat lacks audio (no 08_export/voiceover/<beat>.wav on disk, empty
# file, or no measured duration). Everything else stays advisory — this gate
# blocks the render call only, never downstream work (locked invariant).
#
# P4-T01 will extend THIS file with the real render_jobs table + background
# render; the gate helper below is the shared check both endpoints use.

from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.core.config import DATA_DIR
from backend.db.connection import get_app_db, get_project_db

router = APIRouter(tags=["render"])


async def _get_proj(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute(
        "SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)
    ) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


def _sample(ids: list[str], n: int = 5) -> str:
    return ", ".join(ids[:n]) + ("..." if len(ids) > n else "")


async def render_gate(project_id: str) -> dict:
    """Shared gate check. Pure read (no writes) — safe to call from
    checkpoint, GET check, and POST render."""
    folder, _ch_id = await _get_proj(project_id)
    proj_db = await get_project_db(folder)
    try:
        async with proj_db.execute(
            "SELECT id, duration_sec FROM beats WHERE project_id=? AND stale=0 "
            "ORDER BY sort_order",
            (project_id,),
        ) as cur:
            beats = [dict(r) for r in await cur.fetchall()]
        beat_ids = [b["id"] for b in beats]
        scenes_by_beat: dict[str, dict] = {}
        if beat_ids:
            placeholders = ",".join("?" for _ in beat_ids)
            async with proj_db.execute(
                f"SELECT beat_id, status, stale FROM scenes WHERE beat_id IN ({placeholders})",
                beat_ids,
            ) as cur:
                for r in await cur.fetchall():
                    scenes_by_beat[r["beat_id"]] = dict(r)
    finally:
        await proj_db.close()

    base = Path(DATA_DIR) / "projects" / folder
    vo_dir = base / "08_export" / "voiceover"

    unapproved: list[str] = []
    stale_scenes: list[str] = []
    missing_audio: list[str] = []
    missing_detail: list[dict] = []
    for b in beats:
        bid = b["id"]
        sc = scenes_by_beat.get(bid)
        if sc is None or (sc.get("status") or "") != "approved":
            unapproved.append(bid)
        elif sc.get("stale"):
            stale_scenes.append(bid)
        wav = vo_dir / f"{bid}.wav"
        dur = b.get("duration_sec")
        if not wav.exists():
            missing_audio.append(bid)
            missing_detail.append({"beat_id": bid, "reason": "no wav"})
        elif wav.stat().st_size == 0:
            missing_audio.append(bid)
            missing_detail.append({"beat_id": bid, "reason": "empty wav"})
        elif dur is None or float(dur) <= 0:
            missing_audio.append(bid)
            missing_detail.append({"beat_id": bid, "reason": "no duration"})
    try:
        total_dur = round(sum(float(b["duration_sec"] or 0) for b in beats), 1)
    except (TypeError, ValueError):
        total_dur = 0.0

    total = len(beats)
    approved = sum(1 for b in beats if b["id"] not in unapproved and b["id"] not in stale_scenes)
    can_render = (
        total > 0 and not unapproved and not stale_scenes and not missing_audio
    )
    if total == 0:
        message = (
            f"Render blocked: project {project_id} has no beats — "
            "extract beats first, then retry."
        )
    elif can_render:
        message = (
            f"Render gate passed — {total}/{total} scenes approved, "
            f"{total}/{total} beats have audio, total {total_dur}s. "
            "(P3-T03 gate only; P4 renders the MP4.)"
        )
    else:
        parts = []
        if unapproved:
            parts.append(
                f"{len(unapproved)}/{total} scenes unapproved (e.g. {_sample(unapproved)})"
            )
        if stale_scenes:
            parts.append(
                f"{len(stale_scenes)}/{total} scenes stale (e.g. {_sample(stale_scenes)})"
            )
        if missing_audio:
            parts.append(
                f"{len(missing_audio)}/{total} beats missing audio "
                f"(e.g. {_sample(missing_audio)})"
            )
        message = (
            f"Render blocked: {'; '.join(parts)}. "
            f"Approve scenes in Beat Board "
            f"(PUT /api/v1/projects/{project_id}/scenes/{{beat_id}} "
            f"{{\"status\":\"approved\"}}) and build voiceover "
            f"(POST /api/v1/projects/{project_id}/voiceover/build), then retry."
        )
    return {
        "can_render": can_render,
        "total_beats": total,
        "approved": approved,
        "unapproved": unapproved,
        "stale_scenes": stale_scenes,
        "missing_audio": missing_audio,
        "missing_audio_detail": missing_detail,
        "total_duration_sec": total_dur,
        "message": message,
    }


@router.get("/projects/{project_id}/render/check")
async def render_check(project_id: str):
    """Read-only gate status for S13 (future UI) and for scripting."""
    return await render_gate(project_id)


@router.post("/projects/{project_id}/render")
async def request_render(project_id: str):
    """Gate-only stub: refuses with 409 while the gate fails, passes with a
    ready receipt when it passes. P4-T01 replaces the pass branch with the
    real render_jobs background render — the 409 branch stays as-is."""
    gate = await render_gate(project_id)
    if not gate["can_render"]:
        raise HTTPException(409, gate["message"])
    return {
        "status": "ready",
        "can_render": True,
        "total_beats": gate["total_beats"],
        "total_duration_sec": gate["total_duration_sec"],
        "message": gate["message"],
    }
