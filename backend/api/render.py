# backend/api/render.py
# SCENES-MP4 P3-T03: checkpoint render gate (backend-only; no MP4 work — P4 builds it).
# SCENES-MP4 P4-T01: render_jobs table + background worker + status endpoints
# (extends this gate file, no new file).
#
# S13 gains ONE blocking gate: render is refused while any scene is unapproved
# (missing row or status != 'approved', or stale=1 which also needs re-review),
# any beat is stale (own blocking message — stale beats filter out of the
# fresh-beats query, so without this they collapse to a misleading "no beats"),
# or any beat lacks audio (no 08_export/voiceover/<beat>.wav on disk, empty
# file, or no measured duration). Everything else stays advisory — this gate
# blocks the render call only, never downstream work (locked invariant).
#
# P4-T01 worker: beats-as-segments placeholder (no LLM calls, no ffmpeg yet —
# P4-T02 builds frames, P4-T03 muxes). Pattern reuses generation.py/voiceover.py:
# asyncio.create_task + status endpoint, but progress lives in the render_jobs
# DB row (not memory) so a page reload doesn't blind the user. Cooperative
# cancel is checked between segments; resume reuses the same row from
# current_segment (never rewound to 1).

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.core.config import DATA_DIR
from backend.db.connection import get_app_db, get_project_db

router = APIRouter(tags=["render"])

# Live tasks only (dedupe + aliveness). Progress itself is persisted in
# render_jobs, so GET status reads the DB — reload-safe by construction.
_TASKS: dict[str, asyncio.Task] = {}

# Placeholder per-segment cost (no LLM, no ffmpeg in T01). 30 beats ≈ 15s:
# long enough to land a mid-run cancel deterministically, short enough to
# prove resume-to-done in one sitting. P4-T02/T03 replace the sleep with real
# frame/encode work but keep the between-segments cancel/resume shape.
_SEGMENT_DELAY_SEC = 0.5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


