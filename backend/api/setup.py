# backend/api/setup.py
# SCENES-MP4 D5+D10-T02: Setup screen (first-run green ticks + one-click fix).
#
# New screen auto-opens (App.jsx) when anything here is missing. Every check
# reuses an EXISTING probe — never a typed path, never a hard-coded binary:
#   packages  = fresh import of every requirements.txt module
#   inkscape  = generation._probe_inkscape (INKSCAPE_PATH -> PATH -> MSIX)
#               + classic-installer fallback (%PROGRAMFILES%\Inkscape\...)
#   ffmpeg    = render._probe_ffmpeg (FFMPEG_PATH -> PATH)
#   kokoro    = voiceover._kokoro_probe (deps import + D4-T01 weight paths) +
#               espeak smoke via kokoro_onnx.tokenizer.Tokenizer (D4-T01 §b:
#               phonemize ONLY through Tokenizer, never raw phonemizer)
# Each missing item gets ONE Fix button: winget for binaries, pip for
# packages, direct download for weights (to the KOKORO_MODEL / KOKORO_VOICES
# resolved paths — D4-T01 defaults, never typed by the user). Every fix ends
# with the SAME probe the status uses (re-probe after fix).
# No DB, no AI calls, no new tables.

import asyncio
import glob as _glob
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["setup"])

_REPO_ROOT = Path(__file__).resolve().parents[2]

# module -> pip dist (for the missing-list message + pip fix)
_BASE_PACKAGES: list[tuple[str, str]] = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("openai", "openai"),
    ("PIL", "pillow"),
    ("multipart", "python-multipart"),
    ("sse_starlette", "sse-starlette"),
    ("aiosqlite", "aiosqlite"),
    ("pydantic", "pydantic"),
    ("httpx", "httpx"),
]
_KOKORO_PIP = ["kokoro-onnx", "onnxruntime"]
_KOKORO_MODEL_URL = ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
                     "model-files-v1.0/kokoro-v1.0.onnx")
_KOKORO_VOICES_URL = ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
                      "model-files-v1.0/voices-v1.0.bin")
_KOKORO_MODEL_MIN = 100_000_000
_KOKORO_VOICES_MIN = 10_000_000

_WINGET_INKSCAPE = "Inkscape.Inkscape"
_WINGET_FFMPEG = "Gyan.FFmpeg"

_OUT_TAIL = 2000


def _tail(s: str, n: int = _OUT_TAIL) -> str:
    s = s or ""
    return s[-n:] if len(s) > n else s


def _check_packages() -> dict:
    """Fresh-import every base requirement (sys.modules evicted first so a
    pip uninstall/reinstall inside one server lifetime reads honestly)."""
    missing: list[str] = []
    for module, dist in _BASE_PACKAGES:
        sys.modules.pop(module, None)
        try:
            importlib.invalidate_caches()
            importlib.import_module(module)
        except Exception:
            missing.append(dist)
    if missing:
        return {"ok": False,
                "detail": "missing: " + ", ".join(missing),
                "fix_label": "Install packages (pip)",
                "fix_command": f"{sys.executable} -m pip install -r requirements.txt"}
    return {"ok": True,
            "detail": f"{len(_BASE_PACKAGES)}/{len(_BASE_PACKAGES)} importable (fresh)",
            "fix_label": "Install packages (pip)",
            "fix_command": f"{sys.executable} -m pip install -r requirements.txt"}


def _check_inkscape() -> dict:
    from backend.api.generation import _probe_inkscape
    fix_cmd = (f"winget install --id {_WINGET_INKSCAPE} -e --silent "
               "--accept-package-agreements --accept-source-agreements")
    try:
        path, source, _tried = _probe_inkscape()
        return {"ok": True, "detail": f"found via {source}: {path}",
                "fix_label": "Install Inkscape (winget)", "fix_command": fix_cmd}
    except FileNotFoundError as e:
        tried = str(e)
    # Classic (non-Store) installer fallback — probed, never hard-coded as
    # the only path; the existing MSIX probe above stays untouched.
    classic = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                           "Inkscape", "bin", "inkscape.exe")
    if os.path.isfile(classic):
        return {"ok": True, "detail": f"found via classic-path: {classic}",
                "fix_label": "Install Inkscape (winget)", "fix_command": fix_cmd}
    return {"ok": False, "detail": tried + f" | classic-path {classic}: not found",
            "fix_label": "Install Inkscape (winget)", "fix_command": fix_cmd}


def _check_ffmpeg() -> dict:
    from backend.api.render import _probe_ffmpeg
    fix_cmd = (f"winget install --id {_WINGET_FFMPEG} -e --silent "
               "--accept-package-agreements --accept-source-agreements")
    try:
        path, source, _tried = _probe_ffmpeg()
        return {"ok": True, "detail": f"found via {source}: {path}",
                "fix_label": "Install FFmpeg (winget)", "fix_command": fix_cmd}
    except FileNotFoundError as e:
        return {"ok": False, "detail": str(e),
                "fix_label": "Install FFmpeg (winget)", "fix_command": fix_cmd}


