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

### Config

All scripts read configuration from `scripts/.env`

### Script ideas

- Creates a complete backup of the SD card as a `.zip` file 
- Sync SD card contents to this repository
- Sync the local gitignored `SAMPLES` folder to a another cloud-synced folder for back-up
- Consider a library for parsing and working with the SD card contents?
- Generate a manifest of all SD card contents for quick reference
- Identify and fix broken sample references
- List of used and unused samples
- Lift kits and synths from songs to a dedicated location 
- Bulk rename songs with trailing numbers (after manually deleting old versions)

## Other Todos

- Re-arrange your samples into a structure that is actually usable 

