# New scripts

This contains some high level information about two more scripts to create.

## Create .zip backup

- This creates a .zip of the specified folder
- The .zip source will be defined by .env, and will usually be the mounted SD card. There may be special one-off cases where the repo DELUGE folder requires archiving, in which case the .env variable can be adjusted.  These are the only two folders this script will archive.
- It is CRITICAL that the script does not alter the contents of the archive source in any way
- The .zip archive is a snapshot of the source directory at that point in time. 
- The .zip should only archive xml and .wav files (similar to the sync script) unless doing so creates unneccessary complexity and potential bugs
- the .zip contents should match the source directory structure (similar to the sync script)
- This will be run semi regularly to create backups that represent the final fallback of both the SD card the the repo become lost or corrupt
- The .zip will be saved to a specified location (likely a cloud back up folder) defined in .env

## Sync repo to SD

- This syncs repo DELUGE to SD card
- This is essentially the same as script `sync_from_sd.py` but in the other direction
- SD card safety is CRITICAL. The card must not become corrupted.
- Follow the general safety principles of script writing so far
- The SD card does not need a .trash folder like the repo DELUGE folder does, but for added safety we will save SD trash to the local repo. Before deleting from the SD, copy the to-be-deleted file to the .trash folder in the repo in a folder with `SD` as a prefix.  The SD version may then be deleted. 