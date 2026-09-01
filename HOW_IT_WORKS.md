# HOW IT WORKS — Plain-Language Guide to the App

> What this app is: a production office for animated YouTube videos.
> It plans, writes, tracks, and packages everything.
> It does NOT draw pictures and does NOT edit video — those happen in your
> existing tools. That separation is deliberate and permanent.

---

## The House Rules (how the app behaves, everywhere)

1. **The brain lives in the backend.** The screen only shows and asks; all logic
   is server-side. The UI can change without breaking anything.
2. **Manual always wins.** Every AI output can be edited, replaced, or skipped.
   You can bring your own title, script, or anything else at any time.
3. **Never overwrite — always version.** Locking or editing creates a new
   version. Old ones are kept. You can revert anytime.
4. **Smart ripple.** Change an old decision (e.g., one script line) and the app
   only *flags* affected downstream work with amber dots. One review screen
   lets you choose per item: keep / regenerate / later. Nothing is blocked,
   nothing is silently changed.
5. **Fail cheap.** Drafts before finals. Warnings before expensive stages.
   Cost estimates on idea cards. Checkpoints before beats.
6. **IDs are invisible.** The app names everything internally (C01, E02, B047…)
   and handles prefixes at export. You never manage IDs.
7. **The transparency panel.** For every AI answer you can open "what did the
   AI see and say" — summarized, scoped to the current beat, hidden from
   teammates by default.

---

## Step 0 — Channel Setup (once per channel)

- Upload 2–4 sample pictures of your fixed style (the "MS Paint anchors").
- The AI drafts a text description of the style from them; you approve/edit.
- Confirm defaults: chroma-green background (white if the subject itself is
  green), avoid-list (no clutter, no text, no blur, isolated subjects),
  resolutions (environments 1920×1080 · character sheets portrait 3:4).
- Optional: 2–3 tone sample paragraphs ("how we sound"), overlay text style
  (font/color for text-only beats), and a recurring host (built once, reused
  in every episode).
- Everything here applies to ALL episodes of the channel automatically.
- Changing it later creates a new kit version; in-flight projects get amber
  flags, never silent changes.

## Step 1 — Idea

- Type anything from one word to a paragraph. Or press "Surprise me" for
  fresh concepts that avoid repeating your past videos.
- The AI returns an **Idea Card**: refined concept, 2–3 hook angles, audience
  appeal, tags, a rough cast/locations cost estimate, and a warning if the
  topic will need real-world logos/people.
- Refine it with free instructions ("make it darker") until it feels right.
- Save ideas to the Shelf without starting a project; promote them later.
- Already have a title or script? Skip straight to those doors.

## Step 2 — Title

- One click → 10 candidates, each with a one-line "why this works", a style
  tag, and a length check (YouTube truncates long titles).
- Shortlist, edit, remix, regenerate only the ones you dislike.
- Or type your own. Lock one. Optional alternates kept for A/B testing.

## Step 3 — Script (the Script Studio)

- Slider sets word count; duration shows live (150 words per minute).
- Pass 1: outline (sections, hook placement, turns) — reorder freely or skip.
- Pass 2: full draft, streamed into the editor.
- Pass 3: select any section → "improve this" with a free note. Repeatable.
- Pass 4: one-click final check (name consistency, timeline gaps, tone drift,
  repetition, narration-friendly sentence lengths, hook strength).
- Or paste/upload your own script — it gets the same tools and instant
  duration math.
- The first ~75 words (your hook) stay highlighted. A footer always shows
  words + duration. A pacing strip shows section balance.
- **Lock** the script to unlock analysis. Editing later just starts a ripple.
- Locking also records what you changed vs the AI draft — the app learns
  your taste from it (used later with your stats).

## Step 4 — Meet the Cast, the Locations, the Real World

- **Cast Board:** every character with inferred appearance and where they
  appear. Core characters are permanent; minor ones you choose: full
  character / bundle into a generic crowd / drop. Each person is classified
  drawn (MS Paint actor) or fetched (real photo insert) — flip freely here,
  costs nothing at this point.
- **Variant timelines:** how each character visually changes over the story
  (child→adult, wounded, disguise). Rare versions are suggested as cheap
  one-off poses instead of full sheets.
