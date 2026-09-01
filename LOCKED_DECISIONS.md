### Phase map additions
- P12 scope widened: **World Scan** — real-world entities (revised §4.9) + meme hooks + map/place-era triggers. Detection only; feeds P22 (fetch) and P24 (shot types).
- **P24 (NEW) — Special Shot Types & Inserts:** trigger-rule engine (condition → shot type), per-type prompt recipes & formats (flag-fill map, region-highlight map, paper map, split map, future custom types), beat-referencing rules. Design after P22.
- P09–P11 passes emit a "world annotations" list (place/era, brand, meme hooks) as future fuel for P12/P24.
- Real-world chain locked: detect (P12) → fetch (P22) → reference at beats (P20). Never detected at beat time.


# 🔒 LOCKED DECISIONS — AI Production Asset Pipeline App

> Living document. Every discussed phase ends here with its decisions locked.
> Rule: once locked, a decision only changes through an explicit "unlock" decision.

**Working title:** TBD
**One-line stack:** Python + FastAPI backend · localhost web app · OpenAI-compatible LLM layer · React frontend

---

## ✅ P01 — Architecture & Tech Stack (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | App architecture | **Localhost web app** — local server + browser UI, everything on this machine. Only LLM requests ever leave it. |
| 2 | UI ↔ brain separation | **Hard rule:** all logic lives in the Python backend (the brain). The UI only displays and asks. The UI is swappable (QML / desktop wrapper) later without rewriting logic. |
| 3 | Backend | **Python + FastAPI** — files, SQLite projects, JSON, LLM calls, and the future web-fetch module (P22). |
| 4 | LLM layer | Official **`openai` Python library with `base_url` override** → works with any OpenAI-compatible endpoint/key. One client layer serves every pipeline phase. |
| 5 | Frontend | **React (Vite) + Tailwind CSS** — premium, modern AI-SaaS look. Optional component kit later (e.g., shadcn/ui). Nothing heavier until we feel pain. |
| 6 | Secrets / config | One **local settings file** in the app folder: endpoint URL, model name, API key. Plus an in-app **Settings screen** to paste/edit the key once. Never hardcoded. |
| 7 | Launch | **One-click launcher** — boots the local server and opens the app automatically. |
| 8 | v1 window | **Browser tab on localhost is fine.** Desktop-window wrapper (pywebview/Tauri) remains optional later. |

### Notes
- Environment is ready: Python, Node, React, QML all installed — no setup hand-holding needed.
- Dev setup: Vite dev server proxies `/api` to FastAPI (standard, clean).
- **Rejected alternative:** QML-native — steep curve, few ready-made parts, slow iteration. Revisit only as a later "skin" thanks to Decision #2.

### Future considerations (NOT locked)
- Possible deployment (e.g., Vercel) someday → API-key handling must be redesigned first (key exposure). Out of scope for v1.
- Optional obfuscation of the local key file.

### P01 amendment #3 (UI/UX)
- Theme locked: "Pixel Platformer" — original 8-bit platformer skin
  (Super-Mario-inspired, zero Nintendo assets).
- UI_UX.md adopted: tokens (sky/cream/brick + semantic green/amber/red),
  fonts (Press Start 2P display / Pixelify Sans headings / Nunito body),
  hard-shadow block components, textured sky background, flat panels.
- Screen inventory S01–S17 + G01–G02 is the frontend build map.
- Perfection strategy: locked system first, pixel-tuning by eye right after shell exists.

---

## 📝 Changelog
- **v0.1** — P01 locked (localhost web app, Python+FastAPI, openai-compatible LLM layer, React+Tailwind, local settings file, one-click launcher).

## ✅ P02 — Project & Data Model (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Hierarchy | **App → Channels → Projects.** Each channel owns its style-kit, avoid-list, background rules, resolutions, and cross-episode library. Every video is a project inside a channel. |
| 2 | Storage engine | **Hybrid, both first-class:** every artifact saved as its own human-readable file (txt/md), *and* a `project.db` (SQLite) as the app's working brain. DB can be **rebuilt from files** anytime (repair button). |
| 3 | Portability | A project = one folder. **One-click zip download** (files + DB); import via zip/folder; renameable; projects dir **auto-scanned on launch**. |
| 4 | Multi-user | App supports **multiple user accounts** (team of ~3–4 non-technical users; single developer). Auth/roles: detailed later. |
| 5 | Navigation model | **Free navigation + smart ripple.** No locked steps. Dependencies govern *generation only*. Upstream edits flag downstream items **stale** (never deleted/blocked); one consolidated ripple-review screen with **keep / regenerate / decide-later** per item; permanent **Changes inbox**. |
| 6 | Versioning | **Never overwrite.** Locking snapshots a version; edits/regenerates create new versions; revert to any version always possible. Regenerate buttons everywhere. |
| 7 | IDs | **App-owned.** Short internal IDs; channel/episode prefix auto-added at export; uniqueness enforced by DB. Exact per-section schemes to be defined with the user section-by-section (PDF IDs are a draft). |
| 8 | Asset metadata | Uniform record: `id, kind, status, prompt_text, model, seed, background_color, references, timestamps`. Status ladder: `draft_prompted → draft_imported → approved → final`. |
| 9 | Background color | Default fixed chroma-green; **auto-flips to white** when the asset's own palette contains green; recorded per asset so the editor knows what to key (§6). |
| 10 | On-disk readability | **Explorer-friendly** project folders, stable naming, `README.txt` per project explaining the layout; **rescan button** to pick up edits made outside the app. Exact file arrangement: user to define later. |
| 11 | Exports | **Both .txt and .md mirrors**, in separate folders inside the project zip. |
| 12 | Context passing | Deferred to **P03** (global strategy) + handled per-phase. |

