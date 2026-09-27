# Wobbly-sketch style (owner-authored 2026-09-27 — candidate channel style kit text)

Create a minimal, crude, intentionally shaky, wobbly-lined digital illustration with a consistent wobbly-line thickness for all visual elements. The overall aesthetic must be a raw, unpolished, wobbly digital sketch style reminiscent of early computer paint programs or a child's digital drawing, full of intentional imperfections. Use flat, varied, solid colors with zero gradients, shading, shadows, or texturing. Simplistic forms define everything, like a front-facing building (simple wobbly rectangles), an open refrigerator packed with simple, wobbly boxes and containers, or organic objects like a wobbly brain or a wobbly-lined pile of trash. Props are basic, wobbly-outlined objects (circuit board with wobbly lines, brain, trash bags). Details are suggested by wobbly-lined patterns or simplified shapes, and lines across different items share the same shaky, imperfect quality. Maintain a flat perspective. Backgrounds are simple, wobbly-lined spaces or flat colors. The entire scene must feel hand-crafted and raw.

---
HOW IT FLOWS (no code changes needed to use this):
1. Paste the text above into the channel's Style Kit descriptor (channel screen).
   That is the source of truth — one place, every episode inherits it.
2. From there it flows automatically: style kit descriptor → `style_descriptor`
   context key in `scene_plan` + `svg_gen` recipes → every AI call draws in
   this style. No per-asset repetition needed.
3. svg_gen ALSO enforces the machine-checkable half (flat fills, outline rule,
   no gradients/shading/texture, self-contained SVG) via recipe rules +
   server-side validation — so the model can't silently drift photorealistic.
