# OPERATOR RUNBOOK — driving the Pixel Platformer pipeline (human or agent)

Owner-approved 2026-09-27. You are driving a RUNNING app: backend `:8100`,
frontend `:3000`. Every call below is `http://127.0.0.1:8100/api/v1/...`.
All writes are project-scoped — always use the right `{project_id}`.

Playbook defaults (locked unless you say otherwise): the operator is the
brain — no app LLM/model calls, the app is tracker + renderer only. Voice
is Kokoro (local, no keys). Image provider stays `manual`: nothing
generates unless explicitly triggered.

## 0. Setup (once per machine)

1. Pull, `start.bat` (backend 8100 + frontend 3000).
2. Open the app → Setup node (🛠️, first in sidebar, auto-opens if red).
   Fix every red item with its Fix button. All green to proceed.
3. Settings → voice provider: **Kokoro** (free) or Gemini (needs key).
   Settings → LLM endpoint/models for planning calls.

## 1. New project

Home → new channel (pick a style preset or write the descriptor) → new project
(pick canvas background or keep channel chroma) → paste/lock script.
Record the `project_id` (e.g. `CH04_EP01`) — every call below needs it.
Naming: ASK the user for the project display name at creation (pass as
`slug`) — never invent one silently. The `project_id` + folder are
immutable plumbing; the display name can be renamed anytime on your word
(`PUT /projects/{id} {slug}`), folders never move (P-01).
Ask who generates, per beat: `me / you / sourced / video` (see §2.5).
Default: props + icons = me; characters + places = your call; real
faces = sourced-first.

## 1.5. Step 0 — Reference wall (style DNA, once per channel)

Before the pipeline runs, the driver studies how the reference channel does
it. Source of truth lives at `pixel-platformer/references/` (repo-relative —
never hardcode a machine path): 6 sheets × 18 frames (3×6 grid), one frame
per 5 seconds from the middle 3 minutes of 3 Brofessor Stein videos
(hitmen/kings/doctors). Rebuild with `yt-dlp` (middle-3-min sections) +
`ffmpeg` (`fps=1/5`) — see `references/work/` for the clips. Local-only
stills, never commit them.

How Brofessor Stein does it (see ref — every item below cites frames):
- Canvas is a solid light-blue void, full-bleed, ~90% of the time; a dark
  olive wall only for night/indoor (see ref `sheet_04_kings` frames 31–32).
- People are dead-simple flat figures with THIN black outlines (~2–3px at
  1080p), dot/line faces, period-costume shorthand (fedora = mobster,
  crown = king) — see ref `sheet_01_hitmen`.
- Real photos sit beside cartoons: mugshots, portraits, paintings, building
  photos pasted raw (see ref `sheet_02_hitmen` frames 26–27, `sheet_03_kings`
  frames 05–06). That is what our RW/world-photo inserts are for — never
  redraw a face the record can show.
- Maps name places: MT slots take REAL map images — sourced (URL + license +
  author in the tracker) or generated from a prompt by you/me. Never AI-faked
  geography. File-less MT rows render the honest "MAP COMING" box as fallback.
  (Owner unlock 2026-09-29: old never-any-map rule retired.)
- Red curved arrow = cause, black arrow = sequence, red X = no, green
  check = yes (see ref `sheet_06_doctors` frames 20–24).
- Text grammar: name + nickname plate top-center, date/place under it
  (see ref any sheet) — that is exactly our overlay name/date/place roles,
  ≤1 plate + 1 badge per scene. Quotes go in speech bubbles; counts go big
  ("12", "30 years").
- A small corner avatar tracks the current subject every beat (see ref —
  top-right of every frame) — that is our badge slot.
- Gore is pixelated or XXX-censored, never drawn (see ref `sheet_01_hitmen`
  frame 02). Our symbolic rule (marks, parcels, frost — never depiction)
  is the same instinct.
- One idea per frame; characters slide in and out. Sparse beats
  sparse scenes.

Rule: every scene shot, asset prompt, and overlay must cite its frame
("per `sheet_02_hitmen` frame 24") or state why it deviates. DONE when 6
sheets sit in `references/` and the driver has viewed them.

