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

Creates a complete backup of the SD card as a `.zip` file. This is the **first point of backup** - run this before syncing to the repo.

**Usage:**
```bash
./scripts/sd-to-zip.sh
```

Output: `deluge-backup-YYYY-MM-DD.zip` in your configured backup folder.

### sd-to-repo.py

Syncs SD card contents to this repository. This is the **second point of backup** - run after `sd-to-zip.sh`.

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

---

## TODO

- figure out general formatting of files and folders
- script to clean unused samples
- rearrange sample folder structure
- script to save in-use patches to specific folder
- a script to sync to SD card?
- update to latest community firmware
- get presets from latest community competition
- script to produce a list of patches? 
- script to produce a list of samples and their usage data?
