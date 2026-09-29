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
#
# F3-T01 ffmpeg motion by role, cheap filters only (worker-only, isolated):
# pop-in fade + 4-direction slides via animated crop window + final-beat
# fade-out, all inside the per-segment single encode (pad/crop/fade only —
# NO xfade, NO zoompan). Concat stays `-c copy` (cuts stay cuts). Mapping by
# overlay position / framing / chunk section (read-only); subtle by default
# with SCENES_MOTION* env overrides. Planning/approval untouched.

import asyncio
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.core.config import DATA_DIR
from backend.db.connection import get_app_db, get_project_db

router = APIRouter(tags=["render"])

# Live tasks only (dedupe + aliveness). Progress itself is persisted in
# render_jobs, so GET status reads the DB — reload-safe by construction.
_TASKS: dict[str, asyncio.Task] = {}

# Stills v1: 30 fps hold per P4-T02 spec (round(duration_sec*30) frames/beat).
_FPS = 30

# SCENES-MP4 F3-T01: ffmpeg motion by role, cheap filters only (worker-only).
# Owner ruling 2026-09-27: NO xfade, NO zoompan (force re-encode, slow).
# Allowed vocabulary only:
#   - pop-in fade (short global fade-in on every beat; the worker holds a
#     flattened preview PNG, so per-asset alpha would require re-compositing
#     in scenes.py — out of scope for cheap filters — hence a 0.2s fade from
#     black as the subtle pop-in approximation),
#   - 4-direction slides via animated crop window (pad + animated crop, one
#     direction per beat: up/down/left/right; plates + inserts steer the
#     choice via overlay position / framing, see _motion_direction),
#   - fade-out on the final beat only (0.5s to black).
# Mapping by beat role/framing (read-only — never touches planning/approval):
#   overlay position first (top* -> down, bottom/lower-third -> up,
#   top-left -> right, top-right -> left), else beat_elements framing
#   (close -> up, wide/long/establishing -> left, medium/full -> right),
#   else chunk-section keyword (hook -> right, payoff/outro/finale -> left,
#   turn/twist -> up), else index % 4 fallback (guarantees 4-dir coverage).
#   Overlay role (name/place/date/...) is semantic, not directional, so it
#   does not steer the direction — position does.
# Intensity: subtle by default (12px shift, 0.2s fade-in, 0.5s fade-out).
# Env overrides (no DB, no other files): SCENES_MOTION=off disables all
# motion (byte-identical baseline path, no -vf), SCENES_MOTION_PX (int px),
# SCENES_MOTION_FADE_IN / SCENES_MOTION_FADE_OUT (seconds, floats).
# Cuts stay cuts: the concat step keeps `-c copy` untouched (no re-encode,
# hard cuts at every beat boundary); motion lives inside the existing
# per-segment single encode only. No xfade / zoompan strings anywhere.


def _motion_settings() -> dict:
    """Read motion intensity (env only, once per worker start). Never raises:
    bad values fall back to the subtle defaults."""
    mode = (os.environ.get("SCENES_MOTION") or "subtle").strip().lower()
    try:
        px = int((os.environ.get("SCENES_MOTION_PX") or "12").strip())
    except (TypeError, ValueError):
        px = 12
    try:
        fi = float((os.environ.get("SCENES_MOTION_FADE_IN") or "0.2").strip())
    except (TypeError, ValueError):
        fi = 0.2
    try:
        fo = float((os.environ.get("SCENES_MOTION_FADE_OUT") or "0.5").strip())
    except (TypeError, ValueError):
        fo = 0.5
    px = min(max(px, 0), 32)
    fi = min(max(fi, 0.0), 1.0)
    fo = min(max(fo, 0.0), 1.5)
    return {"off": mode == "off", "px": px,
            "fade_in": fi, "fade_out": fo}


def _motion_direction(idx: int, overlay_pos: str | None,
                      framings: list[str], chunk_id: str | None) -> str:
    """One slide direction per beat (up|down|left|right). Deterministic in
    (idx, overlay_pos, framings, chunk_id) so resumes re-encode identically."""
    pos = (overlay_pos or "").strip().lower()
    if pos in ("top", "top-left", "top-right", "bottom", "lower-third"):
        if pos == "top":
            return "down"  # plate drops from the top edge
        if pos in ("bottom", "lower-third"):
            return "up"  # plate rises from the bottom edge
        if pos == "top-left":
            return "right"  # plate enters from the left edge
        return "left"  # top-right -> enters from the right edge
    for f in framings or []:
        fl = (f or "").strip().lower()
        if fl == "close":
            return "up"
        if fl in ("wide", "long", "establishing"):
            return "left"
        if fl in ("medium", "full"):
            return "right"
    ch = (chunk_id or "").strip().lower()
    if "hook" in ch:
        return "right"
    if any(k in ch for k in ("payoff", "outro", "finale")):
        return "left"
    if any(k in ch for k in ("turn", "twist")):
        return "up"
    return ("right", "left", "up", "down")[idx % 4]


