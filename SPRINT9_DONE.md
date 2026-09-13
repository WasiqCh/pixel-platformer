# SPRINT 9 — DONE ✅ (The Money Pair)

> The studio became a factory: prompts → images → editor timeline, zero copy-paste.

## Completed tasks
- [x] 9.1 Generation backend — generations queue table (masters + poses); composer upserts
      the queue on every compose so generated files survive recomposes; Gemini/Nano Banana
      integration with reference chaining (poses attach their master image for face
      consistency); background Generate All with rate-limit pacing; image_settings
      (provider/key/model) with masked key display.
- [x] 9.2 Generation Queue UI — queue card in Library: per-row ▶, ▶ Generate All with live
      3s polling, PENDING/READY/ERROR chips, error reasons, in-app thumbnails;
      generated masters auto-flip Library slots to READY.
- [x] 9.3 Editor Export — POST /export/editor writes 08_export/:
      episode.edl (CMX3600, 25fps, contiguous record timecodes, * LAYER comments for
      midground/insert files), overlays.srt (timed stickers with type tags),
      editor_manifest.json (per-beat plate/actors/inserts/overlay + missing list).
- [x] 9.4 Doc + commit.

## Proof points (spice episode)
- 45 queue rows (22 masters + 23 poses); M01 generated in ~30s → thumbnail in-app and
  E01 Library slot auto-READY.
- Generate All ran the whole queue in background; rate-limited rows retryable per-row.
- Editor export: 63 clips · 15 stickers · ~430s; SRT #1 = "Moluccas, the Spice Islands
  [place_label]" 00:00:00,000 → 00:00:07,200; "1498" at 00:04:06,800.
- episode.edl imports into DaVinci/Premiere as a pre-timed 63-clip timeline.

## Lessons learned
- Queue as a DB table (not files) makes generation resumable, retryable, recompose-safe.
- Reference chaining (master → pose) is what keeps faces consistent across panels.
- EDL + SRT = universal handshake with every editor; no proprietary format needed.

## Parked
Auto-Download safety gate · channel-level library · TTS timing · meme mode ·
beat reorder · alternate prompts per beat.
