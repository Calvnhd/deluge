# Deluge

Deluge SD card back-up and scripts for managing its contents

---

## SD card file and folder structure

- **DELUGE**:
    - **KITS** - Kit presets
    - **SONGS** - Song presets
    - **SYNTHS** - Synth presets
    - **SAMPLES** - Audio samples
        - **ARTISTS** - Pre-made samples from various artists shipped with the Deluge
        - **CLIPS** - User recordings created with the internal mic or line-in during AUDIO CLIP VIEW
            - **TEMP** - Clip recordings are initially saved here and moved into the parent folder when the SONG is saved
        - **RECORD** - User recordings created with the internal mic or line-in during KIT CLIP VIEW
        - **RESAMPLE** - User recordings created with the resample feature
        ... 
        Additional user created folders

**NOTE:** SONGS store kit and synth information within their own .xml files, therefore KITS and SYNTHS can be altered independently without breaking SONGS. Care must be taken to not break references when moving SAMPLES.

---

## Scripts

All scripts read configuration from `scripts/.env`. Copy `scripts/.env.example` to `scripts/.env` and edit with your paths before running.

### sd-to-zip.sh

Creates a complete backup of the SD card as a `.zip` file. 

**Usage:**
```bash
./scripts/sd-to-zip.sh
```

Output: `deluge-backup-YYYY-MM-DD.zip` in your configured backup folder.

### sd-to-repo.py

Syncs SD card contents to this repository. 

**Requirements:**
- Python 3.9+

**Usage:**
```bash
./scripts/sd-to-repo.py
# or
python3 scripts/sd-to-repo.py
```

**Safety features:**
- Shows a dry-run preview of all changes before applying
- Requires explicit confirmation (`y`) before modifying any files
- Never writes to the SD card (read-only source)

**Behavior:**
- New/modified files are copied from SD card to `DELUGE/`
- Files deleted from SD card are moved to `DELUGE/.trash/`
- Only syncs `.xml` and `.wav` files

### sync-samples.sh

`DELUGE/SAMPLES/` is too large to store on GitHub and may contain copyrighted material. Use this script to sync the local SAMPLES folder to a another cloud-synced folder for back-up.

**Usage:**
```bash
./scripts/sync-samples.sh
```

**Safety features:**
- Validates source contains `.wav` files before syncing (prevents accidental backup deletion)
- Prompts for confirmation before deleting files from backup destination

### deluge_sdk.py

A Python library for parsing and working with Deluge SD card contents. This module provides reusable data structures and functions for reading Deluge XML files (kits, synths, songs) and tracking sample usage.

> ⚠️ **Read-Only:** This library only reads data. It will never modify any `.XML` or `.wav` files.

**Requirements:**
- Python 3.9+

**Usage:**
```python
from deluge_sdk import parse_kit, parse_synth, parse_song, KitInfo, SynthInfo, SongInfo
from pathlib import Path

# Parse a kit preset
kit = parse_kit(Path("DELUGE/KITS/KIT000.XML"))
print(f"Kit uses {len(kit.samples)} samples")

# Parse a synth preset
synth = parse_synth(Path("DELUGE/SYNTHS/MySynth.XML"))
print(f"Synth firmware: {synth.firmware_version}")

# Parse a song
song = parse_song(Path("DELUGE/SONGS/MySong.XML"))
print(f"Song uses {len(song.kits)} kits and {len(song.synths)} synths")
print(f"Has arrangement: {song.has_arrangement}")
```

**Available components:**

| Category | Components |
|----------|------------|
| **Data Structures** | `KitInfo`, `SynthInfo`, `SongInfo`, `SampleInfo`, `ManifestData` |
| **High-level Parsing** | `parse_kit()`, `parse_synth()`, `parse_song()` |
| **Low-level XML** | `parse_deluge_xml()`, `extract_firmware_version()`, `get_actual_root()` |
| **Sample Extraction** | `extract_sample_paths()`, `extract_audio_clip_samples()`, `extract_embedded_instrument_samples()` |
| **Instrument Extraction** | `extract_instruments_from_song()` |
| **Utilities** | `format_size()`, `format_date()` |

**Handles multiple XML formats:**
- Old format (no firmware version, multiple root elements)
- v2.x format (`<firmwareVersion>` as separate element)
- v4.x format (`firmwareVersion` as attribute on root)

### create-manifest.py

Generates manifests of all SD card contents for quick reference. Outputs both markdown and CSV formats for each category. Uses `deluge_sdk.py` for XML parsing.

