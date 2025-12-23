# Deluge

Back-up and scripts for managing Deluge patches

## SD card file and folder structure

- **DELUGE**:
    - **KITS**: Kit presets
    - **SONGS**: Song presets
    - **SYNTHS**: Synth presets
    - **SAMPLES**: Audio samples
        - **ARTISTS**: Pre-made samples from various artists, shipped with the Deluge
        - **CLIPS**: User recordings using the Deluge's mic or line in
            - **TEMP**: Managed internally. User recordings are initially saved here and moved into the parent folder if the SONG is saved
        - **RECORD**: User recordings
        - **RESAMPLE**: User recordings created using the Deluge's resampling feature
        ... 
        Additional user created folders

**NOTE:** SONGS have reference to the kits and synths embedded within, therefore KITS and SYNTHS can be altered independently without breaking SONGS. Care must be taken when moving SAMPLES to not break references.

## TODO

- back up current state
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

