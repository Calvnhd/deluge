# Deluge

# Deluge

Back-up and scripts for managing Deluge patches

---

## SD card file and folder structure

- **DELUGE**:
    - **KITS**: Kit presets
    - **SONGS**: Song presets
    - **SYNTHS**: Synth presets
    - **SAMPLES**: Audio samples
        - **ARTISTS**: Pre-made samples from various artists shipped with the Deluge
        - **CLIPS**: User recordings created with the internal mic or line-in during AUDIO CLIP VIEW
            - **TEMP**: Clip recordings are initially saved here and moved into the parent folder when the SONG is saved
        - **RECORD**: User recordings created with the internal mic or line-in during KIT CLIP VIEW
        - **RESAMPLE**: User recordings created with the resample feature
        ... 
        Additional user created folders

**NOTE:** SONGS store kit and synth information within their own .xml files, therefore KITS and SYNTHS can be altered independently without breaking SONGS. Care must be taken to not break references when moving SAMPLES.

## Scripts

### sync-samples.sh

`DELUGE/SAMPLES/` is too large to store on GitHub, and may contain copyrighted material that shouldn't be distributed. Instead, use this script to sync to a another cloud-synced folder for back-up.

1. Copy `scripts/.env.example` to `scripts/.env`
2. Edit `.env` with your paths
3. Run: `./scripts/sync-samples.sh`

---

## TODO

- figure out general formatting of files and folders
- figure out way to link samples folder to cloud back-up
    - some kind of sync script?
- script to clean unused samples
- rearrange sample folder structure
- script to save in-use patches to specific folder
- a script to sync to SD card?
- a script to create a .zip backup?
- update to latest community firmware
- get presets from latest community competition