def _motion_vf(direction: str, count: int, is_final: bool,
               fade_in_sec: float, fade_out_sec: float, px: int) -> str | None:
    """Cheap-filter chain for one beat: pad + animated crop + fade(s).

    Uses ONLY pad/crop/fade (no xfade, no zoompan). Output stays 1920x1080
    so every segment keeps identical codec params and the concat `-c copy`
    still joins hard cuts. Returns None when there is nothing to animate
    (count < 2 or px == 0 with no fades applicable)."""
    if count < 2:
        return None
    try:
        px_i = int(px)
    except (TypeError, ValueError):
        px_i = 12
    px_i = min(max(px_i, 0), 32)
    total = max(count - 1, 1)
    dur = count / _FPS
    try:
        fi = float(fade_in_sec)
    except (TypeError, ValueError):
        fi = 0.2
    try:
        fo = float(fade_out_sec)
    except (TypeError, ValueError):
        fo = 0.5
    fi = min(max(fi, 0.0), max(dur / 2.0, 0.0))
    parts: list[str] = []
    if px_i > 0:
        # Pad once, then slide the 1920x1080 crop window linearly across the
        # beat. Window centre is (px,px); moving it right shows the image
        # sliding left, etc. Expressions use `n` (0-based frame in this
        # single-segment encode, so resumes match fresh runs).
        parts.append(f"pad={1920 + 2 * px_i}:{1080 + 2 * px_i}:{px_i}:{px_i}:color=black")
        if direction == "left":  # image slides left
            x_e, y_e = f"{px_i}+{px_i}*n/{total}", f"{px_i}"
        elif direction == "right":  # image slides right
            x_e, y_e = f"{px_i}-{px_i}*n/{total}", f"{px_i}"
        elif direction == "up":  # image slides up
            x_e, y_e = f"{px_i}", f"{px_i}+{px_i}*n/{total}"
        else:  # "down": image slides down
            x_e, y_e = f"{px_i}", f"{px_i}-{px_i}*n/{total}"
        parts.append(f"crop=1920:1080:x='{x_e}':y='{y_e}'")
    if fi >= 1.0 / _FPS:
        parts.append(f"fade=t=in:st=0:d={fi:.3f}")
    if is_final:
        fo_c = min(max(fo, 0.0), max(dur - fi, 0.0))
        if fo_c >= 1.0 / _FPS:
            parts.append(f"fade=t=out:st={max(dur - fo_c, 0.0):.3f}:d={fo_c:.3f}")
    return ",".join(parts) if parts else None

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
                    wav: Path, seg_path: Path, vf: str | None = None) -> None:
    """One beat's frames + its WAV -> one segment MP4. -y so a resume redo of
    the in-flight beat overwrites deterministically (idempotent). -shortest
    keeps A/V in sync when the rounded frame hold differs from the WAV by a
    fraction of a frame; -frames:v caps the image2 reader to this beat.

    F3-T01: optional `vf` carries the cheap-filter chain (pad + animated
    crop + fade, never xfade/zoompan) inside this same single encode — the
    concat step stays `-c copy`, so cuts stay cuts."""
    cmd = [ffmpeg, "-y",
           "-framerate", str(_FPS), "-start_number", str(first_num),
           "-i", str(frames_dir / "frame_%06d.png"),
           "-i", str(wav)]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(_FPS),
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
    mid-segment), resume from the persisted current_segment.

    F3-T01: per-segment cheap motion (pad + animated crop + fade) inside the
    same single encode; concat stays `-c copy` (cuts stay cuts). Mapping
    queries below are read-only (overlay position, beat framing, chunk
    section) — planning/approval rows are never written here."""
    proj_db = None
    try:
        # Fail fast with a clear error naming everything tried (same
        # discipline as the Inkscape probe) — before any heavy frame work.
        try:
            ffmpeg, _ff_source, _ff_tried = _probe_ffmpeg()
        except FileNotFoundError as e:
            raise RuntimeError(str(e))
        # F3-T01 intensity (env only, read once so a mid-render env flip
        # cannot make the resume diverge from the fresh pass).
        motion = _motion_settings()
        proj_db = await get_project_db(folder)
        async with proj_db.execute(
            "SELECT id, duration_sec, chunk_id FROM beats WHERE project_id=? AND stale=0 "
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
        # D9-T02 single-renderer rule: overlay plates are drawn ONLY by
        # scenes._draw_overlays() via scene_preview() — this worker MUST NOT
        # grow its own ImageFont/ImageDraw text path (frames match previews
        # by byte-copy construction).
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
            resp = None
            # Phase 2 timed layers: a staging file splits this beat into
            # variant stills (one preview PNG per step, frames split at word
            # boundaries). No staging file = single span, old path exactly.
            from backend.core import staging as staging_mod
            try:
                staging_doc = staging_mod.load(base, beat_id)
            except ValueError as e:
                raise RuntimeError(f"beat {beat_id}: {e}")
            if staging_doc is None:
                step_spans = [{"hide": [], "hide_ov": [], "frames": need}]
            else:
                step_spans = staging_mod.spans(
                    staging_doc, beats[i].get("duration_sec"), need)
            span_srcs = []
            for _sp in step_spans:
                _hide = ",".join(str(x) for x in _sp["hide"])
                _hov = ",".join(str(x) for x in _sp.get("hide_ov") or [])
                _resp = await scenes_api.scene_preview(
                    project_id, beat_id, hide=_hide or None,
                    hide_ov=_hov or None)
                _src = Path(getattr(_resp, "path", "") or "")
                if (not _src.name or not _src.exists()
                        or _src.stat().st_size == 0):
                    raise RuntimeError(
                        f"beat {beat_id}: preview missing ({_src})")
                span_srcs.append((_src, _sp["frames"]))
            # F3-T01 mapping (read-only): first overlay position + framing
            # list + chunk section -> one slide direction; final beat also
            # fades out. Deterministic, so a resume re-encodes identically.
            async with proj_db.execute(
                    "SELECT position FROM scene_overlays WHERE beat_id=? "
                    "ORDER BY id LIMIT 1", (beat_id,)) as cur:
                orow = await cur.fetchone()
            overlay_pos = orow["position"] if orow else None
            async with proj_db.execute(
                    "SELECT framing FROM beat_elements WHERE beat_id=? "
                    "ORDER BY sort_order", (beat_id,)) as cur:
                framings = [(r["framing"] or "") for r in await cur.fetchall()]
            direction = _motion_direction(
                i, overlay_pos, framings, beats[i].get("chunk_id"))
            is_final = (i == total - 1)
            vf = (None if motion["off"] else _motion_vf(
                direction, need, is_final,
                motion["fade_in"], motion["fade_out"], motion["px"]))
            first_num = next_frame
            _off = 0
            for _src, _n in span_srcs:
                if _n > 0:
                    await asyncio.to_thread(
                        _write_beat_frames, _src, frames_dir,
                        first_num + _off, _n)
                _off += _n
            seg_path = segments_dir / f"seg_{i + 1:03d}.mp4"
            await asyncio.to_thread(
                _encode_segment, ffmpeg, frames_dir, first_num, need, wav, seg_path, vf)
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


# --- SCENES-MP4 D5+D10-T03: My Video output (list + serve versioned finals).
# Follows the existing FileResponse file-serving pattern (generation image,
# scenes preview): GET .../render/finals lists 08_handoff/<project>_final[_vN]
# .mp4 (never overwrite, so the list IS the version history); GET .../render
# /file/{filename} streams one MP4 for click-to-play + Download. Read-only —
# no DB writes, no render control, no new tables. Filename is validated
# against the versioned shape so no path can escape 08_handoff/.


def _final_version_key(name: str) -> tuple[int, str]:
    """Sort key: _final.mp4 first, then _v2, _v3, ... numerically."""
    m = re.match(r"^.+_final_v(\d+)\.mp4$", name)
    if m:
        return (int(m.group(1)), name)
    return (1, name)


def _is_valid_final_name(project_id: str, filename: str) -> bool:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return False
    if filename == f"{project_id}_final.mp4":
        return True
    return re.fullmatch(re.escape(project_id) + r"_final_v\d+\.mp4", filename) is not None


@router.get("/projects/{project_id}/render/finals")
async def render_finals(project_id: str):
    """Versioned finals list for the My Video screen. Reads 08_handoff/
    only (no DB writes); each entry plays + downloads via .../render/file/."""
    folder, _ = await _get_proj(project_id)
    base = Path(DATA_DIR) / "projects" / folder
    handoff_dir = base / "08_handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for p in handoff_dir.glob(f"{project_id}_final*.mp4"):
        if not p.is_file():
            continue
        if not _is_valid_final_name(project_id, p.name):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        if st.st_size == 0:
            continue
        files.append({"name": p.name, "rel": f"08_handoff/{p.name}",
                      "size": st.st_size,
                      "mtime": datetime.fromtimestamp(
                          st.st_mtime, tz=timezone.utc).isoformat()})
    files.sort(key=lambda f: (_final_version_key(f["name"]), f["mtime"]))
    latest = ""
    proj_db = await get_project_db(folder)
    try:
        job = await _latest_job_row(proj_db, project_id)
        if job:
            latest = job.get("output_path") or ""
    finally:
        await proj_db.close()
    return {"project_id": project_id, "finals": files, "latest": latest,
            "count": len(files)}


@router.get("/projects/{project_id}/render/file/{filename}")
async def render_file(project_id: str, filename: str):
    """Stream one finished MP4 (click-to-play + Download in My Video).
    Same FileResponse discipline as the PNG image endpoints."""
    folder, _ = await _get_proj(project_id)
    if not _is_valid_final_name(project_id, filename):
        raise HTTPException(404, "No such video")
    p = Path(DATA_DIR) / "projects" / folder / "08_handoff" / filename
    if not p.is_file() or p.stat().st_size == 0:
        raise HTTPException(404, "No such video")
    return FileResponse(p, media_type="video/mp4", filename=filename)


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
        f"{job['output_path']}; F3-T01 cheap motion inside each segment "
        f"encode only, concat stays -c copy; frames deleted per segment).")
    return out