### Step 0 conformance checklist (anti-drift — enforced at every later step)

If any item below fails, the step is NOT done — fix it before advancing.
This is what "follow the reference wall" means in practice (see ref):

- [ ] Thin lines: every asset uses THIN uniform black outlines (~2–3px at
  1080p). Thick outlines (≥5px) are rejected at review, no exceptions.
- [ ] Void-first: scenes stage on the solid light-blue canvas. Measured
  whitespace on the wall is ~65% — voids are correct, packing is the
  defect. Full rooms only for demanded interiors/night (dark olive
  wall). One E-ID may resolve to void + prop fragments — a place is
  not a wallpaper.
- [ ] Photos over redraws: every real-person beat cites its RW photo insert
  once a Download Desk file exists — never redraw a face the record shows.
- [ ] Maps for places: every place-name beat cites its MT map (file) or
  honesty box while file-less.
- [ ] Plates every beat: name (+nickname) + date/place overlays; quotes in
  speech bubbles; counts drawn big.
- [ ] Badge every beat: corner subject avatar top-right, implemented as
  a photo/prop need pinned top-right via explicit x/y/scale. Every beat
  names its avatar; no beat ships without one.
- [ ] Shared icons: drawn ONCE as library masters and reused — never
  redrawn per beat. Full set + triggers live in the vocabulary below.
- [ ] Gore: pixelated, XXX, or symbolic — never depicted.
- [ ] Bundles, not counts: one trigger word per visual change; as many
  elements as the word needs (measured: up to 8 landing on a single
  name-word), never a cap, never one-by-one. Small counts are the common
  case, not a rule.
- [ ] Whitespace is correct: target ~60–70% void per scene (measured mean
  65% on the wall). Compose mass in the upper two-thirds, symmetric and
  center-weighted, ground strip or float — never full-bleed packing to
  "fill" the frame. Feet float free or on a strip, never ON another
  object. Explicit x/y/scale per element (box + contain-fit); seeded
  scatter is a fallback, never the plan.
- [ ] Citation: frame cited per decision, or deviation stated.

### Vocabulary + triggers (final — full 108-frame inventory, no caps)

Everything below was observed on the wall, nothing assumed. Each type
carries its trigger — the words that summon it:
- Name plate + nickname, top-center, EVERY frame. Date/era under it only
  when the script gives one. Corner avatar (current-subject head),
  top-right, EVERY frame — a pinned need, never decoration.
- Speech bubbles: direct quotes only, anchored to the speaker's mouth.
- Label arrows: small text + thin arrow naming a figure or place
  IN-frame ("Klansman", "Santa Rosa, California") — distinct from plates.
- Pictogram bubbles: statistics as drawings (count + stick figures),
  "..." for silence.
- Stat callouts: big number + small unit ("<100 pounds / 45 kg" with
  scale icon, "30 years", giant counts arrowed to bodies).
- Photos (mugshot/portrait/group/painting/building/aerial): first intro
  of a real person + key evidence moments, plain rectangles, no borders,
  roughly every third beat. Never redraw a face the record shows.
- Maps: country + red region + red arrow + label above; small inset for
  foreign ground. Every place name, every move between places.
- Flags: identity shorthand beside figures (never explained, always
  recognized).
- Icons and their triggers — death: skull, crossed/flaming swords,
  tombstone, coffin (killing/death words); negation: red X (never/no/
  rejected words); confirm: green check; time: calendar, clock, lungs;
  authority: crown, medal/ribbon, badge-man, gavel bench; evidence:
  reports doc, poison bottle, syringe, scale, briefcase, press kit;
  warning: skull-triangle, virus; censor: pixelation or XXX on gore
  nouns. Drawn once as library masters, reused forever.
- Tableaus for plurals: rows and lineups (gunmen row, shootout, press
  pack, trial table, meal, digging pair, suit lineup) — never one figure
  standing for a crowd.
- Vehicles on travel verbs (van/car + trunk + boxes accumulate frame to
  frame); isometric buildings on institution nouns (prison, camp);
  furniture on sit/eat/sleep/try verbs (bed, table, bench, throne).
