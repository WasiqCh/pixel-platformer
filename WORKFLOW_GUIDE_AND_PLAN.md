# Pixel Platformer — Workflow Guide, Audit & Improvement Plan

*Written 2026-09-18 after a full end-to-end test run of the pipeline.*

---

## Part 1 — What this app actually does (plain English)

Think of it as a **factory that turns one idea into a pile of copy-paste-ready image
prompts** for a YouTube video. It does **not** make the images. It makes the
*instructions* for making them, keeps them consistent, and tracks which ones you've
already done.

You supply: an idea.
You get out: a locked script, a cast list, a location list, sprite-sheet prompts,
and one prompt per camera shot — plus a checklist that stops you exporting early.

### The 14 stages, in order

| # | Stage | What happens | Uses AI? |
|---|---|---|---|
| 1 | **Channel** | Your brand. Holds the style-kit (the "MS Paint look") that every later image inherits. | No |
| 2 | **Project** | One episode. Everything below belongs to it. | No |
| 3 | **Ideas** | AI proposes concepts from a one-line input. You lock one. | Yes |
| 4 | **Titles** | AI writes title candidates for the locked idea. You lock one. | Yes |
| 5 | **Outline** | AI expands the title into sections with target word counts. | Yes |
| 6 | **Script** | AI writes the narration, section by section (streamed). You lock it. | Yes |
| 7 | **Cast Board** | AI reads the whole script and lists every character + what they look like + **which poses they need**. | Yes |
| 8 | **Variants** | Major appearance changes for a character (age, outfit, wounded). Same character, new look. | Yes |
| 9 | **Locations** | AI lists every distinct place in the script and its 3–4 elements. | Yes |
| 10 | **World Desk** | Real-world things needing care: real people, brands, maps. Also decides "draw it" vs "fetch a photo". | Yes |
| 11 | **Beats** | The script is cut into ~10-word camera shots. Each beat gets its own prompt. | Yes |
| 12 | **Sheets** | Builds the sprite-sheet prompt for each character and location. | No (assembles) |
| 13 | **Generation Queue** | One row per image to make, with the full prompt and the reference image to attach. | No |
| 14 | **Checkpoint → Handoff** | Checklist gate, then export package (EDL, subtitles, manifest). | No |

**The key idea:** stages 7–9 read the *entire* script before deciding anything, so a
character who only appears at the end still gets planned from the start. And every
image prompt references a previously-approved image, so the AI can't drift the look.

---

## Part 2 — What I found

### Things that were genuinely broken (now fixed)

| Problem | Root cause | Fix |
|---|---|---|
| Creating a channel failed with "Unexpected end of JSON input" | Vite proxied `/api` to port **8000**; backend runs on **8100** | Proxy target corrected |
| Backend wouldn't boot | `httpx` missing from the venv (added in sprint-9, venv predates it) | Installed + pinned `httpx==0.28.1` |
| "Compose prompts" → 500 | `KeyError: 'RW01'` — counter seeded from characters only, but world records also count as dynamic assets | Use `.get(ref, 0)` |
| Script writing silently broken | `async for` over a coroutine in `dispatch_stream` | Streams iterate directly; they can't be retried mid-flight anyway |
| LLM calls failed on big jobs but passed on small ones | `HTTP_PROXY` is set in this environment; the OpenAI SDK routed your **localhost** LLM through it | `trust_env=False` on the LLM client |
| Extractions failed with 18–22 validation errors | Cheap models return objects where the recipe asked for a sentence | Tolerant validators (see Part 5) |
| Ghost sprite sheets | Old 6+3 splits left `C01_S2_sheet.md` behind after re-extraction | Clear stale sheets before writing |

### The sprite-sheet sizing you asked about

- **Environment sheets were 9 panels each** — and worse, they were 9 *generic* panels
  (dawn, noon, dusk, weather, texture, silhouette…) that ignored the variations the AI
  had already extracted from your script. The AI did the work; the code threw it away.
  Now: **2 states of one location**, using your script's real variations.
- **Character sheets** used 9 hardcoded poses split 6+3 into two sheets. Now the **AI
  chooses 2–6 poses** based on what that character actually does. Real result:
  Vasco da Gama got 5 story-specific poses; a minor monster got 2.
  Net effect: **6 characters → 6 sheets** (was 7 characters → 14 sheets).

### Things that are fine but invisible

- **Your prompt system is well-built.** 18 versioned recipe files in
  `backend/recipes/`, one per AI job, with model tier and temperature per job, and
  every call logged to `job_log`. I verified **all 18 jobs in use have a recipe**.
  You couldn't tell because there is **no UI to see them** — zero references to
  "recipe" in the frontend. That's the whole reason it felt unmanaged.
