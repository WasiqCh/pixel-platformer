# DECISIONS.md — Locked Architecture Decisions

## Flow (unchanged)
- **S01 Idea** → **S02 Titles** → **S03 Script Studio (lock)** → **S04 Characters** → **S05 Environments** → **S06 World Desk** → **S09 Beat Board** → **S11 Library** → **S12 Export**

## Extraction (unchanged, UX improvements only)
- Staged extracts: Cast → Locations → World → Beats (separate buttons)
- UX: show progress, allow retry, better error messages

## Image Generation
- Code stays (Nano Banana / Gemini image)
- **Default provider = `manual`** (disabled)
- User enables later via Settings → add API key → switch provider
- No background generation unless explicitly triggered

## Rate Limiting (IMPLEMENT NOW)
- **In-process semaphore**: max 2 concurrent LLM requests
- **Exponential backoff** on 429 / timeout: 2s → 4s → 8s → 16s (max 3 retries)
- Applies to all LLM calls: script, cast, locations, world, beats, prompts
- Configurable via env var later if needed

## CSV Export
- **DEFERRED** — decide format later
- Will export from Beat Board (S09) or Export (S12)

## LLM Providers
- Current: Gemini (configurable via settings)
- Keep multi-provider ready (settings screen exists)
- No new provider work now

---

## Immediate Next Steps
1. Add `LLMSemaphore` class (max 2, backoff) to `backend/core/llm_client.py`
2. Wrap all `sharded_extract` / LLM calls with it
3. Test S04 extract with rate limiting
4. Then proceed beat-by-beat through the pipeline