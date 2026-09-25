# backend/core/llm_client.py
import asyncio
import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI

from backend.core import config
from backend.db.connection import get_app_db

# --- Rate Limiting ---
_MAX_CONCURRENT = 2
_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT)

async def _with_backoff(coro, max_retries=3, base_delay=2.0):
    """Execute coroutine with exponential backoff on 429/timeout."""
    delay = base_delay
    for attempt in range(max_retries + 1):
        try:
            return await coro
        except Exception as e:
            err_str = str(e).lower()
            is_rate = any(k in err_str for k in ("429", "rate limit", "quota", "timeout"))
            if not is_rate or attempt == max_retries:
                raise
            await asyncio.sleep(delay)
            delay *= 2

RECIPES_DIR = Path(__file__).resolve().parents[1] / "recipes"

# 4.3 Job Map - tier / temperature / stream per job type
JOB_MAP = {
    "ideation_refine":     {"tier": "high",   "temp": 0.8, "stream": False},
    "ideation":            {"tier": "high",   "temp": 0.9, "stream": True},
    "surprise_me":         {"tier": "high",   "temp": 0.9, "stream": False},
    "title_gen":           {"tier": "high",   "temp": 0.9, "stream": False},
    "title_variants":      {"tier": "high",   "temp": 0.9, "stream": False},
    "title_shorten":       {"tier": "medium", "temp": 0.4, "stream": False},
    "script_outline":      {"tier": "high",   "temp": 0.7, "stream": False},
    "outline_refine":      {"tier": "medium", "temp": 0.7, "stream": False},
    "script_draft":        {"tier": "high",   "temp": 0.7, "stream": True},
    "script_punchup":      {"tier": "high",   "temp": 0.7, "stream": False},
    "script_check":        {"tier": "medium", "temp": 0.2, "stream": False},
    "script_autosection":  {"tier": "medium", "temp": 0.2, "stream": False},
    "style_descriptor":    {"tier": "medium", "temp": 0.3, "stream": False},
    "character_extract":   {"tier": "high",   "temp": 0.3, "stream": False},
    "variant_extract":     {"tier": "high",   "temp": 0.3, "stream": False},
    "environment_extract": {"tier": "high",   "temp": 0.3, "stream": False},
    "world_scan":          {"tier": "medium", "temp": 0.2, "stream": False},
    "env_prompt":          {"tier": "high",   "temp": 0.5, "stream": False},
    "beat_split":          {"tier": "medium", "temp": 0.2, "stream": False},
    "beat_breakdown":      {"tier": "high",   "temp": 0.3, "stream": False},
    "beat_prompt":         {"tier": "high",   "temp": 0.5, "stream": False},
    "retention_analysis":  {"tier": "high",   "temp": 0.5, "stream": False},
    "lesson_proposal":     {"tier": "high",   "temp": 0.5, "stream": False},
    "overlay_text":        {"tier": "medium", "temp": 0.5, "stream": False},
    "scene_plan":          {"tier": "high",   "temp": 0.5, "stream": False},
    "asset_plan":          {"tier": "medium", "temp": 0.3, "stream": False},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def latest_version(job_type: str) -> int:
    """Highest saved version number for a recipe (1 when only the original exists)."""
    import re as _re
    found = [int(m.group(1)) for m in
             (_re.match(rf"^{_re.escape(job_type)}_v(\d+)\.txt$", p.name)
              for p in RECIPES_DIR.glob(f"{job_type}_v*.txt")) if m]
    return max(found) if found else 1


def load_recipe(job_type: str, version: int | None = None) -> str:
    # version=None -> newest. Editing a recipe in the Prompt Library writes a new
    # version, so everything must resolve to the latest or edits would be ignored.
    if version is None:
        version = latest_version(job_type)
    path = RECIPES_DIR / f"{job_type}_v{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Recipe missing: {path.name}")
    return path.read_text(encoding="utf-8")


def _client() -> AsyncOpenAI:
    s = config.load_settings()
    # This environment sets HTTP(S)_PROXY. The OpenAI SDK honours those vars,
    # so calls to a LOCAL endpoint get routed through the proxy and die with
    # APIConnectionError on larger (sharded) payloads while tiny ones survive.
    # LLM endpoints are user-configured and usually local -> bypass proxies.
    try:
        import httpx2
        http_client = httpx2.AsyncClient(trust_env=False)
    except Exception:
        http_client = None
    kwargs = {"http_client": http_client} if http_client is not None else {}
    return AsyncOpenAI(base_url=s["endpoint"], api_key=s["api_key"] or "missing-key", **kwargs)