async def _latest_job_row(proj_db, project_id: str):
    async with proj_db.execute(
        "SELECT * FROM render_jobs WHERE project_id=? ORDER BY id DESC LIMIT 1",
        (project_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


def _job_status_payload(job: dict | None, alive: bool) -> dict:
    if not job:
        return {"has_job": False, "job_id": None, "status": "none",
                "running": False, "alive": False,
                "total_segments": 0, "current_segment": 0,
                "progress": 0.0, "error": "", "output_path": ""}
    st = job.get("status") or ""
    total = int(job.get("total_segments") or 0)
    cur = int(job.get("current_segment") or 0)
    try:
        prog = float(job.get("progress") or 0.0)
    except (TypeError, ValueError):
        prog = 0.0
    return {"has_job": True, "job_id": job["id"], "status": st,
            "running": st in ("running", "cancel_requested"), "alive": alive,
            "total_segments": total, "current_segment": cur,
            "progress": round(prog, 4), "error": job.get("error") or "",
            "output_path": job.get("output_path") or "",
            "created_at": job.get("created_at") or "",
            "updated_at": job.get("updated_at") or ""}


async def _run_render(project_id: str, folder: str, job_id: int) -> None:
    """Background worker: one beat = one segment. Placeholder step only
    (sleep — no LLM calls in T01), but the shape is the real one P4-T02/T03
    keep: persist current_segment + progress after EVERY segment, check for
    cooperative cancel BETWEEN segments (never mid-segment), resume from the
    persisted current_segment."""
    proj_db = None
    try:
        proj_db = await get_project_db(folder)
        async with proj_db.execute(
            "SELECT id FROM beats WHERE project_id=? AND stale=0 ORDER BY sort_order",
            (project_id,),
        ) as cur:
            beat_ids = [r["id"] for r in await cur.fetchall()]
        async with proj_db.execute(
            "SELECT * FROM render_jobs WHERE id=?", (job_id,)) as cur:
            job = await cur.fetchone()
        if not job:
            return
        job = dict(job)
        total = int(job.get("total_segments") or 0)
        start = int(job.get("current_segment") or 0)
        if total != len(beat_ids):
            # Beats changed since the job was created (re-extract): adopt the
            # live count, clamp the resume point, keep going — never rewind.
            total = len(beat_ids)
            start = min(max(start, 0), total)
            prog = (start / total) if total else 1.0
            await proj_db.execute(
                "UPDATE render_jobs SET total_segments=?, current_segment=?, "
                "progress=?, updated_at=? WHERE id=?",
                (total, start, prog, _now(), job_id))
            await proj_db.commit()
        if total == 0:
            await proj_db.execute(
                "UPDATE render_jobs SET status='error', error=?, updated_at=? WHERE id=?",
                ("no fresh beats to render (all stale or none extracted)", _now(), job_id))
            await proj_db.commit()
            return
        for i in range(start, total):
            async with proj_db.execute(
                    "SELECT status FROM render_jobs WHERE id=?", (job_id,)) as cur:
                srow = await cur.fetchone()
            if not srow:
                return
            st = srow["status"]
            if st == "cancel_requested":
                await proj_db.execute(
                    "UPDATE render_jobs SET status='cancelled', updated_at=? WHERE id=?",
                    (_now(), job_id))
                await proj_db.commit()
                return
            if st != "running":
                return
            # --- segment work (T01 placeholder; T02/T03 put frames/ffmpeg here) ---
            await asyncio.sleep(_SEGMENT_DELAY_SEC)
            # --- between-segments cancel point (second check covers a cancel
            # that landed during the segment sleep) ---
            async with proj_db.execute(
                    "SELECT status FROM render_jobs WHERE id=?", (job_id,)) as cur:
                srow2 = await cur.fetchone()
            if srow2 and srow2["status"] == "cancel_requested":
                await proj_db.execute(
                    "UPDATE render_jobs SET status='cancelled', updated_at=? WHERE id=?",
                    (_now(), job_id))
                await proj_db.commit()
                return
            done = i + 1
            prog = done / total if total else 1.0
            await proj_db.execute(
                "UPDATE render_jobs SET current_segment=?, progress=?, updated_at=? "
                "WHERE id=?",
                (done, prog, _now(), job_id))
            await proj_db.commit()
        async with proj_db.execute(
                "SELECT status, current_segment, total_segments FROM render_jobs "
                "WHERE id=?", (job_id,)) as cur:
            fin = await cur.fetchone()
        if fin and fin["status"] == "running" \
                and fin["current_segment"] >= fin["total_segments"]:
            await proj_db.execute(
                "UPDATE render_jobs SET status='done', progress=1.0, updated_at=? "
                "WHERE id=?", (_now(), job_id))
            await proj_db.commit()
    except Exception as e:
        try:
            err_db = await get_project_db(folder)
            try:
                await err_db.execute(
                    "UPDATE render_jobs SET status='error', error=?, updated_at=? "
                    "WHERE id=?",
                    (f"{type(e).__name__}: {str(e)[:280]}", _now(), job_id))
                await err_db.commit()
            finally:
                await err_db.close()
        except Exception:
            pass
    finally:
        if proj_db is not None:
            try:
                await proj_db.close()
            except Exception:
                pass
        _TASKS.pop(project_id, None)


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
        # P4-T01a: stale beats need their own blocking message. They are
        # filtered out of the fresh-beats query above, so without this they
        # collapse to total==0 → a misleading "no beats — extract beats first".
        async with proj_db.execute(
            "SELECT id FROM beats WHERE project_id=? AND stale=1 ORDER BY sort_order",
            (project_id,),
        ) as cur:
            stale_beats = [r["id"] for r in await cur.fetchall()]
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
        total > 0 and not unapproved and not stale_scenes
        and not missing_audio and not stale_beats
    )
    if total == 0:
        if stale_beats:
            message = (
                f"Render blocked: {len(stale_beats)} beats stale "
                f"(e.g. {_sample(stale_beats)}) — re-extract beats "
                "(Beat Board) or clear stale flags, then retry."
            )
        else:
            message = (
                f"Render blocked: project {project_id} has no beats — "
                "extract beats first, then retry."
            )
    elif can_render:
        message = (
            f"Render gate passed — {total}/{total} scenes approved, "
            f"{total}/{total} beats have audio, total {total_dur}s. "
            "(P4-T01: POST /render starts the background render.)"
        )
    else:
        parts = []
        if stale_beats:
            parts.append(
                f"{len(stale_beats)} beats stale (e.g. {_sample(stale_beats)})"
            )
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
            + ("Re-extract beats (Beat Board) or clear stale flags; " if stale_beats else "")
            + f"Approve scenes in Beat Board "
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
        "stale_beats": stale_beats,
        "missing_audio": missing_audio,
        "missing_audio_detail": missing_detail,
        "total_duration_sec": total_dur,
        "message": message,
    }


@router.get("/projects/{project_id}/render/check")
async def render_check(project_id: str):
    """Read-only gate status for S13 (future UI) and for scripting."""
    return await render_gate(project_id)


