# Sticker Studio — Build Plan

**Working name:** Sticker Studio (rename is one folder + one title string; see T-003).
**Status:** Approved for planning. **NOT approved for implementation.**
**Owner:** Wasiq. **Written:** 2026-09-25.
**Donor app:** `pixel-platformer` (read in full, measured — not guessed).
**Companion project:** `wwii-pipeline` (the proof run — its *decisions* are frozen; its *findings* are reusable).

---

## How to read this document

| Part | What it is |
|---|---|
| 0 | How to read this |
| 1 | **What we are building** — the context, in plain language |
| 2 | **Vocabulary** — locked words, do not drift |
| 3 | **What we have** — inventory, measured |
| 4 | **Decisions already locked** — by Wasiq, with dates |
| 5 | Architecture |
| 6 | The core loop — how a beat is born |
| 7 | Asset desk |
| 8 | Render |
| 9 | Voice (optional) |
| 10 | Skill export |
| 11 | Dependencies |
| 12 | Risks |
| 13 | **Tickets** — small, numbered, each with an acceptance test |

Everything in Parts 1–4 is context and inventory. Part 5 onward is design. Part 13 is the work.

---

# PART 1 — WHAT WE ARE BUILDING

## 1.1 The problem, in plain language

Wasiq makes long YouTube explainer videos in a flat-sticker collage style (the "MS Paint / Brofessor Stein" look). A 20+ minute video is **400–500 beats**. A beat is one visual moment, about 10–11 words of script, held on screen for about 4.4 seconds.

Right now the behaviour of one of these videos — what picture goes with what sentence, where things sit on screen, what text appears and in what colour — is decided by hand, per video, and the decisions are buried in Python files that only make sense for the video they were written for.

He wants that decision process turned into a **tool he can drive**, where:

- The AI proposes. **He disposes.**
- Every beat gets looked at by a human. All 450 of them.
- Nothing about the Murder Inc. video is baked in. Every video starts from nothing.
- The result is not "generic repeated". **No two beats may be 100% identical.**

## 1.2 Who uses it

An **absolute layman**. He should be able to answer **yes / no**, or pick between **2–3 options with reasoning shown**, or look at a rendered picture and say "yes, put that there". He is willing to invest **2 days** on a 450-beat video. He wants **perfect**, not fast.

He is technical enough to read a plan and approve tickets. He is not willing to read source code to find out why a beat looks wrong.

## 1.3 What it produces

For one video (a "project"):

1. A locked script, split into beats.
2. For each beat: its **point** (meaning), its **situation**, its **look** (arrangement), its **assets**, its **on-screen text**.
3. A folder of hand-authored SVG art + harvested CC0 art, each with recorded provenance.
4. A rendered video, assembled segment by segment.
5. Optionally: a voice track.
6. A handoff bundle for the editor.

## 1.4 The three modes

This matters because Wasiq clarified that "offline" means **absence of an API**, not absence of a computer.

| Mode | Condition | Behaviour |
|---|---|---|
| **Full** | API endpoint + key configured | AI proposes at every step. Human confirms. |
| **Assisted** | No key | Every AI step becomes a **blank form he fills himself**. Nothing breaks; nothing is suggested. |
| **Portable** | No app at all | He exports a **skill pack zip** from S15 and uploads it to any AI (e.g. Claude). That AI runs the architecture by following the pack. |

The pack is the same brain in a different container. See Part 10.

## 1.5 What this is NOT

- **Not an image generator.** No AI art. Art is hand-authored SVG or harvested CC0. This is a standing rule from Wasiq and it is non-negotiable.
- **Not a subtitle tool.** Stein does not use narration subtitles. On-screen text is **meaning text** — see 6.5.
- **Not a template filler.** There is no fixed set of layouts every beat must fit.
- **Not a replacement for the editor.** It hands off; it does not finish the video.

---

# PART 2 — VOCABULARY (LOCKED)

Wasiq confirmed these words on 2026-09-25. Do not rename them in the UI, the DB, or the code.

| Word | Meaning | Note |
|---|---|---|
| **Beat** | One visual moment. ~10–11 words of script. Held ~4.4 s. | |
| **Point / meaning** | What the beat is *about*. Drives everything downstream. | "Meaning" is fine as a technical word. |
| **Situation** (scene) | The kind of moment: a street, a trial, a map journey, a face line-up. | "Scene" internally, "Situation" in UI. Both fine. |
| **Look** | How the pieces are arranged on screen. | **"Composition" and "arrangement" are banned** — Wasiq rejected them as jargon. |
| **Art asset** | One drawable/reusable thing: a figure, a building, a rope, a map. | |
| **On-screen text** (overlay) | Text or glyph drawn over the picture. | "Overlay" is fine — it can be non-text. |
| **Slot** | A named rectangle **inside a look's place**, with a role. | D19 |
| **Place** | The drawn environment / ground plane a look sits on. Figures stand **in** it. | D19 — see 6.7c |

**Channel vs project vs video — settled, because the words were drifting:**

```
Channel  = the YouTube channel            (e.g. the Stein-style channel)
  └── Project = ONE VIDEO / one episode   (the thing with 450 beats)
```

**"Project" and "video" mean the same thing.** There is no level between them. Anything documented as "per project" is per video. The **style kit lives at channel level** (so all videos on a channel share a look); **font, beat length and text colours are per project** so each video can differ.
| **Style kit** | Per-channel rules: background colour, outline width, head size, grid, palette, font. | |

Slot roles (from the proof run, generic enough to ship as defaults):
`figure`, `portrait`, `plate`, `map`, `scene`, `marker`, `stat`, `photo`, `prop`, `panel`.

---

# PART 3 — WHAT WE HAVE

## 3.1 From the proof run (`wwii-pipeline`) — measured, not assumed

These are findings. They are **channel-level measurements**, which is why some may ship as defaults.

| Finding | Value | Ship? |
|---|---|---|
| Reference channel | Brofessor Stein, `UCZQJKUTmgB-cffFSzL3ENJA` | As a style preset only |
| Reference frame | **854×480 @ 30 fps** (ffprobe-verified — not 24) | Preset |
| Background | `#C0EAF6` | Preset |
| One beat | ~10–11 words ≈ **4.4 s** | **Default, per-video setting** |
| Sticker event rate | 78 events = 17.3/min | Reference only |
| 10-min video | ≈ 136 beats | Reference only |
| Head size | 20–25% of frame height | Preset |
| Outline width | **Constant in pixels**, 1.5–2.0% of head height (205 px head → 3–4 px; 364 px → 6 px) | Preset |
| Canon face landmarks | 0.210 / 0.375 / **0.500** / 0.735 / 0.835 of head height. **Eye sits at 0.50.** | Preset |
| Ears | Two, mirrored, drawn **before** the head, 0.44 → 0.72 | Preset |
| Eye design | **Two dark marks**, no sclera. Brow = a line. Nose = one stroke. | **Locked — do not touch** |
| Recurring looks | ~6, not 33. Top five ≈ 73% of beats. | **Ship as 6 deletable defaults** |
| Base vs overlay | Base look held ~4.4 s; overlays **pop in ~3.5 s** | Preset |
| Photo slot rect | `(0.17, 0.12, 0.66, 0.72)` ≈ 1.63:1 | Reference |
| Portrait slot rect | `(0.34, 0.05, 0.32, 0.64)` ≈ 0.89:1 | Reference |
| Canvas | `CANVAS_W=1920`, `BLEED_X=76.8`, `SCALE=2`, view 2073.6×1166.4, export 4147×2333 | Preset |
| Scene library | 29 scenes, 7 overlays, 10 icon glyphs; 45 manifest / 46 tagged | **Do not ship — example pack only** |
| Reusable drawn art | **7 `env_*.svg` backdrops**: street, courtroom, prison_cell, cork_board, interior, outdoors, relationship | **Ship as optional example pack** |
| Reference scenes | 6 Stein videos → 1068 frames → 192 compositions → `references/scenes.md` (text) → `scenes.py` (text table) | **Text, not art. Dictionary, not templates.** |
| `ref/*.jpg` | Face-measuring photos | Not art |

### 3.1a The source frames — RECOVERED, not lost

On 2026-09-25 I claimed the 1068 harvested frames were gone and that re-measuring would need a re-download. **That was wrong.** They are intact:

```
wwii-pipeline/work/harvest/frames/
  eIq35X__dak   264      CYLpFJ44-j8   177
  j-86RzbnY20   194      4TXeV9rSWrc   172
  nRiezhIOHH0   183      O1YgE-ewSU0    78
                                total  1068   <- exact match with the recorded count
wwii-pipeline/work/harvest/clusters/contact_sheet/   192   <- the compositions
```

Everything needed to settle the motion questions in 6.7 is on disk. No download required.

### 3.1b A measurement I mis-read (corrected 2026-09-25)

I stated "2–3 sticker events per beat". **That was invented.** I went back to the source, `wwii-pipeline/work/_step6_assert.py:72`, which reads verbatim:

> `# Density: sticker events / minute. A "sticker event" is any non-transition beat.`

So a **sticker event is a BEAT**, not a motion inside a beat. The ~17.3/min figure means **about 63% of beats carry content and 37% are transitions** (17.3 content beats/min out of ~27 total at 2.2 s/beat). It says **nothing** about how much motion happens inside one beat.

**Consequence: we currently have no measured number for intra-beat motion.** Part 6.7 is therefore written with empty, user-set fields, and T-117 / T-118 exist to measure it from the recovered frames.

**A second conflict the same check exposed — three incompatible beat lengths:**

| Source | Beat length | Beats in a 20-min video |
|---|---|---|
| Measured base layout hold | **4.4 s** | ~273 |
| `_step6_assert.py` duration estimate | **2.2 s** | ~545 |
| Wasiq's "400–500 for 20+ min" | ~2.4–3.0 s | 400–500 |