- Transitions: FULL CLEAR on subject change (whole bundle lands on the
  name-word at once); ACCUMULATE within a subject (van gains rifle,
  then body); giant-face zoom as the wipe device between eras.
- Gore: pixelated, XXX, blood as flat pools/drips only — never wound
  detail, never depiction.

## 2. Pipeline order (each step's DONE criteria)

| # | Do | DONE when |
|---|---|---|
| 0 | Reference wall (§1.5, once per channel) | 6 sheets in `references/`, driver viewed, later steps cite frames |
|---|---|---|
| 1 | Beat Board → Break beats | beats listed, 6–14 words each, none span two sentences |
| 1.5 | Extract cast + locations + world (Cast/Locations/World Desk) | registry exists: every place a scene will cite is an approved E-ID (scenes cannot cite what was never extracted) |
| 2 | Narrate & Retime | every beat has a WAV + measured duration |
| 3 | ① Plan scenes | every beat has a scene row with shot + reasoning |
| 4 | ② Plan assets (in 10-beat batches, see §2.5) | every need is library-hit OR pending gen (counts balance) |
| 4.5 | Prompt files (user-mode assets) | every `you`-mode asset has a prompt `.md` (see §2.5) |
| 5 | ③ Generate SVGs (loop) | every gen `generated` (then Approve → raster PNG → Finalize) |
| 6 | Approve scenes (1-click or batch) | scenes all approved |
| 7 | Check overlays (auto-proposed per scene) | plates read right, ≤1 plate + 1 badge |
| 8 | Checkpoint green → Render | MP4 in My Video, plays + downloads |

Key endpoints (all `POST` unless noted):
- `GET /projects/{id}/scenes/coverage` — thin beats (re-plan those first)
- `POST /projects/{id}/scenes/plan`, `POST .../scenes/assets/plan`
- `POST /projects/{id}/generate/svg/{gen}` (per row), `.../bulk {only,limit}`
- `POST .../generate/svg/{gen}/approve`, `.../finalize`, `.../improve {note}`,
  `.../revert {version}`, `.../paste {code}`
- `PUT /projects/{id}/scenes/{beat} {status:'approved'}`
- `POST /projects/{id}/voiceover/build`, `GET .../voiceover/status`
- `GET /projects/{id}/render/check` (gate: 409-shaped JSON when blocked),
  `POST /projects/{id}/render`, `GET .../render/status`,
  `POST .../render/cancel`
- `GET /projects/{id}/render/finals`, `GET .../render/file/{name}` (download)

## 2.5. Asset flows — who makes what, and how it lands in the tracker

Modes (ask per beat, write the choice into the need reasoning):
- `me` (props + icons default): brain hand-draws SVG → paste → raster →
  review → finalize. Thin lines, void-first, checklist §1.5 applies.
- `you` (characters + places on your call): brain writes a prompt file →
  you generate JPG/PNG in any external tool, any format → you drop the
  file or say vaguely where → brain finalizes via upload (versioned,
  `source=uploaded`), same review gate. Nothing advances unfixed.
- `sourced` (real faces default): brain downloads first (Download Desk /
  Commons search with license filter, or any-URL fetch with license +
  author recorded; non-Commons licenses are flagged for review before
  publish). If nothing good found, brain gives you 2–3 exact search
  strings, you return a link, brain fetches it.
- `video` (only on explicit order): NOT YET SUPPORTED — render is
  stills-only (preview PNG held `duration×30` frames + WAV, concat).
  Spec when built: `yt_url + start_sec + secs_needed + extra_safe_secs`
  → yt-dlp section → compositor video layer → render splice, with source
  URL + timestamp logged. Until then: supply stills from the clip as
  `you` mode.

Prompt files (the solid piece): one per `you`-mode asset at
`07_beats/prompts/{gen_label}.md` (next to the pack export), written by
the brain, never by an app model. Poses get their own files
(`YOU-{ref}-{pose}.md`, e.g. `YOU-C01-stand.md`) — one file per
generatable unit, boilerplate copied whole into each, never split:
- Subject block: repeat the asset name every line, zero pronouns.
- Style-DNA block: thin 2–3px outlines, void-first, bundles sized by
  trigger (no count caps), flat fills, no gradients/shading (copied from
  the channel kit, not invented).