- **Location Scout Board:** every environment with 3–4 elements and its
  variations (dawn / battle / aftermath). Green-heavy locations are
  auto-switched to white backgrounds.
- **World Desk:** brands, logos, real people, meme moments, and map triggers
  detected in the script. Each gets a 1–4 word search query and a usage
  intent (on-screen insert / prop / text-only). You approve or dismiss.
- Everything is editable; the AI's guesses always show their reasoning.

## Step 5 — Choreography & Prompt Cards

- Per character version: the poses and facial expressions the story needs.
  Sheets stay lean (under 6 poses, only what's necessary; extras suggested
  separately).
- The app then writes a **prompt card** per sheet: style text, identity,
  pose-by-pose lines (character named in every line, no pronouns), isolation
  and background rules, avoid-list, size/ratio, and the exact list of
  reference pictures to attach when generating.
- Environment cards add scale notes ("door ≈ 1.1× human height") and box
  maps for variations. Compositing notes for the editor are kept separate
  from the prompt so the image model never sees them.

## Step 6 — Generate Outside, Approve Inside

- **Export package:** a folder with all prompt cards, copies of reference
  images, editor notes, and a one-page checklist. Zip it, take it anywhere.
- Generate **drafts** (low-res, fast) in your image tool. Name files as the
  README says and drop them back in — the app matches them automatically.
- **Checkpoint Board:** each draft is checked on 4 points (style, background,
  proportions/attire, isolation) plus a geometry check for maps. Approve or
  reject with a reason. Only approved sheets can be used by beats.
- Then generate finals the same way.
- **Real-world assets:** click "search in browser", download with your own
  eyes, drop in. Logos/memes can be used as-is or as references to redraw in
  your style. Maps are always redrawn in style using the downloaded
  era-accurate map as a strict geometry guide.
- **Library:** generic characters, hosts, and extension sheets are saved with
  context tags and reused by future episodes automatically. A counter shows
  how many sheets the library saved you this episode.

## Step 7 — Beats (the Storyboard)

- The script splits into sentences (chunks), then into ~6–14 word beats at
  natural clause boundaries. Merge/split freely on the Beat Board.
- Per beat, the AI decides who/what is in frame, from which angle, and writes
  isolated prompts for anything missing (one-offs). Existing poses are reused
  first — no needless regeneration.
- Result: the **alignment table** — every beat line with its asset tags
  (actor vs insert), framing, duration, and text-only flag.
- One-off poses collect in a tray: accept / promote to library / discard.
- Text-only beats get styled overlay text (short, readable, timed).

## Step 8 — Handoff to the Editor

- One versioned zip: alignment table (txt + md), all final assets, one-off
  prompts, inserts, editor notes (standing planes, horizons, box maps,
  keying colors), text-only specs, manifest, README.
- In-app storyboard preview shows the episode as text + thumbnails before
  export. Re-exports after changes come with a change summary.

## Step 9 — After Publishing: the App Learns

- Paste the video's stats (views, impressions, retention, drop-off times)
  and upload the thumbnail for the record.
- The app maps each drop-off to the exact beat playing at that second and
  hypothesizes why viewers left.
- Across videos it finds patterns (hooks, pacing, titles vs performance).
- It proposes small recipe tweaks with a before/after diff. **Nothing applies
  without your approval.** Approved lessons quietly improve future ideas,
  titles, scripts, and beats. Revertible anytime.

---

## Tiny Glossary

- **Beat** — one visual moment (~6–14 words of narration).
- **Chunk** — a sentence; a container for beats.
- **Sprite sheet** — one image holding 2–6 poses of a character, boxed.
- **Variant** — a major visual version of a character (age/outfit/state).
- **Kit** — the channel's fixed style: references, descriptor, rules.
- **Checkpoint** — the approve/reject gate between drafts and beats.
- **Ripple** — the flag-and-review system for downstream effects of a change.
- **Actor layer** — drawn things living inside the MS Paint world.
- **Insert layer** — real-world things interrupting it (logos, photos, maps).
- **One-off** — an improvised pose for a single beat, chained to a sheet.
- **Lesson** — an approved, revertible rule learned from your stats.