- **6 job types are unimplemented** — no recipe, no call site:
  `beat_split`, `beat_prompt`, `env_prompt`, `overlay_text`, `retention_analysis`,
  `lesson_proposal`. Harmless dead entries, but they look like features in the code.

### Environment quirks worth knowing

- `uvicorn --reload` watches the whole repo including `node_modules` (1700+ files) and
  **silently misses edits**. Three "my fix didn't work" scares were stale code.
  Use `--reload-dir backend`.
- Always `curl --noproxy '*'` when probing localhost — a proxy makes it look down.
- Wikimedia auto-search 403s are **rate limiting**, not a bug. Needs retry/backoff.

---

## Part 3 — Improvements to the existing workflow

**A. Show the prompts.** A "Prompt Library" screen listing the 18 recipes: which stage
uses each, the model/temperature, and an editable text box. This is the single highest
value change — it converts your biggest complaint into a non-issue.

**B. Collapse 14 stages into ~6.** Several stages are configuration, not production:
- Variants (8) and World Desk (10) are usually empty and could be *optional drawers*
  on the Cast Board rather than their own screens.
- Sheets (12) and the Generation Queue (13) are the same concern — "the prompts" —
  and should be one screen.
- Outline (5) can fold into Script (6).
Proposed: **Idea → Script → Cast & World → Sheets & Prompts → Generate → Export.**

**C. Make the "ready" gate match an external workflow.** You generate images outside
the app, so the checkpoint's "0/9 assets ready" will always nag. Add a manual
"I generated this outside" mark-ready button, or make it advisory only.

**D. Fix the port documentation.** `BUILD_PLAN.md` and `implementation_plan.md` still
say port 8000. That stale doc is what caused the channel-creation bug.

**E. Delete or build the 6 dead jobs.** Dead entries in `JOB_MAP` read like features.

---

## Part 4 — New things worth adding

1. **Draft-then-final generation.** Generate a cheap low-res pass first, approve
   composition, then do the full-res run. Your own spec lists this as unbuilt. Saves
   the most money of anything here.
2. **Prompt diff view.** When you edit a recipe, show what changed in output for one
   sample beat *before* re-running everything.
3. **Cost/asset budget per episode.** Count generations and estimated spend up front.
4. **Cross-episode reuse.** Your spec wants a shared library of generic assets
   (crowds, recurring host). The vault exists; the "check library first" step doesn't.
5. **Seed/model/prompt capture per asset** (spec §13). Store model version, seed, and
   exact prompt text with each generated image so you can reproduce a good one.
6. **Import path for external images.** Since you generate outside, a drag-and-drop
   "attach image to this queue row" is the missing half. The upload endpoints exist;
   they just aren't wired into the queue UI.

---

## Part 5 — Deferred: cheap-model robustness (your last priority)

You asked about rate limits, retries, and prompt dividing for models that forget and
hallucinate. Here's the honest read, saved for later.

**What already exists:**
- Exponential backoff, 3 retries, on 429/rate-limit/timeout (`_with_backoff`).
- Max 2 concurrent LLM calls (semaphore).
- One "repair retry": if JSON fails validation, the error is fed back and it tries once.
- Sharding: scripts over 4,000 words are split into overlapping chunks.

**What's weak:**
- **Streaming has no retry protection.** I removed the broken wrapper; a dropped stream
  mid-script currently just fails.
- **Sharding only applies to extraction, not to title/outline/beat jobs.** Long inputs
  there go in one giant call.
- **One repair attempt only.** Cheap models often need 2–3, or a smaller ask.
- **No prompt-size tapering.** The same recipe is sent regardless of model quality.
- **No "narrow the ask" fallback** — e.g. re-asking for 3 fields instead of 9 when the
  model keeps failing.
- **Validation is all-or-nothing.** Today one bad field can fail a whole extraction.
  I patched this defensively for characters and world records; the other 16 recipes
  have no such protection.

**Recommended sequence when you're ready:**
1. Extract the tolerant-validator pattern into one shared helper; apply to all models.
2. Add partial-success parsing — keep the 8 good records, drop the 2 bad ones.
3. Add per-model profiles (max tokens, temperature, retry count, sharding on/off).
4. Extend sharding to every long-input job, not just extraction.
5. Add a 3rd repair attempt that shrinks the requested schema.

---

## Appendix — End-to-end test result (2026-09-18)

Ran a fresh channel → project → idea → title → outline → script → cast → variants →
locations → world → beats → sheets → prompts → checkpoint → handoff → export.

**23/23 stages passed.** Real output: 4 characters, 5 environments, 11 beats, 19 beat
elements, 15 generations, 9 library slots, 4 world records, checkpoint advanced to
`ready_for_handoff`, export produced EDL + SRT + manifest.

Two failures found and fixed during the run (world-scan validation, checkpoint gate),
both from the cheap-model issue described in Part 5.

Total wall time ~9 minutes, dominated by LLM calls on free-tier models.
