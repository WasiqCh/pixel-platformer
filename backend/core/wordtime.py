# backend/core/wordtime.py — word timing for timed layers (Phase 1).
#
# Uses the SYSTEM whisper CLI (openai-whisper + torch live outside the venv;
# see runbook §2.6) — never installs models into the app venv. Resolution:
# WHISPER_BIN env -> PATH -> verified default (same discipline as the
# Kokoro weight paths in voiceover.py). Force-align logic is a headless
# port of audio_prep_engine 2.0.py::force_align_script (dependency-free).
# GUI, merging, and SRT-writing from that tool are intentionally left out:
# our beats ARE the chunks, and the pipeline needs JSON word lists.

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_DEFAULT_BIN = r"C:\Users\wasiq\AppData\Roaming\Python\Python314\Scripts\whisper.exe"


def resolve_bin() -> str:
    """Find the whisper CLI. Raises FileNotFoundError with the fix."""
    env = (os.environ.get("WHISPER_BIN") or "").strip().strip('"')
    if env and Path(env).is_file():
        return env
    found = shutil.which("whisper")
    if found:
        return found
    if Path(_DEFAULT_BIN).is_file():
        return _DEFAULT_BIN
    raise FileNotFoundError(
        "whisper CLI not found. Install it in system python: "
        "pip install openai-whisper (needs torch) — then ensure "
        "'whisper' is on PATH or set WHISPER_BIN.")


def transcribe_cli(wav_path: str | Path, model: str = "base",
                   workdir: str | Path | None = None) -> list:
    """Run whisper CLI with word timestamps. Returns raw segments list."""
    wav = str(wav_path)
    if not Path(wav).is_file():
        raise FileNotFoundError(f"audio not found: {wav}")
    outdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="wordtime_"))
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [resolve_bin(), wav, "--model", model, "--output_format", "json",
           "--word_timestamps", "True", "--output_dir", str(outdir),
           "--fp16", "False", "--verbose", "False"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise RuntimeError("whisper timed out after 600s")
    if r.returncode != 0:
        raise RuntimeError(f"whisper exit {r.returncode}: {(r.stderr or r.stdout or '')[-300:]}")
    stem = Path(wav).stem
    js = outdir / f"{stem}.json"
    if not js.exists():
        cands = sorted(outdir.glob("*.json"))
        if not cands:
            raise RuntimeError("whisper produced no JSON (nothing written).")
        js = cands[0]
    return json.loads(js.read_text(encoding="utf-8")).get("segments") or []


def clean_word(word: str) -> str:
    return re.sub(r"[^\w\s]", "", word or "").lower().strip()


def force_align_words(segments: list, script_text: str) -> tuple[list, dict]:
    """Align pristine script words onto whisper word timestamps.

    Returns (words, stats) where words = [{word, start, end}] in script
    order and stats = {matched, spread, total} (matched = exact whisper
    hits, spread = evenly-interpolated fallbacks).
    """
    import difflib
    whisper_words = []
    for seg in segments or []:
        for w in (seg.get("words") or []):
            whisper_words.append({
                "raw": (w.get("word") or "").strip(),
                "clean": clean_word(w.get("word") or ""),
                "start": float(w.get("start") or 0.0),
                "end": float(w.get("end") or 0.0),
            })
    script_raw = (script_text or "").split()
    script_clean = [clean_word(w) for w in script_raw]
    whisper_clean = [w["clean"] for w in whisper_words]
    matcher = difflib.SequenceMatcher(None, whisper_clean, script_clean)
    aligned, matched, spread = [], 0, 0
    for tag, ws, we, ss, se in matcher.get_opcodes():
        if tag == "equal":
            for i in range(se - ss):
                aligned.append({
                    "word": script_raw[ss + i],
                    "start": whisper_words[ws + i]["start"],
                    "end": whisper_words[ws + i]["end"],
                })
                matched += 1
        elif tag in ("replace", "insert"):
            if ws < len(whisper_words) and ws < we:
                t_start = whisper_words[ws]["start"]
                t_end = whisper_words[we - 1]["end"]
            else:
                t_start = aligned[-1]["end"] if aligned else 0.0
                t_end = t_start + 0.5
            n = se - ss
            per = (t_end - t_start) / max(1, n)
            for i in range(n):
                aligned.append({
                    "word": script_raw[ss + i],
                    "start": t_start + i * per,
                    "end": t_start + (i + 1) * per,
                })
                spread += 1
        # tag == 'delete': whisper-only noise, ignored.
    return aligned, {"matched": matched, "spread": spread, "total": len(script_raw)}


def align_wav(wav_path: str | Path, script_text: str,
              model: str = "base") -> tuple[list, dict]:
    """One call: transcribe + force-align. Returns (words, stats)."""
    segments = transcribe_cli(wav_path, model=model)
    return force_align_words(segments, script_text)
