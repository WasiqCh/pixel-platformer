# DECISION — SVG raster tool (P2-T01, decided 2026-09-25)

**Winner: Inkscape headless CLI. Probbed at runtime, never hard-coded.**

## Evidence (spike, run on this machine)

3 test SVGs (character w/ face landmarks + outlines, environment w/ floor plane + props,
text plates w/ `font-family="Arial, sans-serif"`), exported at 1920×1080, each tool run twice.

| Tool | Result | Time (1080p) | Deterministic | Notes |
|---|---|---|---|---|
| Inkscape 1.4.4 headless | ✅ works | 1.3–1.9 s | YES (same sha256 ×2, all 3 files) | Exact `-w/-h` control; fonts resolved; fidelity verified by eye |
| Edge `--headless=new --screenshot` | works | ~2 s | not verified ×2 | Needed `--allow-file-access-from-files`; screenshot semantics (viewport, DPI, scrollbars) — fragile, not purpose-built |
| cairosvg 2.9.1 (pip) | ❌ dead | — | — | Installs, but `libcairo-2.dll` missing on Windows; needs GTK bundle DLLs — fragile machine setup, rejected |

Spike artifacts (not committed): `%TEMP%\opencode\raster-spike\` (SVGs + runner + PNGs).

## Rules for implementation (P2-T06)

1. Probe order at runtime: `INKSCAPE_PATH` env → PATH (`inkscape`) → known MSIX location
   glob (version-pinned, WILL break on update — never hard-code the full path).
2. Clear error naming every location tried when not found.
3. Command shape: `inkscape <svg> --export-type=png --export-filename=<png> -w 1920 -h 1080`
   (size follows the asset's target; 1920×1080 is the scene/export default).
4. Cache by SVG content hash — identical bytes = cache hit, no re-raster.
5. Never the GUI. Never a new pip dependency for raster.
6. Budget: ~1.5 s/asset → ~10 min per 400-asset full pass, one-time each (cache after).