def _model_for(tier: str) -> str:
    s = config.load_settings()
    return s["models"]["high"] if s.get("use_single_model") else s["models"][tier]


async def _chat(client, model, temp, messages, use_json=True):
    """One chat call. Tries JSON mode first, falls back if endpoint rejects it."""
    if use_json:
        try:
            resp = await client.chat.completions.create(
                model=model, messages=messages, temperature=temp,
                response_format={"type": "json_object"})
        except Exception:
            resp = await client.chat.completions.create(
                model=model, messages=messages, temperature=temp)
    else:
        resp = await client.chat.completions.create(
            model=model, messages=messages, temperature=temp)
    usage = getattr(resp, "usage", None)
    return (resp.choices[0].message.content or "",
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None))


def _validate(raw: str, schema):
    """schema=None -> free text job. Otherwise parse + Pydantic validate."""
    if schema is None:
        return raw, None
    try:
        data = json.loads(raw)
        return schema.model_validate(data).model_dump(), None
    except Exception as e:
        return None, str(e)


async def _log_job(job_type, model, temp, context, raw, parsed,
                   t_in, t_out, ms, error, project_id, channel_id, escalated=0):
    db = await get_app_db()
    await db.execute(
        """INSERT INTO job_log (project_id, channel_id, job_type, inputs, context_pack,
           model, temperature, raw_output, parsed_output, tokens_in, tokens_out,
           duration_ms, error, created_at, escalated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (project_id, channel_id, job_type, "{}", json.dumps(context), model, temp,
         raw, json.dumps(parsed) if parsed is not None else None,
         t_in, t_out, ms, error, now_iso(), 1 if escalated else 0))
    await db.commit()
    await db.close()


def _escalation_target(spec: dict, current_model: str):
    """Pick a stronger model when a cheap tier can't produce valid output.

    Returns None when there is nothing to escalate to: the job is already on the
    high tier, the user pinned a single model for everything, or the high tier
    resolves to the same model we just tried.
    """
    if spec["tier"] == "high":
        return None
    if config.load_settings().get("use_single_model"):
        return None
    candidate = _model_for("high")
    if not candidate or candidate == current_model:
        return None
    return candidate


async def dispatch(job_type: str, context: dict, schema=None,
                   project_id=None, channel_id=None, recipe_version=None):
    """Recipe + context pack -> call -> validate -> repair-retry once -> log.
    Rate-limited: max 2 concurrent, exponential backoff on 429."""
    async def _inner():
        spec = JOB_MAP.get(job_type)
        if spec is None:
            return {"ok": False, "error": f"Unknown job '{job_type}' - add it to JOB_MAP", "raw": ""}

        recipe = load_recipe(job_type, recipe_version)
        model = _model_for(spec["tier"])
        client = _client()

        messages = [
            {"role": "system", "content": recipe},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]

        start = time.time()
        try:
            raw, t_in, t_out = await _chat(client, model, spec["temp"], messages)
        except Exception as e:
            await _log_job(job_type, model, spec["temp"], context, "", None,
                           None, None, 0, str(e), project_id, channel_id)
            return {"ok": False, "error": f"LLM connection failed: {e}", "raw": ""}

        parsed, error = _validate(raw, schema)

        if error is not None:
            # Repair-retry ONCE
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                             f"Your output failed validation: {error}\nReturn ONLY corrected JSON."})
            raw, t_in2, t_out2 = await _chat(client, model, spec["temp"], messages)
            t_in = (t_in or 0) + (t_in2 or 0)
            t_out = (t_out or 0) + (t_out2 or 0)
            parsed, error = _validate(raw, schema)
            if error is not None:
                # Auto-escalation: cheap models routinely fail structured output.
                # Instead of dying, retry once on the strongest tier so the default
                # stays cheap but the stage still completes.
                esc_model = _escalation_target(spec, model)
                if esc_model is not None:
                    try:
                        raw, t_in3, t_out3 = await _chat(client, esc_model, spec["temp"], messages)
                        t_in = (t_in or 0) + (t_in3 or 0)
                        t_out = (t_out or 0) + (t_out3 or 0)
                        parsed, error = _validate(raw, schema)
                    except Exception as e:
                        error = f"{error} | escalation call failed: {e}"
                    await _log_job(job_type, esc_model, spec["temp"], context, raw, parsed,
                                   t_in, t_out, int((time.time() - start) * 1000),
                                   error if error else None, project_id, channel_id,
                                   escalated=1)
                    if error is None:
                        return {"ok": True, "parsed": parsed, "raw": raw, "escalated": True}
                    return {"ok": False, "error": error, "raw": raw, "escalated": True}

                await _log_job(job_type, model, spec["temp"], context, raw, None,
                               t_in, t_out, int((time.time() - start) * 1000), error,
                               project_id, channel_id)
                return {"ok": False, "error": error, "raw": raw}

        await _log_job(job_type, model, spec["temp"], context, raw, parsed,
                       t_in, t_out, int((time.time() - start) * 1000), None,
                       project_id, channel_id)
        return {"ok": True, "parsed": parsed, "raw": raw}

    async with _SEMAPHORE:
        return await _with_backoff(_inner())


async def dispatch_stream(job_type: str, context: dict,
                          project_id=None, channel_id=None, recipe_version=None):
    """Async generator yielding SSE frames for streamed jobs. Rate-limited."""
    async def _inner():
        spec = JOB_MAP.get(job_type)
        if spec is None:
            yield f"data: {json.dumps({'error': f'Unknown job {job_type}'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        recipe = load_recipe(job_type, recipe_version)
        model = _model_for(spec["tier"])
        client = _client()

        messages = [
            {"role": "system", "content": recipe},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]

        start = time.time()
        collected = []
        try:
            stream = await client.chat.completions.create(
                model=model, messages=messages, temperature=spec["temp"], stream=True)
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    collected.append(delta)
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
        except Exception as e:
            await _log_job(job_type, model, spec["temp"], context, "".join(collected),
                           None, None, None, int((time.time() - start) * 1000),
                           str(e), project_id, channel_id)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        raw = "".join(collected)
        await _log_job(job_type, model, spec["temp"], context, raw, raw,
                       None, None, int((time.time() - start) * 1000), None,
                       project_id, channel_id)
        yield "data: [DONE]\n\n"

    # NOTE: _with_backoff() expects a coroutine, but _inner() is an async
    # generator -> wrapping it produced "async for ... got coroutine".
    # Streams can't be retried mid-flight anyway, and _inner() already
    # yields its own error frames, so just gate on the semaphore here.
    async with _SEMAPHORE:
        async for frame in _inner():
            yield frame


async def dispatch_vision(job_type, image_paths, context, schema=None,
                          project_id=None, channel_id=None):
    """Vision job: recipe + images as base64. Free-text output (no JSON mode). Rate-limited."""
    async def _inner():
        spec = JOB_MAP.get(job_type)
        if spec is None:
            return {"ok": False, "error": f"Unknown vision job '{job_type}' - add it to JOB_MAP", "raw": ""}

        recipe = load_recipe(job_type)
        model = _model_for(spec["tier"])
        client = _client()

        user_content = [{"type": "text", "text": json.dumps(context)}]
        for p in image_paths:
            with open(p, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
            ext = Path(p).suffix.lower().lstrip(".")
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "webp": "image/webp"}.get(ext, "image/png")
            user_content.append({"type": "image_url",
                                 "image_url": {"url": f"data:{mime};base64,{b64}"}})

        messages = [
            {"role": "system", "content": recipe},
            {"role": "user", "content": user_content},
        ]

        start = time.time()
        try:
            raw, t_in, t_out = await _chat(client, model, spec["temp"], messages, use_json=False)
        except Exception as e:
            await _log_job(job_type, model, spec["temp"], context, "", None,
                           None, None, 0, str(e), project_id, channel_id)
            return {"ok": False, "error": f"Vision call failed: {e}", "raw": ""}

        await _log_job(job_type, model, spec["temp"], context, raw, raw,
                       t_in, t_out, int((time.time() - start) * 1000), None,
                       project_id, channel_id)
        return {"ok": True, "parsed": raw, "raw": raw}

    async with _SEMAPHORE:
        return await _with_backoff(_inner())