### Notes
- The linear "gates as disabled steps" idea was **rejected** (user examples: direct entry to title/script; mid-pipeline script-line edits). Replaced by Decision #5.
- Multi-user changes P01's deployment note: hosting model (shared PC vs LAN server vs cloud) is now a real future decision, not a fantasy.
- User confirmed: project duplication/fork feature stays.

### Open items (parked, not blocking)
- How the team physically runs the app (one machine / LAN / deployed) → shapes auth design.
- Exact on-disk file arrangement (user will specify).
- Per-section ID schemes (user will specify per phase).

---

### P01 amendment
- **Deployment target: cloud** (team lives in nearby apartments; no manual installs).
  Dev stays localhost-first; the app is architected to deploy as-is later
  (FastAPI + React is cloud-friendly). Consequences parked for later phases:
  real login/roles, server-side key storage, cloud file storage, team permissions.

### P02 amendment (Decision #5, ripple UX)
- Granular regeneration: the ripple review screen lists every affected beat with
  checkboxes → **regenerate only the selected beat prompts**. Independently of the
  ripple, **every beat card always carries its own "regenerate" button**.
  Old versions are kept either way.

### P02 amendment #2 (ID registers)
- Three ID registers: semantic (AI-facing, name-first) · internal short (app) ·
  export-prefixed (files/handoff ONLY — never included in LLM context).

---

## ✅ P03 — LLM Orchestration Core (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Recipe cards | One plain-text prompt template per job type, versioned, tunable without code changes. |
| 2 | Pass structure | Per the Job Map: ideation/titles/analysis = 1 pass; script = 2–4 passes; sheet prompts = 1 pass per character / per environment; beat jobs defined in P19/P20. Actions detected & approved BEFORE sheet prompts. |
| 3 | Context packs | Per-job recipes: full script for all analysis/sheet/beat jobs; style text-descriptor + avoid-list for prompt jobs; approved-sheet registry + prior beats for beat jobs (§4.5 generalized). |
| 4 | Image-reference split | Chat LLM gets text anchors only. Prompt cards carry a "references to attach" field (style-kit files, prior sheet files) for the external image step. |
| 5 | Output shape | Analysis/beat jobs = validated JSON; JSON mode if available; auto-repair retry once; then error badge + **manual override always available**. |
| 6 | Model tiers | 3 settings slots (Light/Medium/High) + "use one model" checkbox collapsing UI to a single field. Default tier mapping per Job Map; per-job override later. |
| 7 | Temperatures | Creative ~0.8–1.0 · precision ~0.1–0.3 · prompt-craft ~0.5 (defaults, tunable). |
| 8 | Job logging | Every call logged (inputs, context, model, temp, raw + parsed output, tokens, time). Transparency panel: summarized, auto-scoped per beat/job, hidden from teammates. |
| 9 | Streaming | Long-form jobs (script) stream into the editor. |
| 10 | Queue | FIFO job queue for multi-user; tiny "queued" badge. |
| 11 | Vision pre-check | Automatic pre-screening DROPPED. Optional on-demand "AI analyze draft" button at checkpoint — parked. |

### Open items (parked)
- Beat length, chunk→beat granularity, per-beat vs per-chunk generation → **P19/P20**.
- Script pass structure (outline-first? section-by-section?) → **P06**.

---

### P02 amendment (Decision #7 finalized)
- ID scheme fully app-owned, per the table above (decided by architect, user opt-out).
- Internal IDs short; channel+episode prefix auto-applied at export only.

---

## ✅ P04 — Ideation Intake (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Screen model | Minimal canvas: one generous text area + "Refine & expand" + "Surprise me" + skip doors to P05/P07 (§1.1). Optional chips (category, tone), never required forms. |
| 2 | AI pass | Single pass, High tier, temp ~0.9, streamed. Produces a structured **Idea Card**: concept, 2–3 hook candidates, audience appeal, category tags (AI-suggested, free-form), production-scale estimate (cast/env count), real-world watchout (→ P12). |
| 3 | Interactive cards | Every idea is a selectable card → detail view with full stats → free-form "refine to my liking" loop; versions preserved. |
| 4 | Surprise me | ~6 fresh concepts, context-fed with channel history (later: P23 performance data). Adopt-to-textarea in one click. |
| 5 | Idea Shelf | Per-channel "someday" list of cards; any card promotable to project anytime. |
| 6 | Fast-lane | Rich/detailed input → offer "skip refinement, straight to titles." |
| 7 | Tone | Channel-level tone inherited automatically; no per-idea tone field. |
| 8 | Overrides | Card fully hand-editable; refinement optional; skip always available. |