- Composition: the scene shot + placement + which plates sit on it.
- Negatives: photorealism, gradients, text/logos in art, gore depicted.
- Params: aspect + size + which reference frames to attach.

Vague finalize: you say "placed in downloads/foo" (or any vague pointer)
→ brain resolves the exact file, uploads it to the gen, shows the
preview, same review gate. Folders outside the repo need your explicit
okay first — brain never scans the machine silently.

Sourced images: provenance is mandatory — every sourced file lands with
source URL + license + author in the tracker before it counts as final.

Poses + variations: `characters.actions` holds 2–6 poses per character;
each pose is a separate library asset (stand / point / sit / lie …).
`variants` covers look-changes across story spans, `env_variations`
covers place states, per-element x/y/scale covers placement. Plan poses
as needs in step 4; draw once, reuse everywhere. No code involved.

Beat loop (the gate): beats run ONE at a time — plan beat N →
make/fetch every asset → approve each → preview beat N → overlay check
→ your explicit OK → N+1. Never batch silently in play mode. Beat DONE =
every need final or library-hit + preview clean (no red boxes) + plates
read right (≤1 plate + 1 badge) + your ok. Every review message carries the
exact preview link (`http://127.0.0.1:8100/api/v1/projects/{id}/scenes/{beat}/preview`)
AND the on-disk path (`data/projects/{folder}/07_beats/previews/{file}.png`) —
never a review without both. The backend already supports
every per-beat call; the loop is discipline, not code. Assignment runs
in 10-beat batches; making runs serially inside the released batch —
one beat fully done before the next.

Asset batches of 10: step 4 assigns assets for beats 1–10 first, then
11–20, and so on. After each batch of 10 the driver shows the assignment
and waits — the review lists EVERY beat with its assets named: each
asset with kind + source (library-hit with LIB id, pending gen, photo
with file, map box, icon reuse). No beat hides its asset list.
Your orders are `more` (add assets), `reduce` (cut assets),
`change` (swap something), or `next` (lock the batch, move to the next
10). `iterate` reworks inside the current batch; `next` advances. No
batch is generated until you say so.

Voice: Kokoro default for our channel (local model, per-beat WAV +
measured duration, no keys). Gemini fallback only on explicit order.

## 2.6. Word timing + timed layers (Stein choreography)

Static one-still-per-beat cannot copy Stein: his visuals change on
specific words (bundles land on name-words, evidence on fact-words,
~every 4–8s — measured on `references/` with 1fps diffs + word-timed
subs). Beats keep their text; visuals get timestamps *inside* each beat.

Word timing — two workflows, one output shape (per-beat word list with
start/end):
- A (you upload full-script audio): merge chunks → normalize −14dBFS →
  word timestamps → force-align onto the pristine script → slice by beat.
- B (Kokoro per-beat WAVs): transcribe each WAV → align to its beat
  text directly (known text = easy, accurate).
- Engine: SYSTEM `whisper` CLI (`backend/core/wordtime.py` shells out —
  WHISPER_BIN env → PATH; openai-whisper + torch live outside the venv,
  never installed into it — see requirements.txt comment + Setup check).
  Alignment is a headless port of `audio_prep_engine 2.0.py`
  `force_align_script` (word stamps + difflib onto script words,
  spread-on-mismatch). No GUI, no merge step (beats ARE the chunks).
- Endpoints: `POST .../wordtime/align {beat_id?|all, model}` (transcribes
  `08_export/voiceover/{beat}.wav`, REPLACES `beat_words` rows),
  `GET .../wordtime/{beat}` (word list). No LLM calls on this router.
- Stein reference timings stay `yt-dlp --write-auto-subs` (YouTube only —
  never for our own audio).

