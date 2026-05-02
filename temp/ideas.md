# Feature Ideas

Parking lot for future feature ideas to revisit.

---

## Mark sidechain kits in song XMLs

**Date:** 2026-05-02

The extraction code (`is_sidechain_kit()` in `deluge_lib/extraction.py`) already detects sidechain-only kits. On detection, we could rename the kit *in the song XML only* to mark it — e.g. add a `[SC]` suffix to `presetName` / `instrumentPresetName`.

**Why:**
- Provides a fast-path detection criterion for future runs
- Makes sidechain kits visually obvious when browsing song XMLs
- Low complexity — just 2 XML attribute updates per kit (instrument + matching clips) plus writing the modified song XML back to disk