## 🔭 P23 — Channel Intelligence / Performance Feedback Loop (SCOPE LOCKED, design later)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Inputs | Per published video: title, description, tags, thumbnail, views, impressions, AVD/retention, drop-off timestamps. v1 = manual entry/CSV; API pull parked. |
| 2 | Retention mapping | Drop-off timestamp → word position (150 wpm) → exact chunk/beat → AI analyzes why. |
| 3 | Output | Structured **Lessons file**: observation + evidence + proposed tweak + target recipe + confidence + status. |
| 4 | Safety | AI proposes; human approves (diff view). Active lessons inject into relevant context packs. All versioned/revertable. Nothing auto-applies. |
| 5 | Parked | Thumbnail vision analysis; YouTube API auto-pull; statistical significance tooling. |

### Tracker updates
- P04 → ✅ LOCKED
- Add: P23 Channel Intelligence — 🔭 SCOPE LOCKED (design after P22)

---

## ✅ P05 — Title Generation (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Pass | Single call, High tier, temp ~0.9. Context: idea card + channel tone + past titles (dedupe) + future P23 lessons. No fine-tuning (§1.1 "trained model" rejected). |
| 2 | Candidates | Default 10 (adjustable 5–20); each carries text, one-line angle, style tag, char count. Diversity rule: styles/structures/lengths must vary. |
| 3 | Selection UX | Card grid; shortlist/edit/remix; regenerate-selected or reroll-all; pick → lock (versioned). |
| 4 | Override doors | "Use my own title" + edit-then-lock always available (manual-always-valid). |
| 5 | Platform checks | Live char count; >~70 chars warns + AI suggests shortened variant. |
| 6 | A/B alternates | One primary locked title + optional alternates; "shipped title" marked at export for P23. |
| 7 | Entry points | Reachable from idea card OR directly from home screen (§1.1 title-first door). |
| 8 | Ripple | Title goes stale-dot if upstream idea card changes; keep/regenerate via ripple review. |
| 9 | Handoff to P06 | Locked title + idea card + channel tone = script-gen context. Title is nullable (script-first entry skips it). |

---

## ✅ P06 — Script Generation (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Word-count contract | Bidirectional slider **500–5,000 words** (50-word steps) ↔ live duration @ **150 wpm**. Type a duration → slider follows; move slider → duration follows. |
| 2 | Pass 1 — Outline | Medium tier, temp ~0.7. Output: section headings + summaries + hook placement + turn markers. Reviewable/reorderable/editable; **skippable** (AI self-structures). Cheapest reshape moment by design. |
| 3 | Pass 2 — Full draft | High tier, temp ~0.8, **streamed**. Context: idea card + title + tone + approved outline + target. Word-count guardrail: per-section weighted targets, total lands ±10%. |
| 4 | Pass 3 — Punch-up | High tier, temp ~0.7. Per-section, on-demand, free-text note, repeatable. Old versions preserved (P02 versioning). |
| 5 | Pass 4 — Consistency check | Medium tier, temp ~0.2. One-click "Final check": name inconsistencies, timeline gaps, tone drift, repetition, hook-strength note, **narration flags** (tongue-twisters, >30-word sentences, phonetic collisions). |
| 6 | Word-count breakdown | Sidebar: per-section counts + % of total; one-click **rebalance** → targeted Pass 3. |
| 7 | Hook audit | First ~75 words permanently highlighted in the editor. |
| 8 | Tone samples | Channel-level, 2–3 example paragraphs ("this is how we sound"), injected as concrete anchors into Pass 2. |
| 9 | Live footer | Word count + duration always visible in-editor, updating on type/stream. |
| 10 | Fail-cheap ordering | Passes ordered by correction cost: outline (free to change) → draft → section punch-up → QA. |

---

## ✅ P07 — Script Import / Edit / Lock (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Screen model | P06 + P07 are ONE screen — the Script Studio. Generation is how scripts arrive; the lock is how they depart. |
| 2 | Two arrivals | From P06 (AI draft in editor) OR script-first: paste text / drop .txt/.md → instant local word-count ÷ 150 wpm duration readout, no AI needed. |
| 3 | Lock mechanics | Lock = version snapshot + recorded stats (words, duration, sections, who/when) + unlocks analysis (§2.1) + starts the ripple clock. |
| 4 | Unlock | No ceremony — editing IS unlocking; version bumps; ripple flags downstream; review screen handles consequences. |
| 5 | Lock permissions | Anyone on the team may lock; audit line records who/when. No permissions maze. |
| 6 | Auto-sectioning for imports | Optional Medium-tier pass producing the same outline structure P06 emits. Skippable — beats work without it (§4.1), only the breakdown panel is lost. |
| 7 | Finalization learning hook | On lock, the app captures: full version history (draft → final diff), edit patterns (what user cut/added/rephrased), and flags the script as a positive sample for **P23**. Later joined with published metrics → the system learns WHY you liked it. |
| 8 | Pre-lock sanity card | Non-blocking 3-line glance: duration vs target, word count, sections, consistency-check status. |
| 9 | Lock & continue | Smart next-step button (analysis / style-kit / pipeline map). |
| 10 | QA parity | Pass 4 consistency+narration check available to imported scripts, not just AI-generated. |
| 11 | Pacing strip | Whisper-thin per-section rhythm dots in the footer (optional garnish, approved). |