@router.get("/projects/{project_id}/render/status")
async def render_status(project_id: str):
    """Persisted job status — reads the render_jobs DB row, so a page reload
    doesn't blind the user (unlike the in-memory _STATE in voiceover.py).
    alive=True means the worker task is live in this process; running=True
    reflects the persisted row (survives reload/restart)."""
    folder, _ = await _get_proj(project_id)
    proj_db = await get_project_db(folder)
    try:
        job = await _latest_job_row(proj_db, project_id)
    finally:
        await proj_db.close()
    task = _TASKS.get(project_id)
    alive = task is not None and not task.done()
    return _job_status_payload(job, alive)


@router.post("/projects/{project_id}/render/cancel")
async def render_cancel(project_id: str):
    """Cooperative cancel: flips the persisted row to cancel_requested; the
    worker observes it BETWEEN segments and marks the row cancelled, keeping
    current_segment so POST /render resumes at N, not 1."""
    folder, _ = await _get_proj(project_id)
    proj_db = await get_project_db(folder)
    try:
        job = await _latest_job_row(proj_db, project_id)
        if not job or job.get("status") not in ("running", "cancel_requested"):
            raise HTTPException(400, "No running render to cancel.")
        await proj_db.execute(
            "UPDATE render_jobs SET status='cancel_requested', updated_at=? WHERE id=?",
            (_now(), job["id"]))
        await proj_db.commit()
        async with proj_db.execute(
                "SELECT * FROM render_jobs WHERE id=?", (job["id"],)) as cur:
            job = dict(await cur.fetchone())
    finally:
        await proj_db.close()
    task = _TASKS.get(project_id)
    alive = task is not None and not task.done()
    out = _job_status_payload(job, alive)
    out["message"] = (
        f"Cancel requested at segment {job['current_segment']}/{job['total_segments']} — "
        "worker stops between segments; resume with POST /render.")
    return out


@router.post("/projects/{project_id}/render")
async def request_render(project_id: str):
    """Gate (409 branch, unchanged from P3-T03) + P4-T01 start/resume.

    Pass branch: new render inserts a render_jobs row (never overwrites a done
    row — history intact); resume reuses the cancelled/error row from its
    persisted current_segment. Launches asyncio.create_task (generation.py /
    voiceover.py pattern); poll GET .../render/status for persisted progress.
    No LLM calls in this ticket."""
    gate = await render_gate(project_id)
    if not gate["can_render"]:
        raise HTTPException(409, gate["message"])
    folder, _ = await _get_proj(project_id)
    proj_db = await get_project_db(folder)
    try:
        job = await _latest_job_row(proj_db, project_id)
        task = _TASKS.get(project_id)
        alive = task is not None and not task.done()
        if job and job.get("status") in ("running", "cancel_requested") and alive:
            raise HTTPException(400, (
                f"A render is already running "
                f"(job {job['id']} at {job['current_segment']}/{job['total_segments']}) — "
                "poll GET .../render/status or cancel first."))
        resumed = False
        if job and job.get("status") in ("running", "cancel_requested") and not alive:
            # Orphaned running row (server restarted mid-render): worker is
            # gone but progress persists — resume the same row, never rewind.
            await proj_db.execute(
                "UPDATE render_jobs SET status='running', updated_at=? WHERE id=?",
                (_now(), job["id"]))
            await proj_db.commit()
            job_id = job["id"]
            resumed = True
        elif job and job.get("status") in ("cancelled", "error"):
            await proj_db.execute(
                "UPDATE render_jobs SET status='running', error='', updated_at=? "
                "WHERE id=?", (_now(), job["id"]))
            await proj_db.commit()
            job_id = job["id"]
            resumed = True
        else:
            total = gate["total_beats"]
            output_path = f"08_handoff/{project_id}_final.mp4"
            now = _now()
            cur = await proj_db.execute(
                "INSERT INTO render_jobs (project_id, status, total_segments, "
                "current_segment, progress, error, output_path, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?, ?, ?)",
                (project_id, "running", total, 0, 0.0, "", output_path, now, now))
            job_id = cur.lastrowid
            await proj_db.commit()
        async with proj_db.execute(
                "SELECT * FROM render_jobs WHERE id=?", (job_id,)) as cur:
            job = dict(await cur.fetchone())
    finally:
        await proj_db.close()
    if _TASKS.get(project_id) is None or _TASKS[project_id].done():
        _TASKS[project_id] = asyncio.create_task(_run_render(project_id, folder, job_id))
    out = _job_status_payload(job, True)
    out["resumed"] = resumed
    out["can_render"] = True
    out["total_duration_sec"] = gate["total_duration_sec"]
    out["message"] = (
        f"{'Resumed' if resumed else 'Started'} render job {job_id} "
        f"at segment {job['current_segment']}/{job['total_segments']} "
        f"(P4-T01 placeholder segments; P4-T02/T03 build frames+ffmpeg).")
    return out
