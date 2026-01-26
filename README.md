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

**Behavior:**
- New/modified files are copied from SD card to `DELUGE/`
- Files deleted from SD card are moved to `DELUGE/.trash/`
- Only syncs `.xml` and `.wav` files

### sync-samples.sh

`DELUGE/SAMPLES/` is too large to store on GitHub and may contain copyrighted material. Use this script to sync to a another cloud-synced folder for back-up.

**Usage:**
```bash
./scripts/sync-samples.sh
```

### create-manifest.py

Generates manifests of all SD card contents for quick reference. Outputs both markdown and CSV formats for each category.

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

---

## TODO

- figure out general formatting of files and folders
- script to clean unused samples
- rearrange sample folder structure
- script to save in-use patches to specific folder
- a script to sync to SD card?
- update to latest community firmware
- get presets from latest community competition
- ~~script to produce a list of patches?~~ ✅ `create-manifest.py`
- ~~script to produce a list of samples and their usage data?~~ ✅ `create-manifest.py`