---

## ✅ P08 — Global Style Kit (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Home | Channel-level. Each channel owns its kit; projects inherit automatically; never per-project (§1.2 fixed style). Second style = second channel. |
| 2 | Reference images | Upload once (2–4 files), stored in channel folder; listed on EVERY prompt card's "references to attach" field. |
| 3 | Text descriptor | AI drafts it from your images via one vision call (fixed slots: line quality / color / shading / proportions / backgrounds / never-does); you edit/approve; hand-editable forever. |
| 4 | Descriptor↔images split | Descriptor → our LLM (prompt writing). Images → external image tool via prompt cards. §1.2 honored at generation time. |
| 5 | Tone samples | Live in the kit (channel identity), written once, injected into script recipes. |
| 6 | Avoid-list | §7's five rules pre-loaded; editable, versioned checklist per channel; auto-appended to every prompt. |
| 7 | Background rules | Default chroma green (standard hex, editable per channel); conflict → white; proactive green-conflict hints at extraction (P09+), confirmed at checkpoint. |
| 8 | Resolutions & scale | Env 1920×1080 16:9 · character sheets ~3:4 portrait · scale-reference notes mandatory in env prompts (rule here, executed at P15). |
| 9 | Versioning + ripple | Any kit change → style_kit_vN snapshot; in-flight projects get amber flags, keep/regenerate per item. |
| 10 | First-run | ~5-minute wizard: upload → AI descriptor → confirm defaults → tone samples. Kit test-prompt button for fail-cheap validation. Kit health checklist advisory, never blocking. |

---

## ✅ P09 — Character Extraction (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Pass | Single Medium-tier pass (temp ~0.2) on the LOCKED script (§2.1). Defensive split: auto-fan-out if >4,000 words or pre-scan cast >20; manual re-run sharded available. |
| 2 | Artifact 1 — Registry | Per-character record: ID, kind (named/generic), names + alias map, faction, role, appearance slots WITH source notes, presence sections, green-conflict flag, library match. |
| 3 | Artifact 2 — Mention Map | Per-instance resolution table (mention, resolved ID, confidence, context). Low-confidence rows amber-highlighted in the inspector. Backbone for P20 SVO. |
| 4 | Significance pick | AI tags core/supporting/minor. Core = permanent, auto-included. Supporting/minor = user toggles: full character / bundle to generic / drop to text-only. |
| 5 | Generic bundling | Per faction (§2.3), one C-series with kind+faction fields; split/merge tools on the Cast Board. |
| 6 | Host | Optional channel-kit checkbox → host builder → channel library asset with channel-level sprite sheets, reused by all projects; host slots only (intro/outro/interstitial); versioning + ripple on redesign. |
| 7 | Library check | Extraction queries channel library first (§10); one-click reuse swaps record to library reference. |
| 8 | Scale reality check | Extracted cast vs P04 idea-card estimate; mismatch flagged pre-sheets. |
| 9 | Re-extraction | Diff & merge against human edits; never overwrite. |
| 10 | World annotations | Pass also emits place/era, brand, meme-hook annotations → future fuel for P12/P24. |
| 11 | Cast Board | Card-per-character UI; edit/promote/demote/split/merge/add; resolution inspector collapsed by default; manual-always-valid. |

### P09 amendment (person classification)
- P09 mints IDs for ALL persons: C## if drawn, RW## if fetched.
- Default rule: pre-photography-era → drawn; photography-era recognizable → fetched.
- Cast Board toggle per person (drawn ↔ fetched), free at P09 (zero downstream cost).
- P10 plans variants for drawn entities only.
- Fetched persons flow to P12 for enrichment (1–4 word search queries, era hint, usage intent).
- Late flips anywhere = ripple correction with visible re-run cost shown before confirm.
- Layer rule locked: drawn = actor layer (lives inside MS Paint world);
  fetched = insert layer (interrupts MS Paint world — PiP, corner graphic, screen-within-screen).
- Beat prompts tag every asset reference with its layer (actor | insert).

---

