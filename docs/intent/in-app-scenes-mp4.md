# Intent — In-app scenes + final MP4

Confirmed 2026-09-25 with Wasiq (explicit yes). Master-architect directive: extend
pixel-platformer in place; no clone, no rewrite (`00_NEW_PLAN (rough sketch).md`
is research notes only, NOT a build plan).

- Outcome: Pixel-platformer builds each beat's scene in-app and renders the final
  MP4. Per beat: AI plans scene + assets → reuses library art on a hit →
  AI-generates missing SVGs one by one (validated, retried on failure) → user
  approves/fixes, including "improve this + what's wrong" with previous SVG
  passed back. Narration audio sets each beat's duration.
- User: Wasiq, solo. AI assembles, he approves/fixes — every scene, every asset.
- Why now: Today the app ends at prompt cards and handoff; pictures and the final
  video happen outside, so quality leaks where he can't control it.
- Success: An upload-ready MP4 out of the app — every scene approved, every asset
  on-model, narration in sync.
- Constraint: His review time. Each approval must cost seconds, or 400 beats never
  ships.
- Out of scope: No hand-drawing tools (AI makes art, user only judges it); no
  editor handoff as the end goal (the MP4 is the final artifact, handoff stays
  only as a byproduct if cheap).

Key codebase facts grounding this (verified in code):
- `beats.duration_sec` is ALREADY narration-measured (`api/voiceover.py` writes
  per-beat WAVs to `08_export/voiceover/B###.wav` and updates durations).
- `beat_elements` ALREADY holds beat → asset → slot/framing/prompt refs.
- `generations` queue + `library` + channel vault ALREADY exist (Gemini-image
  based, default `manual`). SVG generation extends this, not replaces it.
- All AI art goes through `core/llm_client.dispatch()` (validate → repair →
  escalate → log). SVG code is text — same chain with an XML/SVG schema.