> ⚠️ **Work in Progress:** This script is under active development and has not been thoroughly tested. Sample tracking and XML parsing may have edge cases that produce inaccurate results. Please verify critical information manually.

**Requirements:**
- Python 3.9+

**Usage:**
```bash
./scripts/create-manifest.py
# or
python3 scripts/create-manifest.py
```

**Output:**
- `docs/manifest-kits.md` / `.csv` - Kit presets
- `docs/manifest-synths.md` / `.csv` - Synth presets
- `docs/manifest-songs.md` / `.csv` - Song projects
- `docs/manifest-samples.md` / `.csv` - Sample files (used/unused)

**What each manifest contains:**

| Manifest | Contents |
|----------|----------|
| **Kits** | Name, samples used, last modified, firmware version |
| **Synths** | Name, samples used (if any), last modified, firmware version |
| **Songs** | Name, kits/synths/audio tracks/MIDI channels, arrangement status, last modified, firmware version |
| **Samples** | Used/unused status, file size, last modified, detailed usage info |

**Sample usage tracking:**

The samples manifest shows exactly where each sample is used:
- `Kit: KIT000` - Used by a kit preset file
- `Synth: Bass` - Used by a synth preset file  
- `Audio: AUDIO2 (in MySong)` - Used by an audio clip in a song
- `Kit: KIT000 (in MySong)` - Used by an embedded kit within a song

This distinction matters because songs store independent copies of kit/synth configurations. A sample might be used by a preset file AND a song's embedded copy (which could differ from the preset).

**Broken reference detection:**

The script warns about samples referenced in XML files that don't exist on disk. This helps identify:
- Samples that were moved or renamed
- Samples that were deleted but still referenced
- Path case-sensitivity issues

### Sample Migration Scripts

A set of three scripts for safely reorganizing your `SAMPLES/` folder without breaking XML references. Uses file hashing to detect moved files regardless of path or filename changes.

> 📖 **New to hashing?** See [docs/hashing-eli5.md](docs/hashing-eli5.md) for an explanation of how these scripts work and why hashing is useful.

**Requirements:**
- Python 3.9+

#### verify-refs.py

Checks that all sample references in XML files point to files that actually exist. Run this before and after reorganizing samples.

```bash
# Check for broken references
python scripts/verify-refs.py

# Show all references (valid and broken)  
python scripts/verify-refs.py --all

# Group broken refs by sample instead of by file
python scripts/verify-refs.py --by-sample
```

#### scan-samples.py

Creates hash manifests of your samples folder. Run `--before` before reorganizing, then `--after` afterwards to detect what moved.

```bash
# Create baseline manifest
python scripts/scan-samples.py --before

# After reorganizing, detect moves and generate migration map
python scripts/scan-samples.py --after

# Preview without saving
python scripts/scan-samples.py --before --dry-run
```

**Output files (in `docs/`):**
- `sample-manifest-before.json` - Baseline with SHA256 hashes
- `sample-manifest-after.json` - Post-reorganization state  
- `sample-migration-map.json` - Old path → new path mapping

#### update-refs.py

Applies the migration map to update all XML files with new sample paths.

```bash
# Preview changes without modifying files
python scripts/update-refs.py --dry-run

# Apply changes (creates .bak backups)
python scripts/update-refs.py

# Apply without backups (if using git)
python scripts/update-refs.py --no-backup
```

#### Complete Migration Workflow

```bash
# 1. Verify current state is clean
python scripts/verify-refs.py

# 2. Create baseline manifest  
python scripts/scan-samples.py --before

# 3. Reorganize SAMPLES folder however you want
#    (move files, rename folders, etc.)

# 4. Detect what moved
python scripts/scan-samples.py --after

# 5. Preview XML changes
python scripts/update-refs.py --dry-run

# 6. Apply changes
python scripts/update-refs.py

# 7. Verify everything still works
python scripts/verify-refs.py
```

**Handles edge cases:**
- Detects **duplicate files** (same content, different paths) and flags them for manual review
- Works even if you **rename files** (matching is by content, not filename)
- Preserves **case sensitivity** (important for the Deluge)
- Creates **backups** before modifying any XML files

---

## TODO

- figure out general formatting of files and folders
- script to clean unused REC samples
- rearrange sample folder structure
- script to save in-use patches to specific folder
- a script to sync to SD card?
- update to latest community firmware
- resave... everything?  So xml files are consistent.  Idk, this is probably excessive. 
- get presets from latest community competition
