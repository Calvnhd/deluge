# User flow

This doc describes the final state of the scripts in this repo from the perspective of the user. Eventually, rather than using uv run on each script, the user will have a command on their PATH which can be used to run multiple scripts in a row to complete a general task.

## Current state of scripts

As documented in the README

**Phase 1: Backup**

| Step | What you do | Script | Status |
|------|-------------|--------|--------|
| 1 | Pull everything off the SD card into the repo | `sync_from_sd.py` | ✅ |
| 2 | Sync samples to cloud backup | `sync_samples_to_cloud.py` | ✅ |
| 3 | Take a snapshot of samples | `create_snapshot.py` | ✅ |
| 4 | Create a .zip backup (optional) | `create_backup.py` | ✅ |

**Phase 2: Organise**

| Step | What you do | Script | Status |
|------|-------------|--------|--------|
| 1 | Clean up songs — delete old versions, rename | (manual) | — |
| 2 | Extract kit and synth presets from songs | `extract_instruments.py` | 🚧 |
| 3 | Add, remove, or rearrange synths and kits presets as desired | (manual) | — |
| 4 | Add, remove, or rearrange samples as desired | (manual) | — |

**Phase 3: Update**

| Step | What you do | Script | Status |
|------|-------------|--------|--------|
| 2 | Verify sample references are intact | `sample_overview.py missing` | ✅ |
| 3 | Fix any broken references | `fix_references.py` | ✅ |
| 4 | Sync samples to cloud backup | `sync_samples_to_cloud.py` | ✅ |
| 5 | Sync repo back to SD card | `sync_to_sd.py` | 🚧 |
| 6 | Take a fresh sample snapshot | `create_snapshot.py` | ✅ |

## End goal

The user will be able to use a single command (`delly`, short for deluge) that is on their PATH, and is therefore callable from the command line no matter the directory

### Core flows

`delly backup` with optional `--zip` or `-z`

    1. Run `sync_from_sd.py` 
    2. Run `sync_samples_to_cloud.py`
    3. Run `create_snapshot.py`
    4. Run `sample_overview.py duplicates --snapshot latest`
    5. if `--zip` or `-z`, run `create_backup.py`
    6. Run `sample_overview.py summary`

`delly prep`

    1. Run `sample_overview.py missing`
    2. If step one finds missing refs, run `fix_references.py`
    3. Run `sample_overview.py summary`

`delly update` with optional `--extract` or `-e`, `--zip` or `-z`

    1. If `--extract` or `-e`, run `extract_instruments.py`
    2. Run `sample_overview.py missing`
    3. If missing refs found, run `fix_references.py`
    4. If refs are all intact, run `sync_to_sd.py`
    5. Run `sync_samples_to_cloud.py`
    6. Run `create_snapshot.py`
    7. Run `sample_overview.py duplicates --snapshot latest`
    8. If `--zip` or `-z`, run `create_backup.py`

### Smaller utility cmds

Optionally add `--dry-run` or `-n` where applicable for dry run functionality

`delly sd-sync` —> `sync_from_sd.py`
`delly cloud-sync` —> `sync_samples_to_cloud.py`
`delly snap` —> `create_snapshot.py`
`delly zip` —> `create_backup.py`
`delly get-inst` -> `extract_instruments.py`
    optionally add `--extended` or `-x` for multi version extraction
`delly fix` —> `fix_references.py`
    optionally add `--snapshot` or `-s` for specific snapshot
    optionally add `--apply` or `-a` to skip confirmation (note: fix refs is WIP, this flag may change)
`delly sd-update` —> `sync_to_sd.py`
`delly samples` —> `sample_overview.py summary`
    optionally add `--top` or `-t` for custom output list length
`delly samples unused` —> `sample_overview.py unused`
    optionally add `--top` or `-t` for custom output list length
`delly samples missing` —> `sample_overview.py missing`
`delly samples usage <term>` —> `sample_overview.py usage <term>`
`delly samples duplicates` —> `sample_overview.py duplicates`
    optionally add `--snapshot` or `-s` with a path or `latest` to use existing snapshot


