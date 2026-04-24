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

---

Duppy
init-kit: 
    loaded sample, Existing U1 row -> hr16b
    added another row with sample r-50
2
init kit:
    Add another row, but do not load sample
3
init kit:
    Delete row with no sound
4
init kit:
    no changes
000 tr 808:
    no changes
5
init kit
    copied to new section
000 tr 808
    copied to a new section
kit1
    new kit unique to Duppy, loaded with 32 slices of a single sample
kit2
    new kit, loaded with 4 different samples
deeper
    loaded, no changes
6
init kit
    new section, added no sound row
000 tr 808
    new section, added 2 no sound row (top and bot)
kit1
    added one no sound row
kit2
    added one no sound row
deeper
    added one no sound row
7
add identical section 3 for all insts based on highest existing section
8 - edit section 3 for all
init kit
    delete all rows except hr16block
000 tr 808
    delete all rows except no sound row
kit1
    delete 10 rows (incl no sound row)
kit2
    delete all but hook2-8bars-108bpm
deeper
    delete all but rhythmace snare
9
add analog machine kit
add some sequencing info to section 0 insts
mute kit rows in sec 1
a bit of the same in sec 2
10
delete all insts except analog machine

---

## Pre-extraction (song discovery)

### 1. Failed to parse XML
```
WARNING: Skipping SomeSong.XML — failed to parse XML: {error}
```
do manually

### 2. No `<song>` root element
```
WARNING: Skipping SomeSong.XML — no <song> root element found
```
The file parsed as XML but doesn't have a `<song>` element — not actually a song file.
do manually

### 3. Firmware version mismatch
```
WARNING: Skipping SomeSong.XML — firmware 'c1.1.0' (expected 'c1.2.1')
```
The song was saved by a different firmware version. The XML structure may differ so the script skips it.
do manually

---

## During clip discovery

### 4. Missing section attribute
```
WARNING: <instrumentClip> for '000' has no section attribute — treating as section 0
```
A clip doesn't have a `section="N"` attribute. The Deluge should always write this — indicates very old firmware or corrupted XML.
do manually

---

Triggy
    init synth, changed waveform, added some basic sequence
2
    added a bunch of sections and variations for init synth
    added kit in 3 sections with variations
3
    added arranger info using exising sections and insts only
4
    added arranger specific (white) sections to existing ints. synth, unique in arranger, kit, converted long blue to white
5
    added arranger only inst with white section clips
6
    convert white clips to coloured in song view for existing insts only
7
    convert white clips to coloured for inst that was arranger only
8
    change preset in arranger mode, not song mode for the kit and the previously only arranger most inst
9
    change init kit preset to bassdirtyswell from song mode view
10
    add multiple clips for sections
11 
    delete all song view info except for bassdirtyswell duped sections, and make one section inst very very different to the other
12
    put duped bassdirtyswell into its own section
13
    delete missing insts CLIPS from arranger view (but keep insts)
14
    delete mssing insts from arr, convert existing white to coloured
15
    add init synth again
        set sidechain -> side level to 30 (range -+50)
        pan to 25 (range +-25)
        osc1 transpose 96 (max)
        osc2 transpose 40
        LFO to LPF fre modulation to 40 (-+50)
    deleted other insts from song view and arr view
16
    init synth section 1
        sidechain -side level to -49
        mast pan -25
        psc1 trans -96
        osc2 transpose -40
        LFO to LPF fre modulation to 40 (-50)
        HPF cutoff to 25
17
    muted a few notes in the clip for both synths
    added a kit with some sequencing info
18
    muted some rows on the new kit
    added a typical sidechain only kit based on tr808
19
    created a brand new sidechain kit for dedicated use in the future




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
