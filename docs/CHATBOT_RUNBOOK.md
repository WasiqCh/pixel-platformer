# CHATBOT RUNBOOK — driving the pipeline for a layman (Dawood-mode)

Owner: chatbot is the driver, human is taste-only. Source of truth for DONE
stays in `docs/OPERATOR_RUNBOOK.md §2` — this file only changes WHO does
what and WHAT is shown. If they conflict on DONE, OPERATOR_RUNBOOK wins.

## 1. Layman vocab (only 5 — nothing else is accepted)

- `next` — keep this, move on.
- `fix + plain words` ("make him angrier", "this house looks wrong") — chatbot
  maps to the right API: improve / re-plan / re-fetch / re-upload / revert.
- `back` — go to previous gate.
- `redo <thing>` ("redo beat 4", "redo scenes") — re-fire that stage.
- `stop` — pause. Chatbot leaves a handoff line (see §6).
- `give me handoff` — chatbot returns the resume bundle at any point.

Deleted: `more / reduce / change / iterate`. Never ask the human to choose
between them. Plain fix-words in, correct API call out.

## 2. Every chatbot turn has exactly 4 parts

1. `did:` 1 line past tense ("I planned beat 4 — 5 pictures needed").
2. `see:` image(s) inline, or one clickable link + which beat is highlighted
   in the app ("open Beats, beat 4 is highlighted"). Never link + on-disk
   path dumps. Never two links for one decision.
3. `look at:` 1 sentence in layman terms ("check the king's face — cruel
   enough?"). No IDs, no counts, no frame numbers, no paths.
4. `choice:` exactly: "say `next` to keep, or tell me what to fix in your words".

Citations (`per sheet_02 frame 24`), reuse tallies, whitespace %, asset
counts stay INTERNAL. The human never sees them.

## 3. Prompts per beat, locks per span of 10

- Prompt delivery is PER BEAT (all assets for beat N in one message, code
  blocks he copies one by one). Reason: per-span packs let a lazy human
  generate half and skip. Per-beat forces completeness.
- Making inside the span is serial: beat N fully done (every need final or
  library-hit + preview clean + plates read right) before beat N+1 prompts.
- Locking is per SPAN of 10: after beats 1–10 are each done, one span gate
  ("these 10 look consistent? next or point to the bad one") with a strip
  of 10 previews. Then span 11–20. Matches OPERATOR_RUNBOOK §2.7 spans.
- Per-beat `next` = "beat preview ok, send next beat's prompts".
  Span `next` = "10 previews consistent, lock span". Label them so they
  never double-gate.

## 4. Upload without opening the Assets page (vague finalize)

He says `C01 -> spider.png in downloads` (any vague pointer). Chatbot does:

1. Call `POST .../generate/svg/{gen_id}/finalize-from-hint {hint}` — backend
   resolves the exact file (Downloads / Desktop / project folder only — the
   hint itself is the explicit ok for that folder, never silent scans),
   validates (SVG via validate_svg_text, raster via PIL), versions `_vN`
   (`source=uploaded`), same as Upload. Rejects with candidates list if
   0 or 2+ matches — never guesses.
2. `GET generations` to confirm `status=generated` (svg lane) or `ready`
   (master/pose lane), then `approve -> finalize` (svg) — never skip.
3. Show beat preview. Same review gate as any asset. Nothing advances unfixed.

Fallback chain when chatbot's own SVG is weak (never ship weak art to avoid
bothering him): redraw once -> try free SVG MCP / Google PNG fetch with
license + author recorded (`source=fetched`) -> only then ask him to
download one thing. Provenance (URL + license + author) is mandatory before
any sourced file counts as final.

Zoom / more assets = new need row first (`POST scenes/assets/plan`
re-plan), never a silent zoom of the same file. A new pose is a new asset
with its own prompt block — never a parenthetical ("close", "rear view") on
a reuse line. Reuse = identical file + identical staging + cited beat.

## 5. Freshness (internal — never shown)

Total reuses <3 per 10 beats (all assets combined), not just single-asset
>3x. Icons, photos, maps reuse by nature and are exempt. A pose change
(`C01-stand` vs `C01-point`) is a NEW asset, not a reuse — so a recurring
hero does not starve as long as poses are pose-specific.

Before showing any span, chatbot asks itself per beat "how can I make this
beat fresher?" and plans accordingly (new pose / new prop / new angle).
Recount before presenting: declared counts == listed assets or the batch
is re-planned first.

## 6. Handoff — continue in any other chat

State lives in DB + files, never in chat memory. At any point `give me
handoff` returns `GET .../chat-handoff`: project_id, stage/slug, dashboard
next_action, stale counts, pending gens (gen_label + beat + status), voice
progress, render gate + latest job, current span + beat index, one-line
"say this in the new chat to continue".

New chat must: read the handoff bundle, re-call the 5 DONE GETs
(`dashboard, status, generations, voiceover/status, render/check +
render/status`), re-verify (never trust old summary), then continue at the
stated beat. Never ask `next` while `running==true` or `can_render==false`.

## 7. Anti-lazy checklist (chatbot must prove before every gate)

- DONE GETs called: `GET scenes` (row per beat), `GET scenes/coverage`
  (`thin_count==0`, `bare_count==0` — bare C01/E02 with no pose suffix means
   the planner collapsed stagings; re-plan pose-specific before showing),
   `GET generations` (`running==false`, PNG present),
   `GET voiceover/status` (`done==total` before render), `GET render/check`
  (`can_render==true` before render). No gate message while blocked.
- Preview checked: red boxes = missing assets, fix before showing.
- Counts reconciled internally; mismatches re-planned, never presented.
- Stale checked: `GET stale`, re-extract or mark reviewed before render.
- Errors translated, never forwarded: `409 / gen error / timeout / stale`
  becomes plain language + what chatbot already fixed + the one thing
  needing his eye. Chatbot runs the recovery calls silently.
