# backend/core/staging.py — timed-layer staging files (Phase 2, general).
#
# A staging file says what is visible WHEN inside one beat:
#   {"version": 1, "beat_id": "B01", "steps": [
#     {"t": 0.0, "hide": [], "note": "base tableau"},
#     {"t": 2.4, "hide": [12], "note": "map out on 'Brooklyn'"},
#   ]}
# hide = scene_assets need IDs hidden from that time on (cumulative per
# step is the author's job — each step lists the FULL hide set). Steps
# must start at t=0 and ascend. Files live at
# 07_beats/staging/{beat_id}.json (sidecars, never rows). Missing file =
# single step, current stills behavior untouched.
#
# Pure functions (no DB) so render + preview share them byte-identically.

import json
from pathlib import Path

STAGING_VERSION = 1
STAGING_SUBDIR = "07_beats/staging"


def staging_path(project_base: Path, beat_id: str) -> Path:
    return Path(project_base) / STAGING_SUBDIR / f"{beat_id}.json"


def validate(doc: dict) -> dict:
    """Raise ValueError on bad shape; return normalized doc."""
    if not isinstance(doc, dict):
        raise ValueError("staging must be an object")
    if doc.get("version") != STAGING_VERSION:
        raise ValueError(f"staging version must be {STAGING_VERSION}")
    beat = (doc.get("beat_id") or "").strip()
    if not beat:
        raise ValueError("staging beat_id must be non-empty")
    steps = doc.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("staging steps must be a non-empty list")
    norm = []
    prev_t = -1.0
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            raise ValueError(f"step {i} must be an object")
        try:
            t = float(s.get("t", 0.0))
        except (TypeError, ValueError):
            raise ValueError(f"step {i} t must be a number")
        if t < 0 or t <= prev_t:
            raise ValueError(f"step {i} t must ascend from 0 (got {t})")
        prev_t = t
        hide = s.get("hide") or []
        if not isinstance(hide, list) or any(
                not isinstance(x, int) for x in hide):
            raise ValueError(f"step {i} hide must be a list of need IDs")
        norm.append({"t": t, "hide": sorted(set(hide)),
                     "note": str(s.get("note") or "")})
    if norm[0]["t"] != 0.0:
        raise ValueError("first step t must be 0.0")
    return {"version": STAGING_VERSION, "beat_id": beat,
            "steps": norm}


def load(project_base: Path, beat_id: str) -> dict | None:
    """Validated staging doc, or None when no file (plain stills)."""
    p = staging_path(project_base, beat_id)
    if not p.exists():
        return None
    try:
        return validate(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError) as e:
        raise ValueError(f"bad staging {beat_id}: {e}")


def spans(doc: dict, duration_sec: float, total_frames: int) -> list:
    """Split a beat into [(hide, frame_count)] per staging step.

    Step k holds [t_k, t_{k+1}); the last holds to duration. Frame
    counts are proportional with rounding drift absorbed by the last
    span (sums to exactly total_frames). Pure function — unit-testable.
    """
    if total_frames <= 0:
        raise ValueError("total_frames must be positive")
    dur = max(float(duration_sec or 0.0), 0.01)
    steps = doc["steps"]
    bounds = [s["t"] for s in steps] + [dur]
    out, used = [], 0
    for k, s in enumerate(steps):
        t0 = min(max(bounds[k], 0.0), dur)
        t1 = min(max(bounds[k + 1], 0.0), dur)
        if k < len(steps) - 1:
            n = int(round((t1 - t0) / dur * total_frames))
            n = min(max(n, 0), total_frames - used)
        else:
            n = total_frames - used
        out.append({"hide": list(s["hide"]), "frames": n,
                    "t0": t0, "t1": t1})
        used += n
    return out
