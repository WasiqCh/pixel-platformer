# SPRINT 7 — DONE ✅ (The Prompt Engine)

> The pipeline crossed from "knowing what is in a scene" to "knowing exactly how to draw it".
> Every beat element now has a production-ready Nano Banana prompt.

## Completed tasks
- [x] 7.1 Composer Backend — Deterministic (zero AI calls) two-class prompt engine.
      Dynamic elements (actors) get unique per-beat poses based on SVO.
      Static elements (environments/inserts) get one master prompt to draw once and reuse.
- [x] 7.2 Beat Board UI — Prompts visible inside the 📦 shot-kit panel. Added 📋 copy,
      🔒 lock, D/S class toggles, and ✏️ note editor for diegetic/director overrides.
- [x] 7.3 Overlay Taxonomy — Stickers automatically sorted into 7 types (year_chip, place_label,
      emphasis, list_ticker, payoff_line, faction_tag, route_arrow). Timed graphics_layer
      added to the episode package for the video editor.
- [x] 7.4 Pacing Flags — Added ⚡ FLASH (<3.5s) and 🐢 HOLD (>11s) warning chips on the
      Beat Board. Added pacing outlier check to the Checkpoint gate (recommended, not blocking).
- [x] 7.5 Polish Bundle — Mojibake (â€¢) cleaned at extract time (doormat) and retro-cleaned
      on compose (mop). Fixed double-periods in 3x3 sheet prompts. Added 🔄 CROSSFADE badge
      for beats with multiple backgrounds.
- [x] 7.6 Doc + commit.

## Proof points (Spice episode)
- 94 beat elements collapsed into ~45 actual image generations (22 masters + 23 poses).
- Overlays perfectly typed (e.g., "1498" = year_chip, "Pepper = Currency" = emphasis).
- Zero mojibake in the database; clean prose prompts ready for Nano Banana.

## Architecture lessons
- Two-class prompting (Dynamic vs Static) is the secret to visual consistency and saving tokens/money.
- Overlays are editor graphics, not AI images (AI text = typos). Diegetic text goes in the prompt.
- Pacing guardrails should be soft flags, not hard blocks, to respect the creator's rhythm.

## Next up: Sprint 8 — The Editor (when ready)
- Beat merge/split UI to fix the ⚡ and 🐢 pacing outliers.
- Timeline view for the scenes.json manifest.