## ✅ P10 — Character Variants (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Pass | Dedicated Medium-tier pass (temp ~0.2): full script + P09 registry. Separate from P09 by design. |
| 2 | Artifact | Per-character **variant timeline**: variants (ID, span, delta-from-master, evidence, confidence) + **rejected-changes list** (considered-but-declined, with verdict). |
| 3 | Variant rules | §2.4 as-is: age category / permanent state (wounded, scarred, extended disguise, death) / persistent outfit-role change. Minor changes = actions, not variants. |
| 4 | Timeline screen | Horizontal per-character strips; merge/split spans, edit deltas, adjust boundaries; each variant labeled "+1 sheet"; low-evidence spans dashed. |
| 5 | Cost control | Variants spanning ≤2 beats → auto-suggest demotion to one-off poses (§3.3) chained to master sheet. Death/state variants may use minimal sheets (2 actions). |
| 6 | Delta-only descriptions | Variants store only what changed vs master; prompts chain master sheet image + delta text (§5 inside a character). |
| 7 | Timeline = truth | P20 auto-resolves active variant per beat from spans — zero per-beat guessing. |
| 8 | Contradiction detector | Spans checked against P09 Mention Map presence distribution; mismatches flagged. |
| 9 | Ripple | Script edits re-propose variants via diff/merge; human edits sacred. |

---

## ✅ P11 — Environment Extraction (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Pass | Single Medium-tier pass (temp ~0.2): full script + character registry + P09 world annotations + library index. Defensive split same as P09. |
| 2 | Registry record | ID, name, elements (structured 3–4 list per §2.6), variations (state, span, evidence), green_conflict flag, presence sections, library match. |
| 3 | Variation rule | Same location + different state (season / time-of-day / scene-state, §2.7) = variation, never a new environment. Trimmable by user (quality over quantity). |
| 4 | Sheets | One sheet per environment, variations boxed, sheet ID (§2.7) — planned here, executed at P15. |
| 5 | Green conflicts | Proactive white-background recommendation on nature/green-palette environments; confirmed at checkpoint. |
| 6 | Scout Board | Card per environment; edit elements, merge over-splits, split, dismiss bad promotions, hand-add; dashed shading for low-evidence variations. |
| 7 | Cost controls | Environment count vs P04 idea-card estimate flagged pre-sheets; ≤2-beat environments default to single-box minimal sheets. |
| 8 | Library reuse | Generic places check the channel library first (§10), one-click reuse. |
| 9 | Cross-audit | Character-presence vs environment-span contradiction check between the two registries. |
| 10 | Ripple | Script edits re-propose via diff/merge; human edits sacred. |
| 11 | Boundary | §4.7 reference scenes stay parked (P24 / user-defined); P11 plans location variations only. |

