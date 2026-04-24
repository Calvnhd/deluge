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

## Test xmls

A bunch of song xmls have been created on the Deluge that have some unconvential quirks.  The steps to create these files are detailed below. The purpose of these is to analyse how the XML data changes between song versions, and understand how edits on the deluge are reflected in the data. Then, we can observe how they are parsed and understood by our code to find and fix bugs, confirm the warnings are appropriate, look for edge cases we've missed etc.

### Duppy

Create a new song and load clip with "init-kit"
    init-kit:
        loaded sample, U1 row -> hr16b
        added another row, load sample r-50
v2
    init kit: add new row, but do not load sample (i.e. create "no sound" row)
v3
    init kit: delete "no sound" row
v4
    init kit: no changes
    Create clip, load kit "000 tr 808"
v5
    init kit: create duplicate in new section
    000 tr 808: create duplicate in new section
    created kit1, loaded with 32 slices of a single sample
    created kit2, loaded with 4 different samples
    loaded deeper
v6
    init kit: new section, added no sound row
    000 tr 808: new section, added 2 no sound rows (one at each end)
    kit1: added one no sound row
    kit2: added one no sound row
    deeper: added one no sound row
v7
    create a section 3 clip for all instruments
v8
    Make general edits in the section 3 clip for all instruments
    init kit: delete all rows except hr16block
    000 tr 808: delete all rows except no sound row
    kit1: delete 10 rows (incl no sound row)
    kit2: delete all but hook2-8bars-108bpm
    deeper: delete all but rhythmace snare
v9
    load analog machine kit
    add some general sequencing info to section 0 clips
    mute a few kit rows in section 1 and 2
v10
    delete all clips except analog machine


### Triggy

Create a new song and load clip with init synth 
    init synth: changed type (waveform) and add some basic sequencing information
v2
    init synth: added a bunch of sections and variations
    added kit clip for 3 sections with variations
v3
    added arranger info using exising instrument clips
v4
    added arranger specific (white) sections to existing instruments: 
        synth white clip created uniquely in arranger 
        kit white clip created by converting a looped light blue section
v5
    added new instrument, unique to arranger view. Create a number of white clips
v6
    convert white clips for original synth and kit to coloured, automatically adding them to song view.
v7
    convert white clips to coloured for instrument created in arranger view, automatically adding them to song view. 
v8
    change preset for an instrument while in arranger view - is this reflected in song view?
v9
    change preset to bassdirtyswell for one clip in song view - is this reflected for other clips in song view and/or arranger view?
v10
    add multiple clips for an instrument in one section only
v11 
    delete all song view info except for bassdirtyswell duped sections 
    edit one of these sections to have very very different settings
v12
    put a bassdirtyswell into its own section
v13
    In arranger view, delete white clips for instruments that no longer exist in song view
v14
    In arranger view, delete instruments that don't exist in song view. Convert remaining white clips to coloured
v15
    add init-synth again, make a bunch of edits - how are these reflected in the xml?
        modulation [sidechain -> side level] to 30 (range: -50 to +50)
        [pan] to 25 (range: -25 to +25)
        [osc1 transpose] 96 (range: -96 to +96)
        [osc2 transpose] 40
        modulation [LFO -> LPF] to 40 (range: -50 to +50)
    deleted other insts from song view and arr view
v16
    init synth, create section 1:
        modulation [sidechain -> side level] to -49 (range: -50 to +50)
        [pan] to -25 (range: -25 to +25)
        [osc1 transpose] -96 (range: -96 to +96)
        [osc2 transpose] -40
        modulation [LFO -> LPF] to -50 (range: -50 to +50)
        [HPF cutoff] to 25 (range: 0 to +50)
v17
    muted a few notes in the clip for both synths
    added a kit with some sequencing info
v18
    muted some rows on the new kit
    load clip with tr808, and edit the instrument into a typical sidechain only kit
v19
    created a new, dedicated sidechain kit for future use

---

One more note, I usually have sidechain kits in my songs.  The easiest way to set this up is grab some factory kit that has a sidechain send configured for the kick sample row, then...

    1) sequence the kick and nothing else 
        AND 
    2) turn the volume down on the kick row and/or the entire clip

That way the sample sound is never heard, but the sidechain send is still triggered. If no other kit rows have any sequencing information (i.e. the kit is not being used as a full kick), then it is a dedicated side chain kit.  It's likely that my current song set has a few of these which should be ignored during extraction.  

Are we able to make a definition for sidechain kit, and test each kit on extraction?

---