**RESOLVED 2026-09-25 (see 6.7a):** measured cut interval is **≈ 4.5 s**, which **confirms 4.4 s and rejects 2.2 s**. The 2.2 s figure was a script-derived estimate, not a measurement. My hypothesis that "two beats share one layout" was **wrong** — beats cut at ~13/min and a beat is ~4.5 s.

**The remaining conflict is different and is Wasiq's call:** at 4.5 s/beat, 450 beats is a **33.8-minute** video, not 20. See 6.7a consequence 1.

**Critical distinction, restated because it is the most common misunderstanding:**
The Stein harvest is a **dictionary you look things up in**, not a checklist of 33 scenes you must arrange every beat to match. You do not "match a reference". You ask "what kind of picture does this sentence want?" and then draw *that* beat.

## 3.2 From the donor app (`pixel-platformer`)

Read in full. 50 backend `.py` files, 4621 lines in `api/`, 34 files in `frontend/src`, 16 screens, 18 recipes.

| Module | What it does | Verdict |
|---|---|---|
| `backend/main.py` | FastAPI + lifespan + CORS(3000/5173) + 24 routers under `/api/v1` | **Copy** |
| `backend/core/config.py` + `data/settings.json` | endpoint / api_key / `use_single_model` / `models{light,medium,high}` | **Copy** |
| `backend/core/llm_client.py` | `JOB_MAP` (24 jobs, tier/temp/stream); recipe load w/ versioning; Pydantic `_validate`; **repair-retry once → escalate to high**; `_with_backoff` on 429; semaphore 2; `job_log` insert; `dispatch_stream` (SSE); `dispatch_vision` (base64) | **Copy** — the hardest part, free |
| `backend/db/connection.py` | aiosqlite, WAL, FK on, **one DB per project**, `init_project_db` idempotent | **Copy verbatim** |
| `backend/db/migrations.py` | 25 tables, idempotent heal-on-open | **Copy pattern** |
| `backend/core/id_generator.py` | **already mints `B###`** for beats | **Copy pattern** |
| `backend/core/ripple.py` + `api/stale.py` | Amber-dot stale propagation; `STAGE_ORDER` | **Copy** |
| `backend/storage/fs_manager.py` | Stable folder `{CH##}_{EP##}`, numbered subdirs, README.txt | **Copy pattern**, new subdir list |
| `backend/core/sharding.py` | Overlapping shards for long scripts (threshold 4000, overlap 300) | **Copy** |
| `backend/recipes/*.txt` (18) | The brain as versioned plain text, editable in UI via `api/recipes.py` | **Copy** — biggest win |
| `backend/api/settings.py`, `llm.py` | Settings + connection test | **Copy** |
| `backend/api/checkpoint.py` | Gate screen before advancing | **Copy concept** |
| `backend/api/handoff.py` | Export bundle | **Copy pattern** |
| `frontend` | React 19.2.8 + Vite + Tailwind; `Sidebar`, `TopBar`, `Card`, `BlockButton`, `StatusDot`, `StreamLab`, `SliderWithBadge`, `hooks/useStream.js` | **Copy** |
| `frontend/src/screens/S01..S18` | Numbered-screen pattern | **Copy pattern** |
| `backend/core/composer.py` | `classify_overlay` — a **keyword** classifier | **KEEP THE ROLE IDEA, DELETE THE RULES** |
| `backend/api/library.py`, `channel_library` | Asset store | **Copy shape + add provenance columns** |

**The single biggest gap:** the donor app has **no background worker**. Every AI call dies with the HTTP request. Our render is ~59,400 frames. Worker + progress + segment-GC is the largest thing we build from scratch.

**Correction I owe Wasiq:** I earlier told him the donor app "generates images". It does not. I grepped: no `images.generations`, no `ffmpeg`, no `subprocess` anywhere in `backend/`. It writes **prompt cards**; the picture is made **outside** and approved **inside** (their house rule 6, *Generate Outside / Approve Inside*). This is good news: the donor already runs on the philosophy we need. We only change what "outside" means — Inkscape SVG instead of an image generator.

## 3.3 From the skills

| Skill | Carries |
|---|---|
| `flat-sticker-rig` | Style lock, rig, measured-head reference, `assets/grid.py` |
| `ms-paint-pipeline` | The 4-part human-approved workflow (**template is stale** — must be re-synced from `wwii-pipeline/pipeline/render.py` + `run.py` before Phase 4) |
| `geodata-map-asset` | Map building |
| `vector-garment-harvest` | Recipes A/B for harvesting CC0 garments/objects |
| `mspaint-vector-portrait` | Measured-landmark portrait method |

**Known defect, not yet fixed:** the shipped `ms-paint-pipeline` fails its own portability test 8/9 — `references/wikimedia_fetch.md` contains the string "velásquez". One-line fix. Ticket T-103 covers the same class of defect for the new app.

## 3.4 What we do NOT have

- Background job worker with progress, cancel, resume.
- Inkscape headless raster pipeline with cache.
- ffmpeg per-segment encode with frame deletion.
- Pixel-level verification of composited frames.
- The 10-beat review page.
- The no-duplicates fingerprint guard.
- The meaning-text system.
- Portable skill-pack export.

---

# PART 4 — DECISIONS ALREADY LOCKED

These are Wasiq's calls. Do not re-litigate them in implementation.

