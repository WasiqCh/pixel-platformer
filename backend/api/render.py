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
#
# P4-T02 frame builder (stills v1, no motion engine, no ffmpeg, no LLM calls):
# per beat, hold its approved scene preview PNG for round(duration_sec*30)
# frames (durations are the narration-measured beats.duration_sec — never
# recomputed here). Frames live ONLY in 07_render/frames/ as frame_%06d.png
# (1-based, global sequence). Frame 1 of beat N is a byte copy of its approved
# preview, so it pixel-matches by construction. Fresh jobs wipe frame_*.png;
# resumes keep existing frames and overwrite deterministically from the
# computed offset (same range, same bytes — idempotent).
#
# P4-T03 ffmpeg probe + mux (stills v1 in, MP4 out, no LLM calls):
# probe ffmpeg at runtime (FFMPEG_PATH env -> PATH, never hard-coded; hard
# failure names every location tried — same discipline as the Inkscape probe
# in generation.py). Per beat: PNG-loop (that beat's frames) + per-beat WAV
# (08_export/voiceover/<beat_id>.wav) -> per-segment MP4 in 07_render/segments/
# (seg_001.mp4, 1-based beat order). Then concat (ffmpeg concat demuxer,
# -c copy) -> 08_handoff/<project>_final.mp4 (version _vN on re-render, never
# overwrite). Never hold all frames at once: encode segment -> delete that
# beat's frames -> next. Post-render asserts the frames dir is empty.

import asyncio
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.core.config import DATA_DIR
from backend.db.connection import get_app_db, get_project_db

router = APIRouter(tags=["render"])

# Live tasks only (dedupe + aliveness). Progress itself is persisted in
# render_jobs, so GET status reads the DB — reload-safe by construction.
_TASKS: dict[str, asyncio.Task] = {}

# Stills v1: 30 fps hold per P4-T02 spec (round(duration_sec*30) frames/beat).
_FPS = 30

# SCENES-MP4 P4-T03: ffmpeg probe (same discipline as the Inkscape probe in
# generation.py: env override -> PATH, never hard-coded, clear error naming
# everything tried). Only ffmpeg is probed (ffprobe is verification-only,
# used by the acceptance check — not by the worker).


def _probe_ffmpeg() -> tuple[str, str, list[str]]:
    """Probe for the ffmpeg binary. Returns (path, source, tried).

    source is one of 'env' | 'PATH'.
    tried lists every location checked (for the clear-error rule).
    Raises FileNotFoundError naming every location tried when not found.
    """
    tried: list[str] = []
    env = (os.environ.get("FFMPEG_PATH") or "").strip().strip('"')
    if env:
        tried.append(f"FFMPEG_PATH={env}")
        if os.path.isfile(env):
            return env, "env", tried
        tried.append(f"FFMPEG_PATH missing on disk: {env}")
    else:
        tried.append("FFMPEG_PATH=(unset)")
    which = shutil.which("ffmpeg")
    tried.append(f"PATH:ffmpeg={'found ' + which if which else 'not found'}")
    if which and os.path.isfile(which):
        return which, "PATH", tried
    raise FileNotFoundError(
        "ffmpeg not found. Tried: " + " | ".join(tried))


def _next_final_path(handoff_dir: Path, project_id: str) -> Path:
    """Versioned final output (never overwrite): <project>_final.mp4 first,
    then <project>_final_v2.mp4, _v3, ... Picks the first name not on disk."""
    first = handoff_dir / f"{project_id}_final.mp4"
    if not first.exists():
        return first
    n = 2
    while True:
        cand = handoff_dir / f"{project_id}_final_v{n}.mp4"
        if not cand.exists():
            return cand
        n += 1


def _delete_beat_frames(frames_dir: Path, first_num: int, count: int) -> None:
    """Delete one beat's frames (encode -> delete -> next; never hold all)."""
    for k in range(count):
        try:
            (frames_dir / f"frame_{first_num + k:06d}.png").unlink(missing_ok=True)
        except OSError:
            pass


