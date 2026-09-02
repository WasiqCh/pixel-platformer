# SPRINT 2.5 — DONE ✅ (Funnel Polish & Manual Override)

> Every AI surface now has a human override. Nothing is ever lost. 
> The funnel is production-ready.

## Completed tasks
- [x] 2.5.1 Idea control — Refine & Expand, 🤖 AI refine (creates v2), 🔒 Lock (is_current=1), ✏️ inline manual edit.
- [x] 2.5.2 Title control — 10-title accumulation preserved, 📥 Own-title door, ✏️ inline edit, 🎲 "3 variants of this one", ✂️ AI shorten (>70 chars), exclusive race-free lock.
- [x] 2.5.3 Outline persistence — Saved to DB + file mirror (`outline_v1.md`), manual edit (add/reorder/remove sections), 🤖 AI refine (creates v2), Σ budget tracker.
- [x] 2.5.4 Pass 3 punch-up — Select "##" section -> free-text note -> AI rewrite -> side-by-side diff preview -> Apply (unlocks) / Discard.
- [x] 2.5.5 Pass 4 sanity check — 🩺 One-click audit (names, timeline, tone drift, repetition, hook strength) rendered as a color-coded card.
- [x] 2.5.6 Import door — Paste/drop .txt/.md -> instant word/duration math -> source='imported' -> gets every tool.
- [x] 2.5.7 Editor polish — VersionPill (revert/delete versions), Hook strip (first 75 words highlighted), Pacing strip (color-coded per section), Breakdown (actual/target per row), ⚖ Rebalance button.
- [x] 2.5.8 S02/S03 Extras — 📥 Shelf toggle (hide good-but-not-now ideas), Skip Doors (Fast Lane jump buttons).
- [x] 2.5.9 Draft-length recipe tightening — Forced AI to hit ±5% word targets via rich expansion instructions.
- [x] 2.5.10 Git sync + Commit.

## Architecture & UX Lessons Learned
- **Race conditions in single-selects:** "Lock" must unlock all others first (last-click-wins). Fixed in titles.
- **AI Copy-Paste Failure:** LLMs are terrible at "copy this text exactly" (Auto-Section). Removed in favor of manual `## Heading` typing. 
- **Fail-Loud vs Fail-Silent:** Added `safeJson` in frontend to catch raw 500 text errors and show them as readable alerts instead of silent crashes.
- **The Golden Rule:** Editing a locked state = unlocking a new version. Never mutate history.

## Next up: Sprint 3 — The Brain
- P09 Cast Board (Character extraction + mentions)
- P10 Variant Timelines (Costume/age changes)
- P11 Scout Board (Environment extraction)
- P12 World Desk (Real-world assets, maps, memes)