Staging file per beat: `07_beats/staging/{beat}.json`, shape
`{version:1, beat_id, steps:[{t, hide:[need IDs], hide_ov:[overlay IDs],
note}]}` (t ascends from 0, each step lists the FULL hide sets;
validated by `backend/core/staging.py`, missing file = plain stills).
Derived from the timing + the §1.5 grammar (bundle on names, evidence
on facts, map→arrow→label stagger); cited like everything else.
Accuracy gate: below ~75% exact word hits, the beat is flagged and
re-aligned with a bigger model before any staging is written from it —
triggers on guessed times land bundles on wrong words, silently.

Variant previews: `GET .../scenes/{beat}/preview?hide=1,2,3&hide_ov=4,5`
drops those need / overlay IDs from the render (separate scene-hash
cache per hide set) — plates CAN be timed: present in early variants,
hidden in later ones or vice versa. Render reads the staging file per
beat and holds each variant PNG for its word-boundary span — same
concat, no ffmpeg filter changes. Beats without staging files render
exactly as before. Video-clip inserts stay DEFERRED (needs yt-dlp +
video layer + splice — separate build, only on explicit order).

## 2.7. Phases + operator contract

Big scripts plan in spans of ~8–10 beats: registry → scenes → assets →
review per span, lock it, next span. Fresh context, small reviews, no
drift. A span is DONE only at locked batch + approved previews.

Operator contract: every word, asset, and beat is the driver's
responsibility. Own bad asset → iterate unprompted, no waiting to be
told. Bad sourced image → re-download until perfect (10× if needed),
never file a wrong face. User asset below the bar → reject it outright
and state the standard it must meet. No silent passes, ever.

## 3. State checks (read-only, use freely)

- `GET .../scenes` → per-beat status/stale. `GET .../scenes/assets` → needs.
- `GET .../generations` → gen queue with statuses.
- `GET .../render/status` → persisted job progress (survives reload).
- Previews: `GET .../scenes/{beat}/preview` (red boxes = named missing assets).

## 4. Errors + recovery

| Symptom | Meaning | Recovery |
|---|---|---|
| 409 on render | gate lists unapproved scenes / missing audio | approve scenes, build voiceover, retry |
| gen `error` with message | that asset failed (LLM/model) | improve-with-note, regen, or paste code |
| calls crawl/timeout | model too heavy or gateway down | smaller model, or wait + resume (never rewinds) |
| cancelled render | cooperative stop | POST render resumes same job at N |
| stale flags after script edit | downstream needs re-review | re-plan flagged items, or mark reviewed |
| figures look squashed/flat in PNGs | raster export forced 16:9 (patched: aspect-fit) | delete bad raster, re-approve + re-finalize affected gens, refresh library copies |

## 5. Rules (locked)

- Manual always wins: user paste/approve overrides anything.
- Never overwrite: versions only, revert anytime.
- Approved rows are skipped by re-runs (re-plan replaces drafts, keeps approvals).
- Dawood's machine is independent: fresh `data/`, his own settings, same runbook.
- Image provider stays `manual`: no background generation, ever.
- Provenance before pixels: no sourced file counts as final without source
  URL + license + author in the tracker.

## 6. Redo any single step (owner workflow)

Any stage re-fires on demand — say "re-extract characters", "re-plan scenes",
"redraw asset X". Re-runs replace drafts, keep approvals, never duplicate
(bulk loops are idempotent; renders mint new versions). Render resumes at N,
never from 1. Nothing upstream is disturbed by redoing a downstream step.

## 7. Iterate any asset until liked (owner workflow)

View the asset's PNG (Assets page / preview) → say what's wrong in words
("thicker outlines", "angrier eyes") → new version arrives, old kept, revert
anytime. You may also PROVIDE reference pictures with your note ("draw the
eyes like this") — the note + your pictures travel to the model together.
Repeat until liked, then approve. (Playbook mode: no app model runs —
your pictures ride inside the prompt file you paste into your own
generator.)

## 8. Play mode — step by step with a human gate (owner workflow)

Say "play runbook" with a script and the run goes ONE step at a time from §2:
the driver (human or model) finishes a step, shows its result, and WAITS.
Only your explicit "next" starts the following step. Nothing advances on its
own, nothing batches silently. "Redo step 3" / "skip to render" are always
valid orders — the gate in §2 decides what's actually ready. Asset beats
run on the §2.5 beat loop by default: one beat fully done before the next.