def _frames_remaining(frames_dir: Path) -> list[str]:
    try:
        return sorted(p.name for p in frames_dir.glob("frame_*.png"))
    except OSError:
        return []


def _run_cmd(cmd: list[str], timeout: int) -> None:
    """Blocking subprocess runner (called via asyncio.to_thread so the event
    loop stays live for status/cancel polls). Raises RuntimeError with the
    stderr tail when ffmpeg exits non-zero."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ffmpeg timed out after {timeout}s: {' '.join(cmd[:4])}... "
                           f"({type(e).__name__})")
    except Exception as e:
        raise RuntimeError(f"ffmpeg crashed: {type(e).__name__}: {str(e)[:200]}")
    if r.returncode != 0:
        err = (r.stderr or r.stdout or f"exit {r.returncode}")[-300:]
        raise RuntimeError(f"ffmpeg failed (exit {r.returncode}): {err}")


def _encode_segment(ffmpeg: str, frames_dir: Path, first_num: int, count: int,
                    wav: Path, seg_path: Path) -> None:
    """One beat's frames + its WAV -> one segment MP4. -y so a resume redo of
    the in-flight beat overwrites deterministically (idempotent). -shortest
    keeps A/V in sync when the rounded frame hold differs from the WAV by a
    fraction of a frame; -frames:v caps the image2 reader to this beat."""
    cmd = [ffmpeg, "-y",
           "-framerate", str(_FPS), "-start_number", str(first_num),
           "-i", str(frames_dir / "frame_%06d.png"),
           "-i", str(wav),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(_FPS),
           "-c:a", "aac", "-b:a", "192k",
           "-frames:v", str(count),
           "-shortest",
           str(seg_path)]
    _run_cmd(cmd, timeout=300)


def _concat_final(ffmpeg: str, list_file: Path, final_path: Path) -> None:
    """Concat demuxer with -c copy (all segments share codec params). -y is
    safe: final_path is a fresh versioned name that must not exist yet."""
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0",
           "-i", str(list_file), "-c", "copy", str(final_path)]
    _run_cmd(cmd, timeout=600)


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


def _frames_for_duration(duration_sec) -> int:
    """Stills-v1 frame count for one beat. Durations are narration-measured
    (beats.duration_sec) — never recomputed here. Guard floors at 1 so a
    degenerate <0.017s beat still yields one still instead of zero."""
    try:
        dur = float(duration_sec)
    except (TypeError, ValueError):
        raise ValueError(f"bad duration_sec={duration_sec!r} (needs voiceover measure)")
    if not (dur > 0):
        raise ValueError(f"bad duration_sec={duration_sec!r} (needs voiceover measure)")
    return max(1, round(dur * _FPS))


def _write_beat_frames(src: Path, frames_dir: Path, first_num: int, count: int) -> None:
    """Byte-copy one approved preview into N sequential frames. Runs in a
    thread (called via asyncio.to_thread) so status/cancel polls stay live.
    Byte copy => frame 1 pixel-matches the approved preview by construction."""
    data = Path(src).read_bytes()
    if not data:
        raise ValueError(f"preview {src} is empty")
    for k in range(count):
        (frames_dir / f"frame_{first_num + k:06d}.png").write_bytes(data)


async def _run_render(project_id: str, folder: str, job_id: int) -> None:
    """Background worker: one beat = one segment. P4-T03: stills frame hold
    (P4-T02) + ffmpeg per-segment mux + concat to versioned final MP4 — no
    LLM calls. Shape kept from P4-T01: persist current_segment + progress
    after EVERY segment, check for cooperative cancel BETWEEN segments (never
    mid-segment), resume from the persisted current_segment."""
    proj_db = None
    try:
        # Fail fast with a clear error naming everything tried (same
        # discipline as the Inkscape probe) — before any heavy frame work.
        try:
            ffmpeg, _ff_source, _ff_tried = _probe_ffmpeg()
        except FileNotFoundError as e:
            raise RuntimeError(str(e))
        proj_db = await get_project_db(folder)
        async with proj_db.execute(
            "SELECT id, duration_sec FROM beats WHERE project_id=? AND stale=0 "
            "ORDER BY sort_order",
            (project_id,),
        ) as cur:
            beats = [dict(r) for r in await cur.fetchall()]
        beat_ids = [b["id"] for b in beats]
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
        # Frame counts come from the stored narration measures (never recompute
        # audio here). A bad/zero duration fails fast with a clear error.
        counts = [_frames_for_duration(b.get("duration_sec")) for b in beats]
        base = Path(DATA_DIR) / "projects" / folder
        frames_dir = base / "07_render" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        # P4-T03 dirs (mkdir = heal for old projects; fresh projects also get
        # 07_render/segments via fs_manager).
        segments_dir = base / "07_render" / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)
        handoff_dir = base / "08_handoff"
        handoff_dir.mkdir(parents=True, exist_ok=True)
        vo_dir = base / "08_export" / "voiceover"
        if start == 0:
            # Fresh job: never accumulate across renders. Wipe frames AND
            # segments, then claim a versioned final name (never overwrite —
            # re-render after done mints _vN).
            for p in frames_dir.glob("frame_*.png"):
                try:
                    p.unlink()
                except OSError:
                    pass
            for p in segments_dir.glob("seg_*.mp4"):
                try:
                    p.unlink()
                except OSError:
                    pass
            try:
                (segments_dir / "segments.txt").unlink(missing_ok=True)
            except OSError:
                pass
            final_path = _next_final_path(handoff_dir, project_id)
            final_rel = f"08_handoff/{final_path.name}"
            await proj_db.execute(
                "UPDATE render_jobs SET output_path=?, updated_at=? WHERE id=?",
                (final_rel, _now(), job_id))
            await proj_db.commit()
        else:
            # Resume: keep existing segment MP4s for beats < start and the
            # stored versioned output_path (never re-version mid-job).
            async with proj_db.execute(
                    "SELECT output_path FROM render_jobs WHERE id=?", (job_id,)) as cur:
                rrow = await cur.fetchone()
            stored_rel = (dict(rrow).get("output_path") or "") if rrow else ""
            final_path = (base / stored_rel) if stored_rel else _next_final_path(handoff_dir, project_id)
            final_rel = stored_rel or f"08_handoff/{final_path.name}"
        # Resume keeps existing frames and overwrites deterministically from
        # this offset (same range, same bytes — idempotent redo of the
        # in-flight beat after a mid-segment cancel).
        next_frame = sum(counts[:start]) + 1
        # Deferred import: scenes loads llm_client at import time; keep worker
        # startup ordering free. Reuses the exact preview file the GET endpoint
        # serves (no duplicated Pillow logic, no drift).
        from backend.api import scenes as scenes_api
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
            # --- segment work: hold approved preview for N frames, mux with
            # its WAV into a per-segment MP4, then delete the frames ---
            beat_id = beat_ids[i]
            need = counts[i]
            async with proj_db.execute(
                    "SELECT status, stale FROM scenes WHERE beat_id=?", (beat_id,)) as cur:
                sc = await cur.fetchone()
            if not sc:
                raise RuntimeError(f"beat {beat_id}: no scene row (plan scenes first)")
            scd = dict(sc)
            if (scd.get("status") or "") != "approved":
                raise RuntimeError(
                    f"beat {beat_id}: scene not approved "
                    f"(status={scd.get('status') or ''})")
            if scd.get("stale"):
                raise RuntimeError(f"beat {beat_id}: scene stale (re-review first)")
            wav = vo_dir / f"{beat_id}.wav"
            if not wav.exists() or wav.stat().st_size == 0:
                raise RuntimeError(
                    f"beat {beat_id}: voiceover WAV missing/empty ({wav}) — "
                    "build voiceover first")
            resp = await scenes_api.scene_preview(project_id, beat_id)
            src = Path(getattr(resp, "path", "") or "")
            if not src.name or not src.exists() or src.stat().st_size == 0:
                raise RuntimeError(f"beat {beat_id}: preview missing ({src})")
            first_num = next_frame
            await asyncio.to_thread(_write_beat_frames, src, frames_dir, first_num, need)
            seg_path = segments_dir / f"seg_{i + 1:03d}.mp4"
            await asyncio.to_thread(
                _encode_segment, ffmpeg, frames_dir, first_num, need, wav, seg_path)
            if not seg_path.exists() or seg_path.stat().st_size == 0:
                raise RuntimeError(f"beat {beat_id}: segment missing after encode ({seg_path})")
            # Never hold all frames at once: this beat's frames go now.
            _delete_beat_frames(frames_dir, first_num, need)
            next_frame += need
            # --- between-segments cancel point (second check covers a cancel
            # that landed during the segment work) ---
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
            # --- concat per-segment MP4s -> versioned final ---
            seg_files = [segments_dir / f"seg_{k + 1:03d}.mp4" for k in range(total)]
            missing_segs = [p.name for p in seg_files if not p.exists() or p.stat().st_size == 0]
            if missing_segs:
                raise RuntimeError(
                    f"concat blocked: {len(missing_segs)}/{total} segments missing "
                    f"(e.g. {', '.join(missing_segs[:3])})")
            list_file = segments_dir / "segments.txt"
            await asyncio.to_thread(
                list_file.write_text,
                "".join(f"file '{p.name}'\n" for p in seg_files), encoding="utf-8")
            if final_path.exists():
                raise RuntimeError(
                    f"refusing to overwrite final ({final_path.name}) — "
                    "version claim lost its race")
            await asyncio.to_thread(_concat_final, ffmpeg, list_file, final_path)
            if not final_path.exists() or final_path.stat().st_size == 0:
                raise RuntimeError(f"final MP4 missing after concat ({final_path})")
            # Post-render: temp frames dir must be empty (segments encode ->
            # delete as we go, so any leftover is a leak worth failing on).
            leftover = await asyncio.to_thread(_frames_remaining, frames_dir)
            if leftover:
                raise RuntimeError(
                    f"frames dir not empty after render: {len(leftover)} left "
                    f"(e.g. {', '.join(leftover[:3])})")
            # Tidy temp segments (final is the artifact; a fresh re-render
            # rebuilds them — never overwrite the versioned final).
            for p in seg_files:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                list_file.unlink(missing_ok=True)
            except OSError:
                pass
            await proj_db.execute(
                "UPDATE render_jobs SET status='done', progress=1.0, output_path=?, "
                "updated_at=? WHERE id=?", (final_rel, _now(), job_id))
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
            "(P4-T03: POST /render muxes per-beat MP4 segments via ffmpeg to "
            "08_handoff/<project>_final[_vN].mp4.)"
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
    """Gate (409 branch, unchanged from P3-T03) + P4-T03 start/resume.

    Pass branch: new render inserts a render_jobs row (never overwrites a done
    row — history intact; output is a versioned 08_handoff/<project>_final[_vN]
    .mp4 name, never overwrite); resume reuses the cancelled/error row from
    its persisted current_segment. Launches asyncio.create_task (generation.py
    / voiceover.py pattern); poll GET .../render/status for persisted progress.
    No LLM calls — stills hold + ffmpeg mux only."""
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
            # Claim the versioned final name now (first free _final[_vN].mp4)
            # so status shows the real target from the start; the worker
            # re-claims on fresh start (same result — first free name).
            handoff_dir = Path(DATA_DIR) / "projects" / folder / "08_handoff"
            handoff_dir.mkdir(parents=True, exist_ok=True)
            output_path = f"08_handoff/{_next_final_path(handoff_dir, project_id).name}"
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
        f"(P4-T03: per-beat PNG-loop + WAV -> segment MP4 -> concat to "
        f"{job['output_path']}; frames deleted per segment).")
    return out
