# SPRINT 8 — DONE ✅ (The Editor)

> The storyboard became editable: glue, scissors, warnings, and a rhythm map.
> And prompts can never go stale again — every beat mutation auto-recomposes.

## Completed tasks
- [x] 8.1 Surgery backend — POST /beats/{id}/merge_next and /split: sentence-aware split,
      same-section merge guard, element absorb/dedupe, sort_order renumber.
      Compose chain wired into extract + merge + split: prompt_text, overlay_spec and
      mojibake cleanup now happen on EVERY beat mutation, automatically.
- [x] 8.2 Surgery UI — ⤵️ merge and ✂️ split buttons on every beat card; last beat of a
      section greyed out; single-sentence splits politely refused; alerts report recompose counts.
- [x] 8.3 Timeline strip — proportional colored ribbon (width = duration, color = section),
      ⚡/🐢 markers,  sticker dots, hover tooltips, click-to-jump + auto-open shot kit, legend.
- [x] 8.4 Doc + commit.

## Proof points (spice episode)
- Merge B15+B16: 2.8s flash → 6.8s healthy panel; C04 element absorbed; 63 → 62 beats.
- Split guard: B04 (single sentence) refused with a friendly message.
- Split+merge round-trip on B23 preserved text, elements and flags.
- Timeline: 6 color zones; B04/B23/B38 fat with 🐢; B15/B29/B45 slivers with ⚡;
  clicking the B23 block scrolls to it and opens its shot kit.
- After every surgery: 45 generations recomposed automatically (22 masters + 23 poses).

## Lessons learned
- Chaining compose into every mutation kills the whole "stale prompts" bug class forever.
- Surgery guards (same-section merge, multi-sentence split) make destructive ops safe.
- A proportional ribbon communicates pacing better than any table of numbers.

## Parked (unchanged)
Generation Desk (in-app Nano Banana) · Editor Export (XML/EDL) · auto-download safety ·
channel-level library · TTS timing · meme mode.
