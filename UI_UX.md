# UI/UX — "Pixel Platformer" Design System & Screen Map

> Identity: a cute, original 8-bit platformer skin (Super-Mario-*inspired*,
> zero Nintendo assets). Premium = polished, consistent, readable — not austere.
> The tool looks like the videos it produces: MS Paint DNA, game joy.

---

## 1. Design Tokens (the whole theme lives here)

### Colors
| Token | Value (approx) | Use |
|---|---|---|
| sky | #5C94FC | App background (textured) |
| panel | #FFF8E7 | Content panels (flat, no texture) |
| ink | #232323 | Text, borders |
| brick | #8B5A2B | Secondary borders, sidebar accents |
| primary (Mario-red) | #E7402D | Primary actions, locks, destructive |
| success (pipe-green) | #2FA84F | approved / final / saved |
| warn (coin-yellow) | #F7B32B | stale dots, advisories, buffers |
| danger | #C0392B | rejected, error badges |
| info (cloud-blue) | #3E7BFA | links, info, queued |

Semantic colors are SACRED: green/yellow/red mean the same thing on
every screen, forever. Theme may change; semantics never do.

### Type
- Display (logo, big numbers, tiny labels): "Press Start 2P" — never body text.
- Headings / badges: "Pixelify Sans".
- Body / UI / data: "Nunito" (rounded, highly readable).
Rule: pixel fonts ≤ 20% of any screen; everything you read for >5 seconds is Nunito.

### Shape & Depth
- Borders: 2px solid ink/brick; radii small (6–8px) — crisp, not bubbly.
- Shadows: hard offset, no blur (4px 4px 0 ink @ 20%) — the "block" feel.
- Buttons lift on hover (-1px,-1px + shadow grows); press = sink.

### Texture
- Background: sky blue + faint tiled pixel-clouds (low opacity SVG/CSS).
- Panels: FLAT cream. Texture never enters reading surfaces.
- Brick pattern only on decorative strips (login, sidebar footer, empty states).

### Icons & Motion
- Original 16/24px pixel icon set, 2px-consistent.
- Micro-motion: coin-pop on success, block-pop toasts, tiny bounce on hover.
- Respect prefers-reduced-motion. Optional 8-bit SFX toggle (OFF by default).

---

## 2. Layout Grammar

- **Left sidebar:** the pipeline MAP (free navigation — every node always
  clickable; amber dots show stale items; Changes inbox lives here).
- **Top bar:** channel switcher · project switcher · model/queue status ·
  transparency drawer button · user.
- **Main canvas:** one board/studio per phase; panels on the sky.
- **Right drawer (contextual):** transparency panel / SVO reveal / lesson audit —
  scoped per beat, auto-reset, hidden from teammates by role.
- Density: boards are card grids; data-heavy views (mention map, metrics) are
  clean Nunito tables — cuteness never taxes scanability.

---

## 3. Screen Inventory (every screen, from locked phases)

| # | Screen | Purpose / key components |
|---|---|---|
| S01 | Home | 3 doors (idea/title/script) + open project; project grid; duplicate/fork. |
| S02 | Idea Studio | Big canvas + Surprise me; card grid; detail view with stats + refine loop; Shelf tab. |
| S03 | Title Studio | 10-card grid (angle, tag, char count); shortlist/remix/regen-selected; own-title door. |
| S04 | Script Studio | Slider↔duration; outline pass; streaming editor; hook highlight; pacing strip; breakdown sidebar; sanity card; Lock & continue. |
| S05 | Cast Board | Character cards (kind/faction/presence/green flag); drawn↔fetched toggle; significance pick; resolution inspector. |
| S06 | Variant Timelines | Per-character strips; merge/split spans; dashed low-confidence; "+1 sheet" labels. |
| S07 | Scout Board | Environment cards; elements; variation chips (trimmable); merge/split. |
| S08 | World Desk | Grouped RW/meme/map cards; usage intent; meme mode; search-query chips. |
| S09 | Choreography Board | Pose lists per variant; type badges; suggestions tray; sheet counter. |
| S10 | Card View | 8-slot prompt cards; lint badges; diff-regen; copy prompt+refs. |
| S11 | Export & Download Desk | Package builder; generation checklist; RW "search in browser" rows; drop/import zone. |
| S12 | Checkpoint Board | Thumbnail grid; triple view; 4+1 checklist; bulk triage; sticky notes. |
| S13 | Library | Browse/search by tags; usage counts; retire; savings counter. |
| S14 | Beat Studio | Chunk-grouped beats; pacing visualizer; element chips w/ layer tags; SVO reveal; one-off tray; text-only toggles. |
| S15 | Storyboard & Handoff | Scrollable storyboard; retention flags overlay (P23); versioned export. |
| S16 | Channel Intelligence | Metrics rows; retention sparklines pinned to beats; lessons list; diff approvals. |
| S17 | Settings | Models (3 slots + one-model checkbox) · kit wizard · overlay tokens · shot-type registry · thresholds · SFX/theme toggles. |
| G01 | Ripple Review (global) | Diff left / affected items right; keep/regen/decide-later per item. |
| G02 | Transparency Drawer | Scoped per beat; summarized; dev-visible. |

---

## 4. Component Library (build once, reuse everywhere)

BlockButton · IconChip · StatusDot (green/amber/red) · AssetTag (id + layer
badge) · Card (panel + hard shadow) · BoardGrid · DiffView · VersionPill ·
SliderWithBadge (words↔duration) · ToggleRow · Toast (block-pop) ·
EmptyState (brick strip + pixel mascot) · Checklist4+1 · SuggestionsTray.

---

## 5. UX Rules (locked behaviors, rendered)

1. Map, not fence — no disabled steps; empty nodes say "not started".
2. Manual always visible — every AI surface has an edit/override/skip affordance.
3. Advisories never block — amber notes, sanity cards, lints are glanceable, optional.
4. Ripple = one review screen, no popup spam; batched on leave/apply.
5. Streaming for long text; queued badges for jobs; autosave everything.
6. Versions everywhere — VersionPill + revert on scripts, titles, cards, kits.
7. Teammate-safe defaults — dev tools (inspect, transparency) hidden by role.
8. Readability guardrails — pixel fonts capped; textures outside panels;
   contrast ≥ WCAG AA; reduced-motion honored.

---

## 6. Theme Engine & Future

- All tokens in one Tailwind/CSS-variables file → re-theme in an afternoon.
- Parked: per-channel accent themes; seasonal easter-egg skins (1-2 days/year).
- Legal line: original pixel assets only; inspired-by, never copied.