def _check_kokoro() -> dict:
    from backend.api.voiceover import _kokoro_probe
    probe = _kokoro_probe()
    if not probe.get("available"):
        reason = probe.get("reason", "kokoro unavailable")
        if "weights missing" in reason or "model missing" in reason:
            model_path = probe.get("model_path", "")
            voices_path = probe.get("voices_path", "")
            return {"ok": False,
                    "detail": reason,
                    "fix_label": "Download Kokoro weights (~340 MB)",
                    "fix_command": f"download weights -> {model_path} + {voices_path}",
                    "_fix_kind": "kokoro-weights"}
        return {"ok": False,
                "detail": reason,
                "fix_label": "Install Kokoro packages (pip)",
                "fix_command": f"{sys.executable} -m pip install {' '.join(_KOKORO_PIP)}",
                "_fix_kind": "kokoro-packages"}
    # Deps + weights present — espeak smoke through the app path (D4-T01 §b).
    try:
        from kokoro_onnx.tokenizer import Tokenizer
        text = Tokenizer().phonemize("Setup check.")
        espeak = f"espeak ok ({len(text)} chars phonemized)"
    except Exception as e:
        return {"ok": False,
                "detail": f"weights present but espeak phonemize failed: {type(e).__name__}: {str(e)[:200]}",
                "fix_label": "Install Kokoro packages (pip)",
                "fix_command": f"{sys.executable} -m pip install {' '.join(_KOKORO_PIP)}",
                "_fix_kind": "kokoro-packages"}
    n = len(probe.get("voices") or [])
    return {"ok": True,
            "detail": f"kokoro-onnx + onnxruntime import cleanly, weights present, {n} voices, {espeak}",
            "fix_label": "Install Kokoro packages (pip)",
            "fix_command": f"{sys.executable} -m pip install {' '.join(_KOKORO_PIP)}",
            "_fix_kind": "kokoro-ok"}


_CHECKS: list[tuple[str, str]] = [
    ("packages", "Python packages (app brain)"),
    ("inkscape", "Inkscape (art → PNG)"),
    ("ffmpeg", "FFmpeg (video + sound mux)"),
    ("kokoro", "Kokoro voice (free narration)"),
    ("ollama", "Ollama (local AI)"),
    ("whisper", "Whisper CLI (word timing)"),
]


async def _run_check(check_id: str) -> dict:
    if check_id == "packages":
        body = await asyncio.to_thread(_check_packages)
    elif check_id == "inkscape":
        body = await asyncio.to_thread(_check_inkscape)
    elif check_id == "ffmpeg":
        body = await asyncio.to_thread(_check_ffmpeg)
    elif check_id == "kokoro":
        body = await asyncio.to_thread(_check_kokoro)
    elif check_id == "whisper":
        body = await asyncio.to_thread(_check_whisper)
    else:
        raise HTTPException(404, f"unknown setup check: {check_id}")
    label = dict(_CHECKS)[check_id]
    out = {"id": check_id, "label": label, "ok": body["ok"], "detail": body["detail"],
           "fix_label": body["fix_label"], "fix_command": body["fix_command"]}
    if "_fix_kind" in body:
        out["_fix_kind"] = body["_fix_kind"]
    return out


@router.get("/setup/status")
async def setup_status():
    """Probe everything a fresh machine needs. Never asks for a path."""
    checks = [await _run_check(cid) for cid, _label in _CHECKS]
    for c in checks:
        c.pop("_fix_kind", None)
    return {"all_ok": all(c["ok"] for c in checks), "checks": checks}