| # | Date | Decision | Consequence |
|---|---|---|---|
| D1 | 2026-09-25 | **No two beats may be 100% identical.** "A beat can always have room for creativity." | Fingerprint guard at lock time. See 6.4. |
| D2 | 2026-09-25 | Stein uses **no narration subtitles**. He uses **text at different points, in different styles, a colour each, adding meaning**. | Meaning-text system, not a subtitle track. See 6.5. |
| D3 | 2026-09-25 | Clone `pixel-platformer`; swap modules. | Part 5. |
| D4 | 2026-09-25 | The app must **contain the skill** for API-less use. "Offline" = absence of API. | Part 10, three modes. |
| D5 | 2026-09-25 | Vocabulary: scene / layout / asset / meaning / overlay all fine. **"Composition" → "look".** | Part 2. |
| D6 | 2026-09-25 | All 5 review-page additions approved: repeat counter, locked strip, reuse-from-beat, footer warning, per-beat lock file. | 6.2. |
| D7 | 2026-09-25 | Step 2 (what kind of beat) = **AI gives 2–3 options with reasoning, user can overwrite.** | 6.1. |
| D8 | 2026-09-25 | **Ship zero scenes.** The 33 are one video's decisions. | 3.1, T-040. |
| D9 | 2026-09-25 | **Ship the 6 recurring looks** as deletable defaults — they are channel-level (measured across 6 videos / 192 compositions), not video-level. | T-043. |
| D10 | 2026-09-25 | **Voice: optional.** Not in v1 critical path, but **the cloned folder must contain the voice module and its dependencies.** | Part 9. |
| D11 | 2026-09-25 | **Skill export: a single `.zip`.** | Part 10. |
| D12 | 2026-09-25 | **The exported pack must not contain system paths.** No `C:\`, no absolute paths, no machine-specific strings. | T-101, T-103. |
| D13 | 2026-09-25 | **Beat length: per-video setting, default 4.4 s, and no beat may exceed 6.0 s.** | 6.6. |
| D14 | 2026-09-25 | **No AI image generation**, ever, for artwork. | Standing rule. |
| D15 | 2026-09-25 | The video `out/video_step6.mp4` and the `wwii-pipeline` assets are **frozen**. No more fixes. | Findings only. |

| D16 | 2026-09-25 | **Motion numbers are not invented.** Until T-117/T-118 measure them from the recovered frames, every motion default ships **empty and user-set**. Vocabulary may be defined; quantities may not. | 6.7 |
| D17 | 2026-09-25 | **A beat is a timeline, not a frame.** Render must build `duration × fps` frames with per-asset in/out times. | Part 8, Phase 4B |

| D18 | 2026-09-25 | **Q1 = C. Beat length is variable.** Per-beat, range **0.5–6.0 s**, default **4.5 s** (measured). Not a uniform 4.5 s — a fixed rhythm is the "robotic" failure Wasiq is guarding against. | 6.6 |
| D19 | 2026-09-25 | **Q2 = B. A look = a place + slots inside it.** An environment / ground-plane layer sits **under** the slots. Slots become positions *within* a drawn place, not floating rects on flat colour. | 5.2, 6.1, Part 7 |
| D20 | 2026-09-25 | **Q3 = warn, don't block.** Asset count per beat: minimum 1 (0 = dead beat), **soft target 2–4**, **no hard maximum** — a cap would forbid the cast grid, Stein's most-recurring composition. | T-128 |
| D21 | 2026-09-25 | **Q4 = an AI text-rescan pass, run after asset planning.** The app rescans **every** beat and proposes on-screen text **only on the beats where the AI judges it feasible** — not all of them. The human accepts or rejects per beat. *The pop-in timing itself stays unmeasured and user-set.* | T-092, T-093 |

**One assumption I am making and flagging:** D13 gives a maximum (6.0 s) but no minimum. I am setting the **minimum to 0.5 s** unless Wasiq says otherwise. Reasoning: below ~0.5 s at 30 fps a beat is under 15 frames and cannot register as a shot.

---

# PART 5 — ARCHITECTURE

## 5.1 Folder layout

```
sticker-studio/
  00_PLAN.md                 <- this document
  requirements.txt           <- base (no voice)
  requirements-voice.txt     <- optional, present from day one (D10)
  start.bat / start.sh
  backend/
    main.py
    core/       config  llm_client  id_generator  ripple  sharding  fs_layout  raster  verify
    db/         connection  migrations
    api/        settings  channels  projects  scripts  beats  meanings  situations
                looks  assets  text_desk  render  jobs  checkpoint  handoff  recipes  skillpack
    jobs/       worker.py  queue.py
    recipes/    *.txt   (versioned brain)
    storage/    fs_manager.py
  frontend/src/
    screens/    S01_..S16_
    components/ (copied from donor)
  data/
    app.db
    settings.json
    channels/{CH##}/ style_kit/  library/
    projects/{CH##}_{EP##}/
        01_script/  02_meanings/  03_situations/  04_looks/
        05_assets/svg  05_assets/raster  05_assets/provenance/
        06_beats/locks  06_beats/previews/
        07_render/segments  07_render/frames(temporary, deleted)
        08_handoff/  09_skillpack/
```

Frame store under `07_render/frames` is **temporary by design** — written, encoded, deleted. Never accumulates.

## 5.2 Database

Two DBs, copied from the donor's pattern: `app.db` (global) and one `project.db` per project.

**App DB:** `channels`, `projects`, `app_settings`, `job_log`, `lessons`.

**Project DB (new tables):**

| Table | Holds |
|---|---|
| `scripts` | versioned, `locked` flag |
| `beats` | `B###`, text, section, duration_sec, stale |
| `meanings` | beat → chosen point + rejected options + reasoning + `locked` |
| `situations` | user-named kinds of moment; **starts empty** |
| `looks` | **a place + its slots** (D19); 6 deletable defaults |
| `look_slots` | name, role, rect, optional flag — positions **within** the place |
| `look_env` | the environment / ground-plane layer beneath the slots (D19) |
| `assets` | id, kind (**author / harvest / photo / environment** — D19), svg path, raster path, provenance |
| `provenance` | source, licence, source_url, retrieved_date |
| `beat_assets` | beat → asset → slot → framing |
| `text_items` | beat → text, role, colour, position, emphasis, pop_time |
| `fingerprints` | beat → hash(situation + look + asset set + text set) |
| `render_jobs` | status, progress, segment, error |
| `render_segments` | path, frames, duration, encoded |

## 5.3 The 16 screens

| # | Screen | Copy? | Job |
|---|---|---|---|
| S01 | Project home | ✅ | Pick channel + project, see progress |
| S02 | **Style kit** | NEW | bg, outline rule, head size, grid, palette, font |
| S03 | Script | ✅ donor S04 | outline → draft → punchup → **lock** |
| S04 | **Meaning** | NEW | AI gives 2–3 points + reasoning; pick or overwrite |
| S05 | **Situations** | NEW | Vocabulary grows from zero |
| S06 | **Look** | NEW | 2–3 arrangements per meaning; edit rects |
| S07 | **Asset desk** | 🔶 donor Library | author / harvest / photo + provenance; approve PNG |
| S08 | **Beat board** | 🔶 donor S09, rebuilt | The 10-beat page |
| S09 | **Text desk** | NEW | meaning-text roles, colours, positions |
| S10 | **Render** | NEW | segments, progress, cancel, resume |
| S11 | Checkpoint | ✅ | Gates before advancing |
| S12 | Handoff | ✅ | Export bundle |
| S13 | Settings | ✅ | Endpoint, key, models |
| S14 | Recipes | ✅ | The brain, editable text |
| S15 | **Skill export** | NEW | Build the portable zip |
| S16 | **Voice** | NEW, optional | Hidden until voice deps installed (D10) |

## 5.4 AI job map

Reusing the donor's `JOB_MAP` shape: every job declares `{tier, temp, stream}`.

| Job | Tier | Used by |
|---|---|---|
| `beat_split` | medium | S03 |
| `meaning_options` | high | S04 (returns 2–3 + reasoning) |
| `situation_propose` | medium | S05 |
| `look_options` | medium | S06 |
| `text_suggest` | light | S09 |
| `asset_search_query` | light | S07 harvest |
| `dupe_diff_suggest` | high | S08 (the 5 ways to differ) |

Every call: Pydantic validate → repair once → escalate to high → log to `job_log`. Copied.

## 5.5 Recipes

The brain is 7+ plain-text versioned files in `backend/recipes/`, editable in the UI. **No prompt text hardcoded in Python.** This is the donor's best idea and we keep it exactly.

## 5.6 Worker

New. A `jobs/` package with a queue table, a single worker loop, and SSE progress.

- Jobs: `render_segment`, `raster_all`, `skillpack_build`.
- A job must **survive a page reload** and **survive an app restart** (resume from `render_jobs`).
- Progress is written to the DB, not held in memory.
- Cancel is cooperative: the worker checks a flag between segments.

## 5.7 Portability rule

No absolute path may appear in: recipe text, exported skill pack, generated handoff README, or any committed file. This is D12 and it is enforced by a test, not by memory. See T-101 / T-103.

---

# PART 6 — THE CORE LOOP

## 6.1 Stages

```
script ──lock──> beats ──> point ──> situation ──> look ──> assets ──> text ──> LOCK ──> render
                   ^          ^          ^                                        |
                   |          |          |                                        |
                 ripple: editing the script marks all downstream amber            |
                 fingerprint check happens AT LOCK --------------------------------+
```

Every stage after the script produces a proposal the human confirms or overwrites. **Nothing is silently decided.**

## 6.2 The 10-beat review page (S08) — spec

Wasiq approved all five additions (D6). The page shows **10 beats**; locking them reveals the next 10, with the previous 10 collapsed to a locked strip.

Each beat card has these columns:

| Column | Content |
|---|---|
| **Beat #** | `B###` |
| **Beat line** | Verbatim script text for this beat |
| **Point** | Chosen meaning; click to see the rejected options and their reasoning |
| **Reasoning** | Why the AI picked it — always visible, never hidden |
| **Visual** | Rendered preview of this beat's base look |
| **Repeat counter** | `×3` with a jump link to each earlier identical beat |
| **Reuse-from-beat** | "Copy the arrangement from B###" |
| **Actions** | Approve / Suggest alternative / Send to Make queue |

Plus:

- **Locked strip** — previous 10, collapsed, each expandable, each unlockable.
- **Footer warning** — what is still unresolved in this batch before it can be locked.
- **Per-beat lock file** — `06_beats/locks/B###.json`, human-readable, one per beat. So a lock is a file he can read and diff, not a DB bit he has to trust.

## 6.3 The three queues (how 450 beats stays doable)

He always sees all 450. Only the effort per beat changes.

| Queue | Enters when | Effort |
|---|---|---|
| **Quick pass** | AI confident, no fingerprint clash | One click |
| **Think pass** | AI unsure, **or** fingerprint clashes with a locked beat | Full card |
| **Make pass** | Needs a new asset | Routed to Asset desk first |

## 6.4 The no-duplicates rule (D1)

Every beat gets a **fingerprint**: hash of (situation + look + asset set + text set).

At lock time, if the fingerprint equals a **locked** beat's fingerprint:

- **The lock is refused.** Not warned — refused.
- A diff panel opens showing the two beats side by side.
- The panel offers exactly **five ways to differ it**:
  1. Rotate the look (mirrored / shifted slots)
  2. Swap an asset variant
  3. Change the framing distance
  4. Change the text role or colour
  5. Move the text position
- Any one of the five clears the block.

This is the "room for creativity" affordance, made mechanical.

## 6.5 Meaning text (D2) — not subtitles

Stein does not caption his narration. He places **text at different points, in different styles, a colour each, adding meaning to the scene**.

So the system is:

| Role | Typical colour | Use |
|---|---|---|
| Name | one colour | Who this is |
| Place | another | Where |
| Date / year | another | When |
| Number / stat | another | How much |
| Quote | another | What was said |
| Warning / emphasis | another | The turn |

- Chosen **once per video** (S09), overridable **per beat**.
- Each item has a **position** and an **emphasis** level.
- Overlays **pop in** around 3.5 s into a beat, not at frame 0 (measured).
- **This is not a subtitle track.** There is no narration captioning anywhere in this app.

## 6.6 Beat length (D13, superseded by D18)

- **Per-BEAT**, not per-video. Range **0.5 – 6.0 s**. **Default 4.5 s** (measured, 6.7a).
- **Hard maximum 6.0 s.** Validation refuses more; no "just this once".
- Minimum 0.5 s.
- The per-video setting is only the **starting default** for new beats.

**D18 is explicitly anti-robotic.** A uniform 4.5 s across 450 beats is the failure mode Wasiq named. Rhythm must vary. The **rhythm monotony check (T-129)** flags runs of same-length, same-look beats.

## 6.7 Motion — written with EMPTY defaults, on purpose (D16)

**This section is deliberately incomplete.** On 2026-09-25 I caught myself about to design a motion system on a number I had mis-read (see 3.1b). Rather than invent "2–3 events per beat" and ship it, the model is defined and **every quantity is left unset** until T-117 and T-118 measure it from the 1068 recovered frames.

### The model (settled)

A beat is **a timeline, not a frame** (D17). Each asset placed in a beat carries:

| Field | Meaning | Default |
|---|---|---|
| `in_time` | when it appears, in seconds from beat start | **UNSET — user** |
| `out_time` | when it leaves (null = to end of beat) | **UNSET — user** |
| `motion` | which primitive moves it | **UNSET — user** |
| `motion_duration` | how long the move takes | **UNSET — user** |

### Motion primitives (vocabulary only — no quantities)

`hold` · `pop` · `slide_in` · `drift` · `scale` · `fade`

These are **names**, not measurements. They live in the style kit as editable per-channel data. **There is no keyword→motion auto-assignment** — that is the same bug class as the donor's `classify_overlay` and the skull icon (see T-083).

### Beat-to-beat transition (vocabulary only)

`cut` — the next beat starts fresh. `carry` — the previous base look stays and only the changed assets move.

Which one Stein uses, and how often, is **unmeasured**. T-118.

### 6.7a MEASURED — run on 2026-09-25, fills the gaps above

Method: three Stein videos (`eIq35X__dak`, `nRiezhIOHH0`, `j-86RzbnY20`), 90-second window each, sampled at **10 fps** via ffmpeg, downscaled to 160×90, consecutive-frame difference, threshold `>16` grey levels, runs collapsed into events. Separately, all six `index.json` timestamp sets (n = 1062 gaps) for layout persistence.

| Metric | **Measured** | Notes |
|---|---|---|
| **Beat length** (interval between cuts) | **≈ 4.5 s** | 12.0 / 13.3 / 14.0 cuts per minute across the three videos |
| Layout persistence (keyframe gaps, all 6 videos) | median **5.04 s**, p25 2.37, p75 8.52 | skewed; 41% of gaps > 6 s |
| **Small motion events** (1–15% of pixels) | **16.0 – 18.7 per minute** | → **≈ 1.3 events per beat** |
| **Motion event duration** | **≤ 0.10 s** — exactly one sample in every case, n = 76 | **a pop, not a tween** |
| Static fraction | **93–94%** of frames change < 1% | the picture is frozen between events |
| Medium events (15–25%) | 2.7 – 6.7 per minute | |

**Direct answers to the questions that were open:**

- **Does a beat hold 2–3 sticker events?** **No — ~1.3.** Both numbers I offered earlier (2.5, then 2–3) were wrong. It is **1–2 events per beat**, and a beat with 3 is unusual.
- **True beat length: 4.4, 2.2 or ~2.7 s?** **≈ 4.5 s.** This **confirms 4.4 s and rejects 2.2 s.** The 2.2 s figure in `_step6_assert.py` was a rough script-derived estimate, not a measurement.
- **How long is one motion?** **≤ 0.1 s — instantaneous.** Motion is an appearance, not an animation.
- **Cut or carry?** Measured cuts at ~13/min means **beats cut**. A carry would show as no cut, so carry is the exception, not the rule.

**Two consequences Wasiq needs to decide on:**

1. **450 beats × 4.5 s = 33.8 minutes, not 20.** At Stein's real rhythm, "400–500 beats" is a ~34-minute video. Either his videos are ~34 min, or he runs a shorter beat than Stein. **This is his call, not mine.**
2. **A 0.1 s pop means the motion system is nearly trivial.** There is no tween engine to build — an asset has an `in_time` and appears. That removes most of the risk from Phase 4B.

**Caveats, stated:**
- 10 fps cannot resolve motion faster than 0.1 s. A very fast tween (< 0.1 s) would look identical to a pop. **T-127 re-checks at 30 fps.**
- Motion was sampled on **3 of 6** videos (the three densest). Layout gaps used all 6.
- `O1YgE-ewSU0` is an outlier on keyframe gaps (median 11.4 s, only 78 frames over 1384 s) — its scene detector barely fired. It is excluded from the beat-length claim.
- One 90-second window per video. Wider sampling is cheap if he wants tighter confidence.

### 6.7b Asset count per beat — ADDED 2026-09-25 after Wasiq's challenge

He pushed back: *"not every beat will contain only one asset — some can contain 2, 3, 4... we are not making our beats robotic."* He is right, and **the plan did not say this anywhere.** Grep for "assets per beat" returned nothing.

**The distinction I had blurred:** *assets on screen* and *motion events* are two different numbers.

| | Measured | Meaning |
|---|---|---|
| **Assets visible in one beat** | **1–8, median 2, mean 2.79** (from the proof run's 22 layouts) | how full the picture is |
| **Motion events in one beat** | **~1.3** (from Stein, 6.7a) | how often something changes |

A beat can easily hold **4 assets** — the ~1.3 says they mostly **arrive together**, not that they can't all be there. Stein's own catalogue confirms the high end: his most-recurring composition is the **cast grid — 5–6 portraits per row, each labelled**, recurring at t=2 s and t=1049 s in the same video.

Proof-run slot distribution (22 layouts):

```
8 slots  cast_grid            3 slots  single_figure_props / group_scene / comparison_row
6 slots  asset_grid           2 slots  figure_location / portrait_nameplate /
4 slots  map_markers                   portrait_banner / two_facing
                              1 slot   object_only / panel_full / photo / stat_card
```

**Anti-robotic rule this implies:** variety comes from *how many* assets a beat holds and *how full* the frame is — not from adding motion. Since motion is a 0.1 s pop (6.7a), **padding beats with fake motion is not what makes them engaging.** Density and composition are.

### 6.7c ⚠️ A FOUNDATIONAL CONFLICT — the slot model may be wrong

While pulling the numbers above I re-read `wwii-pipeline/work/harvest/SCENE_CATALOGUE.md`. Its **headline finding**, measured from all six Stein videos, says:

> **HE DRAWS THE ENVIRONMENT AND THE GROUND PLANE.** A figure is rarely alone on blue. It stands on a *drawn floor*, in a *drawn room*, beside a *drawn door, table, bed, cell, car or fence*. Beats read as **scenes**, not as stickers-in-slots.
>
> "Our 10 layouts all share one assumption: the canvas is a flat colour and elements float in slots... **our beats have no place in them.**"

**This contradicts the architecture of this document.** Part 5 and Part 6 build everything on *slots*: a look is a set of named rectangles, each holding one asset. The harvest says Stein builds a **place** and puts figures **in** it.

This is not a small thing — it is the difference between "a collage of cut-outs on blue" and "a scene". It is very likely the source of the "quality is messed up" feeling from the proof run.

**I am not resolving this myself.** It needs Wasiq's decision. See the open questions at the end of Part 13.

### 6.7d MEASURED — pop timing and the 30 fps re-check, run 2026-09-25

Method: two Stein videos (`eIq35X__dak`, `nRiezhIOHH0`), 120 s each at **30 fps**, 320x180, frame-diff `>16`, cuts at `>=25%` define beat boundaries, events at 1-25%, each event's position recorded as a fraction 0-1 through its beat.

| Metric | eIq35X__dak | nRiezhIOHH0 |
|---|---|---|
| Beat length (median) | **4.00 s** | **4.37 s** |
| Events | 44 | 41 |
| **Event position inside beat (median)** | **0.42** | **0.42** |
| position p10 / p25 / p50 / p75 / p90 | 0.08 / 0.22 / 0.42 / 0.62 / 0.70 | 0.16 / 0.29 / 0.42 / 0.60 / 0.72 |
| Events in the first 20% of the beat | 25% | 20% |
| Events after 60% of the beat | 30% | 24% |
| **Event duration (median)** | **0.033 s** | **0.033 s** |
| Event duration (max) | 0.133 s | 0.033 s |

**Three conclusions:**

1. **T-127 is answered: it is a pop, not a tween.** At 30 fps the median event lasts **0.033 s - exactly one frame**; the longest seen was 0.133 s. There is no measurable animation. **There is no tween engine to build.**
2. **Beat length confirmed again** at 4.00 / 4.37 s, in line with the 4.5 s from 6.7a.
3. **My 3.5 s constant was badly wrong.** 3.5 s of a 4.4 s beat is **80%** through. The measured median is **42%** - about **1.9 s into a 4.5 s beat**. I had been popping overlays at roughly the 90th percentile of when Stein actually changes anything.

**Honest failure: I could not isolate text from asset pops.** I tried a shape heuristic (compact, wide, solid blob: height < 20% of frame, aspect >= 1.8, fill >= 45%). It matched **0 of 85 events**. Two readings, and I cannot tell which is right from pixels alone:

- (a) **Stein's text is baked into the composition** - it arrives with the beat, so there is no separate pop time at all; or
- (b) my heuristic is simply wrong for his text style.

**Therefore the shipped default is: on-screen text arrives with the beat (position 0),** with the position overridable per beat. The **42%** figure is the measured timing for *changes in general* and is the right default if he ever wants a delayed pop.

### What is still NOT written here

| Question | Status |
|---|---|
| Is Stein's text baked into the art, or does it animate in? | **UNRESOLVED.** Needs a human to look at frames - I cannot see images. Default ships as "arrives with the beat" (6.7d). |

**Rule for implementation:** the measured values above may ship as defaults, each labelled `measured` with its method (T-126). Anything still unmeasured renders as an empty, user-set control.

---

# PART 7 — ASSET DESK

Three ways an asset comes into existence. All three record provenance.

| Kind | How | Notes |
|---|---|---|
| **Author** | Hand-authored SVG, measured from a reference | Never traced. Never AI-generated (D14). |
| **Harvest** | CC0 / public-domain SVG from the web | Recipes in `vector-garment-harvest` |
| **Photo** | Real photograph with a licence | e.g. Wikimedia Commons |
| **Environment** | A drawn place: floor, room, street, cell | **D19.** Sits under the slots. This is the layer the proof run was missing (6.7c). |

**D19 changes what an asset is.** The proof run's `env_*.svg` backdrops (street, courtroom, prison_cell, cork_board, interior, outdoors, relationship) were treated as one slot among many. Under D19 they become a **first-class layer every look has**, and a beat without one is the "no place in them" failure the harvest named.

Rules carried from the proof run:

- **OBJECT → harvest is sanctioned. FIGURE / face → hand-author.** Wasiq approved harvesting for objects (2026-09-24).
- **No asset without a reference.**
- **Approve the rendered PNG, never the SVG source.** The render is the only feedback that counts.
- Outline width is **constant in pixels**: 1.5–2.0% of head height.
- **A missing asset gets an honest labelled box — never a silent blank.** This is a rule, not a fallback.

Known trap to carry forward: the `photo` role mints an id **from the beat text**. On a beat about a building this minted `photo_abe_reles` — a mugshot id. Ticket T-068 must handle place-photos on their own path.

---

# PART 8 — RENDER

**A beat is a timeline, not a frame** (D17). Render builds `duration_sec × fps` frames, and each asset is drawn only between its own `in_time` and `out_time`. A static frame held for a whole beat is a valid *choice*, not the default.

The number that governs everything: **450 beats × 4.4 s × 30 fps ≈ 59,400 frames.** At 1920×1080 PNG that is ~150 GB. **Never held.** (That figure is a planning upper bound and inherits the unsettled beat length from 3.1b — it swings to ~27,000 frames if the true beat is 2.2 s. T-118 settles it.)

- Encode **per segment** (e.g. 40 beats), then **delete the frames immediately**.
- Frames live only in `07_render/frames`, and the folder is asserted empty at job end.
- Progress, cancel, resume — all through the worker (5.6).
- Single-beat preview render available from the beat card before committing.
- Verification is **by pixel, not by eye**: ink-map, row-flip profile, placeholder-fill detection. The placeholder grey is detectable; a silent blank is not.

Donor reference numbers: `CANVAS_W=1920`, `BLEED_X=76.8`, `SCALE=2`, view 2073.6×1166.4, export 4147×2333.

---

# PART 9 — VOICE (OPTIONAL) — D10

Wasiq's call: **keep it optional, but the cloned folder must contain it.**

- Voice dependencies live in **`requirements-voice.txt`**, separate from `requirements.txt`.
- The **S16 Voice screen and its backend module exist in the folder from Phase 0**, hidden until the deps are detected.
- Not on the v1 critical path. v1 ships script + timing + frames.
- When added (Phase 6): beat duration can be driven by actual audio length — still capped at 6.0 s (D13).

Dependencies: `kokoro-onnx` (~311 MB weights + ~27 MB), `onnxruntime`, `phonemizer`, **espeak-ng** (system binary).

---

# PART 10 — SKILL EXPORT (PORTABLE PACK) — D11, D12

S15 builds **one `.zip`**. He uploads it to any AI; that AI runs the architecture.

The pack contains:

- `SKILL.md` — the workflow, the rules, the vocabulary.
- `recipes/` — the same brain the app uses, as text.
- `templates/` — empty project skeleton.
- `reference/` — the measured numbers from 3.1 (as data, not code).
- `docs/` — the 9-step plain-language guide.

Hard constraints:

- **No system paths.** No `C:\`, no absolute paths, no machine-specific strings. (D12)
- A portability test greps the built pack and **fails the build** on a hit. (T-103)
- The pack must work with **no API** — it is instructions, not a service.

---

# PART 11 — DEPENDENCIES

**From the donor (already present):**
`fastapi` · `uvicorn[standard]` · `openai` · `pillow` · `python-multipart` · `sse-starlette` · `aiosqlite` · `pydantic` · `httpx==0.28.1`

**Add to base:**
`numpy` · `scipy` · `ffmpeg-python` (or plain subprocess to `ffmpeg`) · build tooling

**Optional (voice), present in folder from day one:**
`kokoro-onnx` · `onnxruntime` · `phonemizer` · **espeak-ng** (system binary)

**External binaries — not pip:**
`ffmpeg` · `inkscape` (headless CLI only — **never the GUI**, standing rule) · a font file

**Runtime:** Python. Donor venv is **3.14.0**. ⚠️ Unverified whether `onnxruntime` / `kokoro-onnx` ship 3.14 wheels. **T-001 exists specifically to settle this before anything else is installed.**

---

## 11a — Where everything actually lives on THIS machine

**Scope note, and a correction.** I previously kept this document free of system paths and treated that as a virtue. That was **wrong**: D12's "no system paths" rule applies **only to the exported skill pack** (Part 10), because that pack gets uploaded to a stranger. This **build plan runs on Wasiq's own machine** and is useless if it won't say where Kokoro is. Paths below are recorded deliberately.

All entries verified on disk 2026-09-25, not recalled.

### The skills (the existing brain)

| Skill | Path | Note |
|---|---|---|
| **`ms-paint-pipeline`** | `C:\Users\wasiq\.workbuddy-ai\skills\ms-paint-pipeline\` | **This is the current MS Paint skill.** 4-part workflow. Its `assets/pipeline-template/` is **STALE** — re-sync from `wwii-pipeline/pipeline/` before use (T-072). |
| `flat-sticker-rig` | `C:\Users\wasiq\.workbuddy-ai\skills\flat-sticker-rig\` | Style lock, rig, `references/measured-head.md`, `assets/grid.py` |
| `mspaint-vector-portrait` | `C:\Users\wasiq\.workbuddy-ai\skills\mspaint-vector-portrait\` | Measured-landmark portrait method |
| `geodata-map-asset` | `C:\Users\wasiq\.workbuddy-ai\skills\geodata-map-asset\` | Map building |
| `vector-garment-harvest` | `C:\Users\wasiq\.workbuddy-ai\skills\vector-garment-harvest\` | CC0 harvest recipes A/B |
| `beat-timed-explainer-pipeline` | `C:\Users\wasiq\.workbuddy-ai\skills\beat-timed-explainer-pipeline\` | **DEPRECATED** — absorbed into `ms-paint-pipeline`. Do not start new work here. |

### Kokoro (voice) — already installed, contrary to my earlier risk note

| What | Where |
|---|---|
| **Model weights** | `C:\Users\wasiq\Downloads\Kokoro\kokoro-v1.0.onnx` — **311 MB** |
| **Voices** | `C:\Users\wasiq\Downloads\Kokoro\voices-v1.0.bin` — **27 MB** |
| Runtime | `kokoro-onnx 0.6.1` + `onnxruntime 1.30.0` — **already in the default venv** |
| Phonemizer | `phonemizer 3.4.0` — already in the default venv |

**This retires risk R1.** I had flagged voice as "the dependency most likely to eat a week on version conflicts". It will not — the weights are downloaded and the Python packages are installed and importable today. **What is missing is `espeak-ng` as a system install**: only `espeak-ng.dll` appears, and only inside `%TEMP%` folders, where phonemizer unpacks it at runtime. It probably works; it is not verified. Ticket **T-131**.

### External binaries

| Tool | Path | Version |
|---|---|---|
| **ffmpeg** | `C:\Users\wasiq\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-full_build\bin\ffmpeg` | **9.0.1** |
| **Inkscape** | `C:\Program Files\WindowsApps\25415Inkscape.Inkscape_1.4.40.0_x64__9waqn51p1ttv2\VFS\ProgramFilesX64\Inkscape\bin\inkscape.exe` | **1.4.40.0** |
| Inkscape override | env var `INKSCAPE_PATH` (the proof run already honours it) | |
| **Font** | **NOT CHOSEN.** The proof run fell back to PIL's `ImageFont.load_default()` — a built-in bitmap font, not a real typeface. 393 `.ttf` files sit in `C:\Windows\Fonts`. To be chosen **per project** from a system-font picker. | **GAP** — T-133 |

**Font shortlist for the Stein style — bold, heavy, readable at sticker scale.** All verified present in `C:\Windows\Fonts`:

| File | Look | My take |
|---|---|---|
| `Oswald-Bold.ttf` | condensed, tall | **Best fit** — condensed and heavy, the standard YouTube-explainer look |
| `Roboto-Black.ttf` | very heavy, wide | Strong, neutral |
| `Roboto_Condensed-Black.ttf` | heavy + condensed | Heavy *and* fits long words |
| `Impact.ttf` | extremely heavy, condensed | Very loud; classic, but overused |
| `arialbd.ttf` (Arial Bold) | neutral | Safe, forgettable |
| `bahnschrift.ttf` | geometric, variable | Modern, less punch |
| `verdanab.ttf` | wide, chunky | Readable but bulky |

*My opinion: **`Oswald-Bold`** as the channel default, with **`Roboto_Condensed-Black`** as the fallback when a word is too long for the box.* Reasoning: on-screen text sits in small boxes over busy art, so condensed beats wide — it fits more characters at the same legibility. Wasiq picks; this is not my call to make.

### What `espeak-ng` actually is (plain language)

Kokoro does not read spelling. It reads **sounds**. Something has to turn the letters `"though"` into the phonemes `ð oʊ` before Kokoro can say them.

**`espeak-ng` is that converter.** It is a small standalone program that turns written text into phonemes. **`phonemizer`** is the Python wrapper that calls it. So the chain is:

```
text  ->  phonemizer  ->  espeak-ng  ->  phonemes  ->  Kokoro  ->  audio
```

**Kokoro is the singer. espeak-ng writes the pronunciation guide it sings from.**

**The problem on this machine:** there is no proper espeak-ng install. Only an `espeak-ng.dll` appears, and only inside `%TEMP%` folders — phonemizer unpacks it there at runtime. It may work fine. Nobody has actually run it. If it breaks, voice breaks, and the error will look like a Kokoro failure when it isn't. Ticket **T-131**.

⚠️ **The Inkscape path is an MSIX (Windows Store) path and it is version-pinned.** `25415Inkscape.Inkscape_1.4.40.0_x64__9waqn51p1ttv2` will change the moment Inkscape updates, and every hard-coded call breaks. **The app must probe for Inkscape, never hard-code it** — ticket **T-132**.

### Python environments

| Venv | Path | Contains |
|---|---|---|
| **default** | `C:\Users\wasiq\.workbuddy-ai\binaries\python\envs\default\` | **numpy 2.4.6, scipy 1.18.1, pillow 12.3.0, fastapi 0.141.1, kokoro-onnx, onnxruntime, phonemizer** |
| paintprev | `C:\Users\wasiq\.workbuddy-ai\binaries\python\envs\paintprev\` | pillow only |
| donor app | `C:\Users\wasiq\pixel-platformer\.venv\` | Python **3.14.0**; fastapi, uvicorn, openai, pillow, aiosqlite, pydantic, sse-starlette |

**This also retires most of R1's sting.** numpy and scipy — which I listed as "❌ add" — are already present in the default venv. The base `requirements.txt` mostly re-declares what exists.

### Source material (the measurements in Part 6.7 came from here)

| What | Path |
|---|---|
| Proof-run project | `C:\Users\wasiq\WorkBuddy AI\2026-09-22-10-09-25\wwii-pipeline\` |
| **Stein frames (1068)** | `wwii-pipeline\work\harvest\frames\<video_id>\` — `f00001.png` + `index.json` (has timestamps) |
| **Source videos (6)** | `wwii-pipeline\work\harvest\src\` |
| Compositions (192) | `wwii-pipeline\work\harvest\clusters\contact_sheet\` |
| Scene catalogue | `wwii-pipeline\work\harvest\SCENE_CATALOGUE.md` — **source of the 6.7c finding** |

### LLM endpoint

`http://localhost:20128/v1`, provider `duckduckgo-free` for search — from `pixel-platformer\data\settings.json`, models `{light, medium, high}`. The search endpoint is **web-only**.

---

# PART 12 — RISKS

| # | Risk | Mitigation |
|---|---|---|
| R1 | ~~`onnxruntime`/`kokoro` have no Python 3.14 wheel~~ **RETIRED 2026-09-25.** Weights are downloaded (311 MB + 27 MB) and kokoro-onnx / onnxruntime / phonemizer are already installed in the default venv. See 11a. Replaced by R12/R13. |
| R2 | 59,400 frames fills the disk | Per-segment encode + immediate delete; assert frames dir empty |
| R3 | The donor's `classify_overlay` keyword rules get copied in | T-083 deletes them; text roles are user-defined |
| R4 | Recipe text drifts into containing video-specific names | T-103 portability test |
| R5 | The stale `ms-paint-pipeline` template gets used as a source | Re-sync from `wwii-pipeline/pipeline/` first (T-072) |
| R6 | Scope creep into voice | Voice is Phase 6, optional, behind a dep check |
| R7 | Beat creep | Hard 6.0 s cap (D13), validated, no override |
| R8 | I hallucinate | Tickets are small and each has an acceptance test. Nothing is "done" without it. |
| R9 | **Motion gets designed on invented numbers** — the exact thing I nearly did on 2026-09-25 with "2–3 events per beat" | D16: all motion defaults ship empty; T-117/T-118 measure first; T-126 labels every filled default `measured` |
| R10 | **Beat length stays conflicted** (4.4 / 2.2 / ~2.7 s) and every downstream count is wrong by 2× | T-118 resolves it before any render-size estimate is trusted |
| R11 | A motion keyword classifier gets copied in, as the donor's `classify_overlay` nearly was | T-116 keeps primitives as data; no auto-assignment |
| R12 | **The Inkscape path is version-pinned MSIX** and breaks on update | T-132 — probe at runtime, never hard-code; honour `INKSCAPE_PATH` |
| R13 | **No font is chosen.** The proof run fell back to PIL's built-in bitmap font | T-133 — pick a real typeface; on-screen text is central to D2, so a bitmap fallback is not acceptable |
| R14 | **`espeak-ng` has no system install** — only a DLL phonemizer unpacks into `%TEMP%` | T-131 — verify phonemizer actually works end-to-end, or install espeak-ng properly |

---

# PART 13 — TICKETS

Rules for these tickets:
- **One ticket = one change.** If a ticket needs more than one sitting, it is two tickets.
- **Every ticket has an acceptance test.** No acceptance = not done.
- Phases are ordered. A phase starts when the previous phase's tickets all pass.
- `T-001` is deliberately first: it is the only ticket that can invalidate a dependency decision.

---

## PHASE 0 — Foundation (clone, rename, empty out)

**T-001 — Settle the Python version before installing anything.**
Check whether `onnxruntime` and `kokoro-onnx` publish wheels for Python **3.14.0** (the donor venv's version). If either does not, record the decision to pin the new venv to 3.13.
*Acceptance:* a written line in this file stating the chosen Python version and the wheel verdict for each of onnxruntime, kokoro-onnx, numpy, scipy. No installs until this line exists.

**T-002 — Clone the donor to `sticker-studio/`.**
Copy `pixel-platformer` including `.git` history so provenance is preserved; keep `HOW_IT_WORKS.md` and `LOCKED_DECISIONS.md` in a `donor/` subfolder for reference.
*Acceptance:* folder exists; `git log` shows the donor history; app is not yet run.

**T-003 — Rename the app.**
`FastAPI(title=...)`, frontend title string, sidebar brand, `start.bat`/`start.sh` window text. Single source: one constant file.
*Acceptance:* no occurrence of "Pixel Platformer" in any user-visible string. Grep returns zero.

**T-004 — Decide the fate of the 8 donor screens we do not need.**
`S02_IdeaStudio`, `S03_TitleStudio`, `S05_CastBoard`, `S06_VariantTimelines`, `S07_ScoutBoard`, `S08_WorldDesk`, `S10_Sheets`, `S18_Prompts`. Move them to `donor/disabled_screens/` rather than deleting.
*Acceptance:* those 8 files are out of `frontend/src/screens/`; the app still boots; no import references them.

**T-005 — Write the base `requirements.txt`.**
Donor list + numpy + scipy. No voice packages.
*Acceptance:* fresh venv installs from this file with zero errors.

**T-006 — Write `requirements-voice.txt` (present from day one).**
kokoro-onnx, onnxruntime, phonemizer. A comment records that espeak-ng is a system binary.
*Acceptance:* file exists in the repo root even though nothing installs it in v1.

**T-007 — Delete donor recipes that do not apply; keep the loader.**
Keep `load_recipe` / `latest_version` / the recipe API. Remove recipe files for jobs we do not run (character_extract, environment_extract, variant_extract, world_scan, title_*).
*Acceptance:* `backend/recipes/` contains only recipes for jobs in 5.4; `api/recipes.py` still lists and edits them.

**T-008 — Replace the DB schema.**
Drop donor tables not in 5.2. Add `meanings`, `situations`, `looks`, `look_slots`, `beat_assets`, `text_items`, `fingerprints`, `render_jobs`, `render_segments`, `provenance`. Keep `init_project_db` idempotent.
*Acceptance:* delete `project.db`, boot, and the schema heals itself; every table in 5.2 exists.

**T-009 — New project subfolder list in `fs_manager`.**
Use the layout in 5.1. Keep the stable `{CH##}_{EP##}` naming rule — never a human slug.
*Acceptance:* creating a project makes exactly those folders; renaming a project never changes the folder.

**T-010 — Extend `id_generator`.**
`B###` for beats (already exists), plus prefixes for situations, looks, assets, text items. Reuse `mint_beat` verbatim.
*Acceptance:* IDs increment with no gaps and no collisions after deleting a middle row.

**T-011 — App boots.**
`start.bat` runs backend + frontend; `/api/v1/settings` responds; frontend loads.
*Acceptance:* cold start to working UI in under 60 s, no console errors.

**T-012 — Smoke path: channel → project → empty home.**
*Acceptance:* create a channel, create a project, land on a home screen that honestly says zero beats.

---

## PHASE 1 — Script in, beats out, point chosen

**T-020 — Script subfolder + `scripts` table.** Versioned rows, `locked` flag. *Acceptance:* saving twice creates version 2; version 1 is unchanged.

**T-021 — `beats` table.** `B###`, text, section, `duration_sec`, `stale`. *Acceptance:* 450 inserts run in under 2 s.

**T-022 — Script import.** Paste text or upload `.md`. Store verbatim, never rewrite. *Acceptance:* importing the same file twice yields byte-identical stored text.

**T-023 — Script lock.** Locking writes an immutable version and is the ripple trigger. *Acceptance:* a locked script cannot be edited without an explicit unlock that flags downstream amber.

**T-024 — `beat_split` job + recipe.** One beat = one visual moment, ~10–11 words. *Acceptance:* recipe file exists; a 500-word script returns a plausible beat list; malformed output is caught by Pydantic and repaired once, then escalated.

**T-025 — Wire `sharding.py` for long scripts.** Reuse donor thresholds (4000 words / 300 overlap). *Acceptance:* a 6000-word script splits, extracts, and merges with no dropped beat at the seam.

**T-026 — Beat length setting.** Per project, default 4.4, max **6.0**, min 0.5. *Acceptance:* the default appears on a new project as 4.4.

**T-027 — Duration validation.** Refuse > 6.0 and < 0.5 at the API, not just the UI. *Acceptance:* a direct API POST with 7.0 is rejected with a clear message.

**T-028 — `meaning_options` job + recipe.** Returns **2–3 options, each with reasoning**. *Acceptance:* every option carries a non-empty reasoning string; a schema without reasoning fails validation.

**T-029 — Meaning UI.** Radio-style option cards; reasoning always visible; a free-text "or type your own" box. *Acceptance:* the user's own text wins over every option.

**T-030 — Per-beat meaning lock.** *Acceptance:* locking writes `06_beats/locks/B###.json` and the beat cannot change without unlocking.

**T-031 — Ripple from script to beats.** Editing a locked script marks all beats amber. *Acceptance:* edit → amber count equals beat count; reviewed clears them.

**T-032 — `job_log` for every AI call.** *Acceptance:* after a full pass, every beat has at least one job_log row with tokens, tier, and ok/fail.

---

## PHASE 2 — Situations, looks, and the Beat Board (the core)

**T-040 — `situations` table, empty on create.** D8: ship zero. *Acceptance:* a brand-new project has zero situations, and the UI says so instead of showing a sample list.

**T-041 — `situation_propose` job.** Cluster beats that want the same kind of picture; propose a name. *Acceptance:* on 30 beats the proposal groups them; the user renames or rejects every group.

**T-042 — Situation UI.** Create / rename / delete / merge. *Acceptance:* deleting a situation in use warns and lists the affected beats — it never deletes silently.

**T-043 — `looks` table with 6 deletable defaults.** D9. Seeded from the channel-level measurement, **all deletable**. *Acceptance:* a new project shows 6; deleting all 6 leaves an empty, working state.

**T-044 — `look_options` job.** 2–3 arrangements per meaning, with reasoning. *Acceptance:* options differ in slot *arrangement*, not just in which asset fills a slot.

**T-045 — Look editor.** Add/remove slots, drag rectangles, set role and optional flag. *Acceptance:* rects persist as 0–1 fractions.

**T-046 — Slot role vocabulary.** The 10 roles from Part 2, editable per channel. *Acceptance:* the role list is data, not code — adding a role needs no Python change.

**T-047 — Rect validation.** No two slots overlap; all within 0..1; aspect ratio warning on a photo slot mismatch. *Acceptance:* an overlapping save is refused with the two slot names named.

**T-048 — Beat board: page of 10.** *Acceptance:* 450 beats render as 45 pages; page 3 shows B021–B030.

**T-049 — Beat card columns.** Beat #, line, point, reasoning, visual. *Acceptance:* all five present on every card.

**T-050 — Repeat counter + jump.** `×N` with links to each earlier beat. *Acceptance:* clicking jumps to that beat and highlights it.

**T-051 — Locked strip.** Previous 10 collapsed, expandable, unlockable. *Acceptance:* unlocking one moves it back into the working batch and re-arms its checks.

**T-052 — Reuse-from-beat.** Copy arrangement from another beat. *Acceptance:* copying then changing one asset produces a different fingerprint.

**T-053 — Footer warning.** Lists what is unresolved in this batch. *Acceptance:* the lock-all button is disabled while the warning is non-empty.

**T-054 — Per-beat lock file.** `06_beats/locks/B###.json`, human-readable. *Acceptance:* the file can be read and understood without the app.

**T-055 — Three queues.** Quick / Think / Make, by the rules in 6.3. *Acceptance:* a beat with a missing asset is in Make, never in Quick.

**T-056 — Fingerprint guard + diff panel.** D1. Refuse the lock; offer the five ways to differ. *Acceptance:* an exact duplicate **cannot** be locked; applying any one of the five clears the block.

**T-057 — Fingerprint definition.** hash(situation + look + asset set + text set). *Acceptance:* changing only the beat's script text does **not** change the fingerprint; changing any listed field does.

---

## PHASE 3 — Style kit, assets, Inkscape

**T-060 — `style_kit` screen.** Background colour, outline rule, head size, grid, palette, font. *Acceptance:* all six are per-channel and all six are editable.

**T-061 — Stein preset, deletable.** The measured numbers from 3.1, shipped as one preset. *Acceptance:* deleting the preset leaves a working empty kit.

**T-062 — `assets` + `provenance` tables.** Kind, svg path, raster path, source, licence, source_url, retrieved_date. *Acceptance:* an asset cannot save without source and licence — the UI refuses, not warns.

**T-063 — Three asset entry paths.** Author / harvest / photo. *Acceptance:* each writes its own provenance shape.

**T-064 — Inkscape headless raster.** SVG→PNG via CLI, never the GUI. *Acceptance:* rasterising 100 assets produces 100 PNGs with no GUI process spawned.

**T-065 — Raster cache.** Keyed on SVG hash. *Acceptance:* re-rasterising an unchanged SVG is a cache hit.

**T-066 — Approve the PNG, not the SVG.** *Acceptance:* the approval UI shows a PNG; there is no "approve SVG" action anywhere.

**T-067 — Harvest flow.** CC0/PD search, download, provenance capture. *Acceptance:* every harvested file has licence text stored with it.

**T-068 — Photo path for places.** The id-minting trap from Part 7: a beat about a **building** must not mint a person's id. *Acceptance:* a place beat and a person beat mint visibly different ids.

**T-069 — Outline rule enforced.** 1.5–2.0% of head height, constant in pixels. *Acceptance:* a generated figure at head height 364 px has a 6 px outline.

**T-070 — Landmark grid helper.** The canon 0.210/0.375/0.500/0.735/0.835. *Acceptance:* the helper returns the eye at 0.500 of head height.

**T-071 — Pixel verification.** Ink-map, row-flip, placeholder-fill detection. *Acceptance:* a deliberately blank frame is **detected as a placeholder**, not passed.

**T-072 — Re-sync the stale pipeline template.** Before using `ms-paint-pipeline`'s `assets/pipeline-template/`, copy the live `wwii-pipeline/pipeline/render.py` + `run.py`. *Acceptance:* template matches live files; diff is empty.

**T-073 — Fix the donor portability defect.** `ms-paint-pipeline/references/wikimedia_fetch.md` contains "velásquez". One-line fix. *Acceptance:* the skill passes its own portability test 9/9.

**T-074 — Environment layer in every look (D19).** `look_env` table; the look editor gains a place layer beneath the slots; a look may not save without either a place or an explicit "flat colour, deliberate" opt-out. *Acceptance:* a beat rendered with a place shows a floor/ground plane under the figures; the opt-out is recorded and countable.

**T-075 — `environment` asset kind + ground-plane authoring.** Authoring flow for a drawn place (floor, room, street, cell), including the ground plane the figures stand on. Reuses the proof run's 7 `env_*.svg` as starting examples. *Acceptance:* an environment asset can be authored, rastered, and placed under a look's slots without occupying a slot.

---

## PHASE 4 — Text desk and render

**T-080 — Text roles.** name / place / date / number / quote / warning, each with a colour. *Acceptance:* six roles exist; colours are per-video.

**T-081 — Choose once per video, override per beat.** *Acceptance:* changing the video default re-colours only beats that were never overridden.

**T-082 — Assert no subtitle track exists.** *Acceptance:* grep finds no narration-caption code path; the docs state Stein uses no narration subtitles.

**T-083 — Delete the donor keyword classifier.** `composer.classify_overlay` maps "any year" → `year_chip` by keyword. That is the same bug class as the skull icon firing on a subscriber beat. *Acceptance:* no keyword→overlay rules remain; roles are user-defined.

**T-084 — Overlay pop timing.** Default ~3.5 s into the beat. *Acceptance:* a frame at 20% of the beat has no overlay; a frame at 88% does.

**T-085 — Render job worker.** Queue + single worker + SSE progress. *Acceptance:* killing the browser mid-render does not stop the job.

**T-086 — Per-segment encode, delete frames after.** *Acceptance:* after a segment, the frames folder is empty and one video file exists.

**T-087 — Frame budget guard.** Warns before a render estimated at 59,400 frames. *Acceptance:* the estimate appears before the job starts, with disk needed.

**T-088 — Cancel and resume.** Cooperative cancel between segments; resume from `render_jobs`. *Acceptance:* cancel at segment 3, restart, and it resumes at segment 3 — not segment 1.

**T-089 — Single-beat preview render.** From the beat card. *Acceptance:* preview matches the full render for that beat, pixel-compared.

**T-090 — Checkpoint gates.** *Acceptance:* render cannot start with any unlocked beat or any unresolved asset.

**T-091 — Handoff bundle.** Frames/timing/asset list + README. *Acceptance:* README contains **no absolute paths** (D12).

**T-092 — AI text-rescan pass (D21).** Runs **after** asset planning, over every beat. For each beat the AI returns either a proposed text item (role, wording, suggested colour, suggested position) **or an explicit "no text needed"** — feasibility is the AI's judgement. The human accepts or rejects per beat. *Acceptance:* on a 30-beat project the pass returns a mix, not all-yes and not all-no; every proposal carries a reason; a rejected proposal does not reappear on re-run.

**T-093 — Text pop-in default, from measurement.** ✅ **DONE 2026-09-25.** Default = **arrives with the beat (position 0)**, because 6.7d found **no evidence of separately-animated text** (0 of 85 events matched a label-shape heuristic). Overridable per beat; the measured **42%-through-the-beat** figure is offered as the alternative for a delayed pop. *Acceptance:* the 3.5 s constant is gone everywhere; default is 0; any entered value renders correctly.

**T-131 — Verify `espeak-ng` actually works.** Only `espeak-ng.dll` exists, unpacked by phonemizer into `%TEMP%` at runtime. *Acceptance:* phonemize a sentence end-to-end and show the output; if it fails, install espeak-ng properly and record the path in 11a.

**T-132 — Probe for Inkscape, never hard-code it.** The MSIX path in 11a is version-pinned and breaks on update. *Acceptance:* with `INKSCAPE_PATH` unset the app finds Inkscape anyway; with a deliberately wrong path set, it reports a clear error naming the executable it tried.

**T-133 — Font picker, per project, from system fonts.** Enumerate `C:\Windows\Fonts\*.ttf` in the UI; let the project pick one; store the choice on the project, defaulting to the channel style kit's font. Ship with `Oswald-Bold` as the channel default (Wasiq to confirm). *Acceptance:* picking a font changes rendered on-screen text; PIL's `load_default()` is never reachable from the text desk — grep finds it only in unrelated code, or not at all.

**T-134 — Copy the chosen font into the project folder.** Do not depend on `C:\Windows\Fonts` at render time; a system font can vanish on another machine. *Acceptance:* rendering works with `C:\Windows\Fonts` renamed away.

**T-094 — Settle whether Stein's text is baked into the art.** 6.7d could not decide between "text arrives with the beat" and "my heuristic is wrong" — **I cannot see images, so a human must look.** *Acceptance:* Wasiq (or anyone who can see) checks ~10 frames and records the answer. Until then T-093's default stands.

---

## PHASE 4B — Motion (added 2026-09-25; do Phase 4 first)

These exist because the original plan had **no motion model at all** — it held a static frame per beat, which would have rendered a slideshow. Defaults are deliberately empty until T-117/T-118 land.

**T-115 — `beat_assets` gains motion fields.** `in_time`, `out_time`, `motion`, `motion_duration`. All nullable. *Acceptance:* columns exist, all default NULL, and a beat with no motion still renders as a held frame.

**T-116 — Motion primitives as data, not code.** `hold`, `pop`, `slide_in`, `drift`, `scale`, `fade` — editable per channel. **No keyword→motion auto-assignment.** *Acceptance:* adding a primitive needs no Python change; grep finds no keyword-mapping table.

**T-117 — MEASURE: intra-beat motion count.** ✅ **DONE 2026-09-25.** Three videos × 90 s @ 10 fps, frame-diff, runs collapsed. Result: **16.0–18.7 small events/min ≈ 1.3 per beat**; duration **≤ 0.10 s (a pop, not a tween)**; 93–94% of frames static. Full numbers in 6.7a.

**T-118 — MEASURE: true beat length and the cut rule.** ✅ **DONE 2026-09-25.** Cut rate 12.0/13.3/14.0 per minute → **beat ≈ 4.5 s**; keyframe-gap median 5.04 s (n = 1062). **Confirms 4.4 s, rejects 2.2 s.** Beats **cut**; carry is the exception. Full numbers in 6.7a.

**T-128 — Asset-count field and range.** Record how many assets a beat holds. Warn below a per-video minimum and above a maximum. *Acceptance:* a beat holding 4 assets is valid; a beat holding 0 is flagged.

**T-129 — Rhythm monotony check.** Flag any run of **4 or more consecutive beats with the same asset count and the same look** — that is what "robotic" looks like mechanically. *Acceptance:* a deliberate run is allowed but must be acknowledged; an accidental one is flagged in the footer warning (T-053).

**T-130 — Decide the slot-vs-scene model.** 6.7c. The harvest says Stein draws a **place** (floor, room, props) and puts figures **in** it; this document builds everything on **slots**. *Acceptance:* a written decision, and either the look editor gains a ground-plane/environment layer, or the finding is explicitly rejected with reasoning.

**T-127 — Re-measure motion at 30 fps.** ✅ **DONE 2026-09-25.** Two videos, 120 s each @ 30 fps. Median event duration **0.033 s = exactly one frame**; max 0.133 s. **Pop confirmed — there is no tween, so no tween engine is needed.** Also re-confirmed beat length at 4.00 / 4.37 s. Full numbers in 6.7d.

**T-119 — Motion editor on the beat card.** A per-asset timeline strip inside the beat duration. *Acceptance:* setting `in_time` to 2.0 s on a 4.4 s beat moves the asset's appearance to frame 60 at 30 fps.

**T-120 — Render a beat as a timeline.** `duration_sec × fps` frames; each asset drawn only inside its window. *Acceptance:* a 4.4 s beat at 30 fps yields exactly 132 frames; an asset with `in_time=2.0` is absent from frame 59 and present in frame 60.

**T-121 — Sticker-event budget check.** Warn when a beat has **zero** motion events (a dead beat). *Acceptance:* a beat with no motion and no overlay change is flagged in the footer warning (T-053).

**T-122 — Beat-to-beat transition as data.** `cut` / `carry`, per beat, default user-set. *Acceptance:* switching a beat from cut to carry changes the render without touching any other beat.

**T-123 — ffmpeg encode redesign.** Segment assembly from per-beat timelines rather than per-beat stills. *Acceptance:* a 10-beat segment with mixed motion encodes to one file with the correct total duration.

**T-124 — Motion preview.** A short looping GIF per beat from the beat card — not a full render. *Acceptance:* preview generates in under 10 s and shows the motion, not a still.

**T-125 — Overlay pop time becomes user-set.** Remove the proof run's 3.5 s constant; it was an implementation choice, not a measurement. *Acceptance:* no hardcoded pop time remains anywhere; default is empty until T-117 lands.

**T-126 — Fill defaults, labelled `measured`.** Only after T-117 and T-118 close. Each filled default records its source and method. *Acceptance:* every default in the style kit carries a `measured` tag with a method string; anything labelled `assumed` is listed for Wasiq to approve or reject.

---

## PHASE 5 — Skill export

**T-100 — Skill pack builder → one `.zip`.** D11. *Acceptance:* running it produces exactly one file.

**T-101 — No system paths.** D12. *Acceptance:* no path in the pack starts with a drive letter or `/Users` or `/home`.

**T-102 — Pack contents.** `SKILL.md`, `recipes/`, `templates/`, `reference/`, `docs/`. *Acceptance:* all five present; `templates/` is empty of project data.

**T-103 — Portability test fails the build.** Grep the built pack for a watchlist (video-specific names, drive letters, absolute paths, the owner's username). *Acceptance:* seeding a watchlisted string makes the build **fail**, not warn.

**T-104 — Assisted mode.** With no API key, every AI step becomes a blank form. *Acceptance:* with no key, a full pass is completable by hand with zero errors.

**T-105 — Docs inside the pack.** Plain-language 9-step guide using the locked vocabulary. *Acceptance:* a reader who has never seen this file can complete a beat.

---

## PHASE 6 — Voice (optional, D10)

**T-110 — Voice install script.** Installs `requirements-voice.txt`; detects espeak-ng and reports clearly if missing. *Acceptance:* running it on a clean machine either succeeds or names the exact missing binary.

**T-111 — S16 Voice screen, hidden until deps present.** *Acceptance:* with voice deps absent the screen is not in the sidebar; installing them makes it appear.

**T-112 — Kokoro + espeak-ng wiring.** *Acceptance:* synthesising one beat produces a valid audio file.

**T-113 — Duration from audio length.** *Acceptance:* a beat whose audio is 5.2 s becomes 5.2 s; one whose audio is 7 s is **capped at 6.0** (D13) and flagged.

**T-114 — Mux audio into segment.** *Acceptance:* the encoded segment has exactly one audio track with matching duration.

---

## Ticket count

| Phase | Tickets |
|---|---|
| 0 Foundation | 12 |
| 1 Script → beats → point | 13 |
| 2 Situations, looks, beat board | 18 |
| 3 Style kit, assets, Inkscape | 16 |
| 4 Text + render | 15 |
| **4B Motion** (added 2026-09-25) | **16** |
| 5 Skill export | 6 |
| 6 Voice (optional) | 5 |
| **Environment probes** (added 2026-09-25) | **3** |
| **Total** | **105** |

T-001 through T-130 with gaps for insertion.

**Phase order:** 0 → 1 → 2 → 3 → 4 → **4B** → 5 → 6.
T-117 and T-118 are **closed** (measured 2026-09-25); T-127 is their follow-up at higher frame rate.

---

## OPEN QUESTIONS — ALL FOUR ANSWERED 2026-09-25

Wasiq answered all four. Recorded as **D18–D21** in Part 4. Kept here for the reasoning trail.

### Q1 — How long is the video, really? **→ ANSWERED: C**

At Stein's measured rhythm (4.5 s/beat), **450 beats = 33.8 minutes**, not 20.

| Option | Beat | 450 beats = |
|---|---|---|
| **A** — accept Stein's rhythm | 4.5 s | **33.8 min** |
| **B** — shorter beats than Stein | 3.0 s | 22.5 min |
| **C** — variable, per beat, capped | 0.5–6.0 s | whatever the script earns |

*My opinion: **C**, with a default of 4.5 s and the existing 6.0 s cap (D13).* Reasoning: a beat should be as long as its sentence needs. A hard uniform 4.5 s is exactly the "robotic" failure he is guarding against, and a fixed 3.0 s would cut against the one number we actually measured from Stein.

### Q2 — Slots, or scenes? (the big one — 6.7c) **→ ANSWERED: B**

The harvest says Stein draws a **place** — floor, room, props — and stands figures in it. This document builds everything on **slots**: named rectangles each holding one asset.

| Option | Consequence |
|---|---|
| **A** — keep slots | Faster to build. Risks reproducing the "beats have no place in them" problem. |
| **B** — add an environment layer under the slots | A look = a place + figures in it. Closest to Stein. More work in the asset desk. |
| **C** — both, chosen per beat | Most flexible, most UI. |

*My opinion: **B**.* Reasoning: it is the only option that addresses a measured finding rather than ignoring it, and it does not throw away the slot work — slots become positions *within* a drawn place. **C** is tempting but two models means every downstream rule (fingerprint, repeat guard, look editor) needs branches.

### Q3 — Should the app enforce an asset-count range per beat? **→ ANSWERED: warn, don't block**

*My opinion: **yes — warn, don't block.*** Minimum 1 (flag 0 as a dead beat, which T-121 already does), soft target 2–4, no hard maximum (Stein's cast grid reaches 5–6, and my layouts reach 8). Reasoning: a hard cap would forbid the cast grid, which is his most-recurring composition.

### Q4 — On-screen text: when does it appear? **→ ANSWERED: reframe**

Wasiq did not answer the timing question. He reframed it:

> *"for every beat, when after asset planning, it should rescan for beats that should contain text overlays where AI sees it feasible"*

So the answer is **workflow, not timing**: an AI pass after asset planning that proposes text **only where the AI judges it feasible** — a mix, not all beats. Recorded as **D21**, ticket **T-092**.

**The timing was then measured anyway** (he accepted the suggestion): events land **42% through the beat** on average, and my old 3.5 s constant was **80% through — far too late**. See 6.7d. Default is now **arrives with the beat**, because no separately-animated text could be detected.

---

## Status: unblocked

All four blockers are resolved. **No ticket is blocked on a decision from Wasiq.** Implementation may begin at Phase 0 on his go.