## ✅ P12 — World Scan / World Desk (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Scope | Brands/logos/trademarks + meme hooks + map triggers + enrichment of fetched persons pre-seeded by P09. NO person classification here (P09 owns it). |
| 2 | Pass | One dedicated sweep, Medium tier, temp ~0.2; context: full script + P09–P11 world annotations + P09 fetched-person seeds. Defensive split same as P09. |
| 3 | RW record | id (RW##), type (brand_logo / trademark / real_person / meme), text, script context, usage intent (on_screen_insert / background_prop / text_only), era hint, **search_query (1–4 words)**, optional usage-note, status. |
| 4 | MT record | id (MT##), place, era_hint, evidence, suggested map template (flag_fill / region_highlight / paper / split — finalized at P24). |
| 5 | Meme dual-mode | fetched_template (insert layer) OR in_style_parody (drawn → actor layer, generated via P24 chained to character sheets). Mode choice sets the layer tag. |
| 6 | Layer rule | All fetched RW = insert layer (interrupts the MS Paint world). in_style_parody = actor layer. Tag travels with every beat reference. |
| 7 | World Desk board | Cards grouped by family; approve / dismiss / edit / choose meme mode / set usage intent / hand-add. Manual-always-valid. |
| 8 | Feeds | RW → P22 (fetcher executes queries, you approve results). MT → P24. Approved records → P20 context pack; beats cite RW01/MT01 like any asset. |
| 9 | Dismissal memory | Project-level: dismissed/text_only choices inform future suggestions. |
| 10 | Era-awareness | Fetch hints and queries carry era (1980s Apple logo ≠ current). |

---

### P13 amendment #1 (lean sheets)
- Sheets stay lean by default: <6 poses, ONLY script + mandatory poses included.
- Buffer poses move to a "suggested additions" tray — proposed by AI, added ONLY
  by explicit user action. §3.1 discretion becomes propose-not-include.

### P13 amendment #2 (library context)
- Library extension sheets save WITH context: source episode, situation tags
  ("rowing", "crowd panic"), use-case line — searchable at future fetch time.
  (Feeds P18 library design.)

## ✅ P13 — Character Action/Pose Inference (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Pass | One Medium-tier pass (temp ~0.4) per drawn variant; host at channel level if sheets missing. |
| 2 | Output | Pose list per variant: id, type (physical/expression), human-readable name, evidence, priority (script / mandatory). |
| 3 | Lean default | Sheets <6 poses, script+mandatory only. Buffers proposed in a suggestions tray; opt-in add only. |
| 4 | Mandates | Neutral expression mandatory per variant set; expression poses required, not optional (§3.1). |
| 5 | Packing | >6 poses → type-grouped sheets (action sheet / reaction sheet), each <6. Grid proposed by AI, overridable (§3.2). |
| 6 | Isolation | No multi-character poses on any sheet (§0 at pose level). |
| 7 | Minimal sheets | Death/state variants get exactly 2-action sets (P10 rule). |
| 8 | Choreography Board | Add/cut/move poses across sheets; live "+1 sheet" counter; suggestions tray; thin-coverage note at ≤3 poses. |
| 9 | Library extensions | Missing poses on reused library characters → extension sheet chained to library sheet (§5), saved to library BY DEFAULT with context metadata (source episode, situation tags, use-case line); per-case toggle to project-local. |
| 10 | Ripple | Pose-list re-proposal on script/variant edits via diff/merge. |

---

## ✅ P14 — Character Sheet Prompt Assembly (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Pass | One High-tier pass (temp ~0.5) per character, assembling ALL of that character's sheet cards (master first, variants chained). |
| 2 | Card anatomy | Fixed 8 slots, stable order: [1 STYLE] descriptor verbatim · [2 IDENTITY] master-only full block · [3 DELTA] variant-only delta text · [4 POSES] per-pose lines · [5 ISOLATION] · [6 BACKGROUND] · [7 AVOID] verbatim · [8 PARAMS] (3:4 portrait, grid, draft-first). |
| 3 | Chaining | Master sheet = full identity. Variant/extension sheets = delta + master image in "references to attach" (§5). Style-kit refs on every card (§1.2). |
| 4 | No-pronouns rule | **Critical (user-emphasized):** every pose line repeats the character's name; zero pronouns inside prompt text. |
| 5 | Background logic | Green hex auto-written; white auto-substituted when P09 green_conflict flag set (§6). |
| 6 | Draft-first | Flag on every card (§4.8); metadata slots (model/seed/background_color) present (§4.10). |
| 7 | Card lifecycle | Editable text, versioned, regenerate with diff preview; slot-stable regeneration (only changed slots rewrite). |
| 8 | Lint | Pre-export check: all 8 slots + references + params present, else error badge (P03 validation discipline). |
| 9 | Batch order | Master sheets → variants → extensions (dependency order). |

---

## ✅ P15 — Environment Sheet Prompt Assembly (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Pass | One High-tier pass (temp ~0.5) per environment. Parallel-safe in batch export (depends only on style kit). |
| 2 | Card anatomy | Fixed 8 slots: [1 STYLE] · [2 IDENTITY] (combined elements) · [3 BOXES] (visual separation, no text) · [4 SCALE] (relative to Canonical H) · [5 ISOLATION] · [6 BACKGROUND] (Green/White logic) · [7 AVOID] · [8 PARAMS] (16:9, draft-first). |
| 3 | Box map | Box-position ↔ variation-ID map lives in **metadata only**; image contains no labels/text (§7). |
| 4 | Scale & Compositing Split | **Prompt** contains scale notes (element size relative to H). **Metadata/Editor Notes** contains compositing guides (standing plane, horizon line) — *never* sent to image generator to prevent hallucination. |
| 5 | Minimal sheets | ≤2-beat environments default to single-box cards (no variations). |
| 6 | Spans in metadata | Each box carries its script span (from P11), documenting the chain for P20. |
| 7 | Lint & Lifecycle | Pre-export lint (slots + refs + params); editable text, versioned, slot-stable regen. |

---

## ✅ P16 — Prompt Export Package (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Package | Folder: `prompts/` (one .txt/.md per card) · `references/` (copies of all attach-listed images) · `manifest.json` · `README.txt` · **`editor_notes/`** (per-asset compositing notes, never in prompts). |
| 2 | Status on export | All cards `draft_prompted`; README instructs drafts-first (§4.8). |
| 3 | Return convention | `[CardID]_draft.png` / `[CardID]_final.png` → P17 auto-matches via manifest/filename. |
| 4 | Helpers | Batch clipboard-copy script included; generated one-page **Generation Checklist** (counts by type/ratio). |
| 5 | Portability | Self-contained zip; usable without the app installed. |

### Tracker updates
- Add: **P25 — Text-Only Beats & Overlay Spec** (parked, design after P24; overlay style tokens likely channel-kit).

---

## ✅ P17 — Asset Import & Quality Checkpoint (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Import | Drop folder/zip; `[CardID]_draft.png` / `_final.png` auto-match cards via manifest/filename (P16 convention). |
| 2 | Auto background check | Local corner-pixel sampling verifies actual background ≈ expected chroma hex or white — zero AI, instant amber flag on mismatch. |
| 3 | Checkpoint Board | Thumbnail grid with status chips; triple view on click: draft \| style-kit refs \| master sheet. |
| 4 | Approve rule | Four-point checklist mandatory (§3.4): style consistency · background correct · proportions/attire correct · isolation clean. |
| 5 | Status ladder | draft_imported → approved → final; rejected carries reason (taxonomy: style drift / wrong background / proportions / extra elements / other) → card tweak → re-export loop. |
| 6 | Metadata capture | Seed + model filled at import (or parsed from filename); required for `final`, optional at draft (§4.10). |
| 7 | Gate | Beats may

---

## ✅ P18 — Cross-Episode Asset Library (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Scope | Per-channel library. Reuse = reference record (not copy); pre-approved at citation; export prefix keeps uniqueness. |
| 2 | Entry rules | Auto-promote: generics, host, extension sheets (with context metadata). Opt-in: named characters, story environments. |
| 3 | Kit-version safety | On reuse, brain compares kit versions. Mismatch flags: "reuse as-is" OR "regenerate under current kit" (draft-first). |
| 4 | Management | Retire-not-delete. Editable tags. Duplicate guard on save (similarity check). |
| 5 | Matching | Extraction passes (P09/P11) receive library index; propose matches with confidence. Library screen for manual browse/search. |
| 6 | Metrics | Savings counter per episode. Usage count per entry (surfaces workhorses vs dead weight). |
| 7 | Export | One-click library manifest (backup/audit file). |

---

## ✅ P19 — Chunk & Beat Splitting (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Chunking | Pure local sentence tokenizer — zero AI cost. Chunk ends at full stop (§4.1). |
| 2 | Beat splitting | Medium-tier pass (temp ~0.2), batched 5–10 chunks per call; context = chunk + neighboring sentences. |
| 3 | Beat length | Target 6–14 words; hard rule: clause/comma/conjunction boundaries, never mid-thought (§4.2). Beats never cross chunk boundaries. |
| 4 | Prompt unit | **Per beat, never per chunk** (parked question resolved). |
| 5 | Beat Board | Chunk-grouped list; word counts visible; manual merge/split always available. |
| 6 | Pacing tools | Pacing visualizer (word-count bars); auto-merge micro-beats (2+3 words → one). |
| 7 | Text-only | AI softly pre-flags candidate text-only beats; confirmed at P20. |
| 8 | Ripple | Script edits flag affected beats; every beat carries its own regenerate button. |

---

## ✅ P20 — Per-Beat Prompts (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Pass | One High-tier pass (temp ~0.5) per chunk. Context: full script + approved-sheet registry + established-references rollup + last 2–3 beats' prompts + variant timelines + mention-map rows + RW/MT records + descriptor/avoid-list + active lessons. |
| 2 | Reuse-first rule | Elements match existing approved poses/boxes first (no new generation). New image prompts ONLY for gaps → §3.3 one-offs (chained to sheet, improv_note attached, not added back; promote-to-library door via tray). |
| 3 | Element record | instance B###-I# + asset_ref + layer tag (actor/insert) + framing + prompt (one-offs only) + refs-to-attach + compositing note (editor-only). |
| 4 | Rules enforced | Nothing mandatory · isolation per element · no pronouns in prompts · crowd cap ≤4 detailed · framing variety with rhythm advisory · text-only confirmed here with sanity nudge · host-slot suggestions. |
| 5 | SVO | Stored hidden per beat; reveal toggle on demand (§4.3). |
| 6 | MT placeholders | Map elements carry MT ref; P24 backfills the prompt recipe. |
| 7 | Beat Studio | Row per beat (VO line, element chips, framing, badges); detail view with prompts + SVO; per-beat regenerate; edit prompts; toggle text-only. |
| 8 | Output | The alignment table: B### \| VO line \| asset tags (+layer) \| text-only flag — the P21 deliverable. |

---

## ✅ P21 — Beat Export & Editor Handoff (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Default package | `HANDOFF_[EP]_[version]/` containing: `alignment_table.md/.txt` (B### \| VO \| asset tags + layer \| framing \| duration \| text-only), `manifest.json`, `assets/`, `one_off_prompts/`, `inserts/`, `editor_notes/`, `text_only_beats.md`, `README.txt`. Overridable by user later (§12). |
| 2 | Duration column | Words ÷ 150 wpm = seconds per beat, exported in the table. |
| 3 | Preflight lint | Checks: all referenced assets have final files, one-offs generated, RW fetched, MT mapped. Advisory by default, strict mode optional. |
| 4 | Versioning | Ripple changes trigger `v2` export with a change-summary diff vs `v1`. |
| 5 | Shipped title | Marked here from P05's A/B alternates; feeds P23. |
| 6 | In-app preview | Alignment table renders as a scrollable storyboard (text + pose thumbnails) before export. |

---

## ✅ P22 — Real-World Asset Download Desk (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Engine v1 | Keyless Download Desk: per-record "Search in browser" (pre-filled query), manual download, drop/import with filename matching, status pending → fetched. No APIs, no scraping. |
| 2 | Role tags | Every fetched file: `final_insert` (used as-is) OR `generation_reference` (fed to external image generator to redraw in style). Maps default to reference; logos/people/memes default to insert; switchable per asset. |
| 3 | Era-accuracy | Lives in the chosen reference (e.g., 1709 borders map), not in query engineering. |
| 4 | Provenance field | Assets carry `source: fetched_final | generated_in_style` (layer tag stays separate: placement vs provenance). |
| 5 | Parked | API engine (Google CSE/SerpAPI/Bing), transparent-PNG priority, batch fetch, SafeSearch — bolt-on later. |
| 6 | Feeds | RW finals/refs → handoff inserts or external generation; MT refs → P24 map recipes. |

---

## ✅ P23 — Channel Intelligence / Performance Feedback Loop (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Metrics Entry | v1 manual (form or CSV paste): title shipped, description, tags, views, impressions, AVD/retention curve, drop-off timestamps. |
| 2 | Thumbnail | Manual upload slot per project for record-keeping. AI vision analysis of thumbnails parked for future. |
| 3 | Retention Mapping | Drop-off timestamp × 150 wpm = exact word/beat. AI analyzes the beat/prompts to hypothesize *why* viewers left. |
| 4 | Pattern Mining | Cross-video analysis of hooks, pacing, topics vs CTR/AVD. |
| 5 | Lessons File | Structured records (observation + evidence + proposed tweak + target recipe + confidence + status). |
| 6 | Approval Gate | AI proposes recipe tweaks with a diff view. Human approves to make `active`. Nothing auto-applies. Revertible. |
| 7 | Context Injection | Active lessons inject into relevant context packs (P04/P05/P06/P20). Transparency panel shows which lessons shaped a generation. |
| 8 | UI | Channel Intelligence view: metrics rows, retention sparklines with drop-off flags pinned to exact beats, lessons list, approval diff viewer. |

---

## ✅ P24 — Special Shot Types & Inserts (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Trigger engine | After P19/P20, scans beats for MT / in-style-meme records; assigns a shot-type template per detection. |
| 2 | Map redraw pipeline | P22's downloaded reference image attached as STRICT structural guide + style-kit + template instruction (flag-fill / region-highlight / paper / split). External generator redraws era-accurate geometry in MS Paint style. |
| 3 | Meme parodies | Chain: character sheet + meme pose description + style kit. Prompt requests green-screen isolation (auto-crop friendly). |
| 4 | Tags | layer: insert (overlays the world) · provenance: generated_in_style. |
| 5 | Shot Type Registry | Admin UI: built-in v1 types (4 map templates + meme parody); custom types later = trigger condition + prompt recipe. Visual cheat-sheet in-app for teammates. |
| 6 | Draft-first | Same §4.8/P17 flow as all assets (external draft → import → approve). P17 checklist gains ONE map-specific tick: geometry matches reference. |
| 7 | Output | Prompt cards for special inserts; generated externally; reviewed at P17; cited by beats via MT/instance refs. |

---

## ✅ P25 — Text-Only Beats & Overlay Spec (LOCKED)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Overlay tokens | Live in the channel kit: font, color, stroke, default placement, punctuation/emoji policy. Channel identity, written once. |
| 2 | Overlay text | AI proposes a shortened readable fragment of the beat line; fully editable. |
| 3 | Spec card | Per text-only beat: text + style tokens + placement + duration (beat words ÷ 150) + readability lint (advisory). |
| 4 | Preview | In-app render of the overlay in actual kit font/color on a dark swatch. |
| 5 | Export | Fills P21's text_only_beats.md + alignment-table column. |

### Tracker update — ALL 25 PHASES ✅ LOCKED (+ P23/P24/P25 scope additions)

---
## 🗺️ Phase Tracker

| Phase | Name | Status |
|-------|------|--------|
| P01 | Architecture & Tech Stack | ✅ LOCKED |
| P02 | Project & Data Model | ✅ LOCKED |
| P03 | LLM Orchestration Core | ✅ LOCKED |
| P04 | Ideation Intake | ✅ LOCKED |
| P05 | Title Generation | ✅ LOCKED |
| P06 | Script Generation | ✅ LOCKED |
| P07 | Script Import / Edit / Lock | ✅ LOCKED |
| P08 | Global Style Kit | ✅ LOCKED |
| P09 | Character Extraction | ✅ LOCKED |
| P10 | Character Variants | ✅ LOCKED |
| P11 | Environment Extraction | ✅ LOCKED |
| P12 | Real-World Entity Detection (revised §4.9) | ✅ LOCKED |
| P13 | Character Action/Pose Inference | ✅ LOCKED |
| P14 | Character Sheet Prompt Assembly | ✅ LOCKED |
| P15 | Environment Sheet Prompt Assembly | ✅ LOCKED |
| P16 | Prompt Export Package | ✅ LOCKED |
| P17 | Asset Import & Quality Checkpoint | ✅ LOCKED |
| P18 | Cross-Episode Asset Library | ✅ LOCKED |
| P19 | Chunk & Beat Splitting | ✅ LOCKED |
| P20 | Per-Beat Prompts | ✅ LOCKED |
| P21 | Beat Export & Editor Handoff | ✅ LOCKED |
| P22 | Real-World Asset Fetcher (web) | ✅ LOCKED |
| P23 | Channel Intelligence (Performance Feedback Loop) | ✅ LOCKED |
| P24 | Special Shot Types & Inserts (Maps, Parodies, Custom Triggers) | ✅ LOCKED |
| P25 | Text-Only Beats & Overlay Spec | ✅ LOCKED |