def _run_cmd(argv: list[str], timeout: int) -> tuple[int, str]:
    """Blocking subprocess runner (always called via asyncio.to_thread)."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.returncode, _tail((r.stdout or "") + ("\n" + r.stderr if r.stderr else ""))
    except subprocess.TimeoutExpired as e:
        return 124, _tail(f"timed out after {timeout}s: " + str((e.stdout or "") + (e.stderr or ""))[:500])
    except Exception as e:
        return 127, f"{type(e).__name__}: {str(e)[:300]}"


def _refresh_path_from_registry() -> str:
    """Pick up PATH entries a just-run installer wrote (current process would
    otherwise stay blind until restart). HKCU + HKLM merged, existing kept."""
    notes = []
    try:
        import winreg
        fresh: list[str] = []
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                fresh.append(winreg.QueryValueEx(k, "Path")[0])
        except OSError:
            pass
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as k:
                fresh.append(winreg.QueryValueEx(k, "Path")[0])
        except OSError:
            pass
        if fresh:
            merged = ";".join(fresh)
            for part in os.environ.get("PATH", "").split(";"):
                if part and part.lower() not in merged.lower():
                    merged += ";" + part
            os.environ["PATH"] = merged
            notes.append("PATH refreshed from registry")
    except Exception as e:
        notes.append(f"PATH refresh skipped: {type(e).__name__}")
    return "; ".join(notes) or "no PATH refresh needed"


def _fix_packages_sync() -> tuple[bool, str]:
    req = _REPO_ROOT / "requirements.txt"
    code, out = _run_cmd([sys.executable, "-m", "pip", "install", "-r", str(req)], timeout=600)
    ok = code == 0
    return ok, (f"pip exit {code}\n{out}" if not ok
                else f"pip install ok (already-satisfied is fine)\n{out}")


def _fix_kokoro_packages_sync() -> tuple[bool, str]:
    code, out = _run_cmd([sys.executable, "-m", "pip", "install", *_KOKORO_PIP], timeout=600)
    return code == 0, f"pip exit {code}\n{out}"


def _download_file_sync(url: str, dest: Path, min_size: int) -> str:
    import httpx
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (dest.name + ".part")
    # External host: default trust_env so a configured proxy is honored
    # (the trust_env=False bypass in llm_client is for LOCAL endpoints only).
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1 << 20):
                f.write(chunk)
    size = tmp.stat().st_size
    if size < min_size:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded {size}B < minimum {min_size}B — refusing to install")
    os.replace(tmp, dest)
    return f"{dest.name} {size}B"


def _fix_kokoro_weights_sync() -> tuple[bool, str]:
    from backend.api.voiceover import _kokoro_paths
    model_path, voices_path = _kokoro_paths()
    try:
        got_model = ("present" if os.path.isfile(model_path) else
                     _download_file_sync(_KOKORO_MODEL_URL, Path(model_path), _KOKORO_MODEL_MIN))
        got_voices = ("present" if os.path.isfile(voices_path) else
                      _download_file_sync(_KOKORO_VOICES_URL, Path(voices_path), _KOKORO_VOICES_MIN))
        return True, f"model: {got_model}\nvoices: {got_voices}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:400]}"


def _fix_winget_sync(pkg_id: str) -> tuple[bool, str]:
    argv = ["winget", "install", "--id", pkg_id, "-e", "--silent",
            "--accept-package-agreements", "--accept-source-agreements"]
    code, out = _run_cmd(argv, timeout=600)
    note = _refresh_path_from_registry()
    # winget exit 0 OR "already installed" text both mean the bits exist.
    already = "already installed" in out.lower() or "no newer version" in out.lower()
    return (code == 0 or already), f"{' '.join(argv)}\nexit {code}\n{note}\n{out}"


def _check_whisper() -> dict:
    """Whisper CLI for word timing (runbook §2.6). System-python install —
    the venv must NOT carry torch, so this probes PATH only (same rule as
    the requirements.txt comment). Backend resolves it via WHISPER_BIN."""
    fix_cmd = "py -m pip install openai-whisper"
    which = shutil.which("whisper")
    if which and os.path.isfile(which):
        return {"ok": True, "detail": f"found via PATH: {which}",
                "fix_label": "Install Whisper (system python)",
                "fix_command": fix_cmd}
    return {"ok": False, "detail": "whisper not on PATH (tried PATH lookup)",
            "fix_label": "Install Whisper (system python)",
            "fix_command": fix_cmd}


def _fix_whisper_sync() -> tuple[bool, str]:
    code, out = _run_cmd(["py", "-m", "pip", "install", "openai-whisper"],
                         timeout=600)
    note = _refresh_path_from_registry()
    return code == 0, f"py -m pip install openai-whisper\nexit {code}\n{note}\n{out}"


@router.post("/setup/fix/{check_id}")
async def setup_fix(check_id: str):
    """Run ONE fix for a missing item, then re-probe with the same probe the
    status uses. Already-green items short-circuit (no reinstall)."""
    if check_id not in dict(_CHECKS):
        raise HTTPException(404, f"unknown setup check: {check_id}")
    before = await _run_check(check_id)
    if before["ok"]:
        recheck = {k: v for k, v in before.items() if not k.startswith("_")}
        return {"ok": True, "fixed": False,
                "detail": "already ok — no action, re-probed green",
                "output": before["detail"], "recheck": recheck}
    if check_id == "packages":
        wok, out = await asyncio.to_thread(_fix_packages_sync)
    elif check_id == "inkscape":
        wok, out = await asyncio.to_thread(_fix_winget_sync, _WINGET_INKSCAPE)
    elif check_id == "ffmpeg":
        wok, out = await asyncio.to_thread(_fix_winget_sync, _WINGET_FFMPEG)
    elif check_id == "kokoro":
        kind = before.get("_fix_kind", "kokoro-packages")
        if kind == "kokoro-weights":
            wok, out = await asyncio.to_thread(_fix_kokoro_weights_sync)
        else:
            wok, out = await asyncio.to_thread(_fix_kokoro_packages_sync)
    elif check_id == "whisper":
        wok, out = await asyncio.to_thread(_fix_whisper_sync)
    else:
        raise HTTPException(404, f"unknown setup check: {check_id}")
    after = await _run_check(check_id)
    after.pop("_fix_kind", None)
    green = after["ok"]
    return {"ok": green, "fixed": wok,
            "detail": ("fixed + re-probed green" if green
                       else "fix ran but re-probe still red — see output, then Re-check"),
            "output": _tail(out), "recheck": after}
