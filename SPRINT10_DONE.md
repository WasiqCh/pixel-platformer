# SPRINT 10 — DONE ✅ (The Reuse Layer)

> Real-world assets fetch themselves (legally), and finished art is reused across episodes.

## Completed tasks
- [x] 10.1 Auto-Download Desk — ✨ auto-search on Wikimedia Commons filtered to
      PD / CC0 / CC-BY / CC-BY-SA only (NC & ND excluded — monetized channel);
      candidate strip with thumbnails + license + author; human picks the image;
      backend downloads into the Library slot; provenance = source URL | license | author.
      Zero scraping of copyrighted sources, ever.
- [x] 10.2 Channel Vault — channel_library table + data/channels/{ch}/library/ store;
      every finished master (generated / uploaded / downloaded) is copied into the vault,
      keyed by normalized title; Library scaffold pre-fills matching slots as READY
      (source='channel', 🌐 chip); GET /channels/{id}/vault lists the vault.
- [x] 10.3 Doc + commit.

## Proof points (spice episode)
- VOC logo ✨ search returned public-domain candidates; one click → READY +
  provenance recorded on the world record.
- Obscure record → 0 free-license results → friendly "use 🔎 manual" fallback
  (the safety gate visibly working).
- Deleted slot + re-scaffold → instantly READY 🌐 from vault ("1 reused from channel vault").
- Vault count chip live in the Library readiness bar.

## Lessons learned
- Legal-by-design: license whitelist + human pick = automation without copyright risk.
- Vault key = normalized title, so future episodes match assets by NAME, not by ID.

## Parked
TTS timing · meme mode toggle · drag-to-reorder beats · alternate prompts ·
analytics · i18n.