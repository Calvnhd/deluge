# Extract Instruments — Warning Reference

## Pre-extraction (song discovery)

### 1. Failed to parse XML
```
WARNING: Skipping SomeSong.XML — failed to parse XML: {error}
```
The XML file is malformed and lxml can't parse it. Would happen if a file is corrupted or truncated.

### 2. No `<song>` root element
```
WARNING: Skipping SomeSong.XML — no <song> root element found
```
The file parsed as XML but doesn't have a `<song>` element — not actually a song file.

### 3. Firmware version mismatch
```
WARNING: Skipping SomeSong.XML — firmware 'c1.1.0' (expected 'c1.2.1')
```
The song was saved by a different firmware version. The XML structure may differ so the script skips it.

---

## During clip discovery

### 4. Missing section attribute
```
WARNING: <instrumentClip> for '000' has no section attribute — treating as section 0
```
A clip doesn't have a `section="N"` attribute. The Deluge should always write this — indicates very old firmware or corrupted XML.

---

## During instrument-clip matching

### 5. Orphaned instrument
```
WARNING: Orphaned instrument '000' (folder='SYNTHS', type=synth) — no matching session clips
```
An instrument exists in `<instruments>` but no `<instrumentClip>` in `<sessionClips>` references it. Probably used in arrangement only, or loaded then removed from session view without full cleanup.

**Real example:** Arpo.XML has synth '000' in instruments but no session clip for it.

### 6. Duplicate clip in same section
```
WARNING: Duplicate clip for '009' in section 0, taking first
```
Two `<instrumentClip>` elements reference the same instrument with the same section ID. The script keeps the first. Happens when you duplicate a clip without moving it to a different section.

**Real example:** Dject.XML has two clips for synth '009' both in section 0.

---

## During extraction (per-instrument)

### 7. Unexpected section ID
```
WARNING: (PresetName) — unexpected section ID 14, treating as section 0
```
The clip's section attribute is outside 0–11 (the Deluge has 12 sections). Would indicate corrupt data or a future firmware change.

### 8. drumIndex out of range
```
WARNING: drumIndex 20 out of range (soundSources has 16 sounds) — skipping noteRow
```
A kit clip has a `<noteRow>` pointing to a drum row index that doesn't exist in the kit's `<soundSources>`. Would indicate the kit was modified (rows removed) after the clip was created.

### 9. noteRow has no `<soundParams>`
```
WARNING: noteRow (drumIndex=5) has no <soundParams> — skipping
```
A `<noteRow>` with a `drumIndex` exists but doesn't contain a `<soundParams>` child. The Deluge normally always includes this — indicates incomplete/corrupted data.

### 10. Kit sound has no clip parameters
```
WARNING: (000, section 0/LightBlue) — Kit sound 'U1' (index 16) has no clip parameters — using defaults
```
A sound exists in the kit's `<soundSources>` but no `<noteRow>` in the selected clip has a matching `drumIndex`. The sound was never used in that clip — could be an empty placeholder row, an unused sample row, or a row added but never programmed. The script clones `<defaultParams>` from another sound in the same kit as a fallback.

**Real example:** Kit 000 in Ambient-Fishes has 17 sounds but the section 0 clip only has noteRows for indices 0–15. Sound "U1" at index 16 is an empty placeholder.
