# Deluge

Back-up and management scripts for a [Synthstrom Deluge](https://synthstrom.com/product/deluge/) SD card.

XML presets for kits, synths, and songs are backed up in version control. Due to their size, samples are gitignored and synced to cloud backup via scripts.

> **Note:** This repository is a work in progress. Some folders (e.g. `scripts/`) may be empty or incomplete.

---

## Repository structure

```
deluge/
├── DELUGE/        # SD card backup (see below)
├── scripts/       # Scripts for managing SD card contents
├── docs/          # Project documentation
└── agent-system/  # AI-assisted development configuration
```

### SD card structure

The `DELUGE/` folder mirrors the contents of the Deluge SD card:

- **KITS/** — Kit presets
- **SYNTHS/** — Synth presets
- **SONGS/** — Song presets (include embedded kit and synth data)
- **SAMPLES/** — Audio samples (gitignored)
- **MIDIFollow.XML** — MIDI Follow Mode config mapping MIDI CCs to Deluge parameters

SONGS store their own kit and synth data, so KITS and SYNTHS can be altered independently. Sample paths in XMLs are hardcoded and case-sensitive — moving or renaming samples breaks referencing presets.

---

## Scripts

### Overview

**Phase 1: Backup**

| Step | What you do | Script | Status |
|------|-------------|--------|--------|
| 1 | Pull everything off the SD card into the repo | `sync_from_sd.py` | ✅ |
| 2 | Sync samples to cloud backup | `sync_samples_to_cloud.py` | ✅ |
| 3 | Create a .zip backup (optional) | `create_backup.py` | ✅ |
| 4 | Take a sample snapshot for future reference fixing | `create_snapshot.py` | ✅ |

**Phase 2: Organise**

| Step | What you do | Script | Status |
|------|-------------|--------|--------|
| 1 | Clean up songs — delete old versions, rename | (manual) | — |
| 2 | Rearrange samples into a usable folder structure | (manual) | — |
| 3 | Rearrange synth and kit presets | (manual) | — |

**Phase 3: Update**

| Step | What you do | Script | Status |
|------|-------------|--------|--------|
| 1 | Extract kit and synth presets from songs | `extract_instruments.py` | 🚧 |
| 2 | Verify sample references are intact | `verify_references.py` | ✅ |
| 3 | Fix any broken references | `fix_references.py` | ✅ |
| 4 | Sync samples to cloud backup (if samples were reorganised) | `sync_samples_to_cloud.py` | ✅ |
| 5 | Sync repo back to SD card | `sync_to_sd.py` | 🚧 |
| 6 | Take a fresh sample snapshot | `create_snapshot.py` | ✅ |

### Setup

Scripts require **Python 3.12+**. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) to manage Python and dependencies:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows (PowerShell):

```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Copy the example config and set paths for your machine:

```
cp scripts/.env.example scripts/.env
```

All scripts read configuration from `scripts/.env`. See `.env.example` for available options. Run all scripts from the `scripts/` directory.

### `sync_from_sd.py`

Syncs the mounted SD card into the local `DELUGE/` directory so it mirrors the card exactly. The SD card is never modified — all changes flow one way (SD card → repo).

```
uv run sync_from_sd.py            # preview changes, then prompt to apply
uv run sync_from_sd.py --dry-run  # preview only, no changes
```

### `verify_references.py`

Checks that all samples (.WAV) referenced in all XML presets point to existing files under `DELUGE/`. Reports any broken references.

```
uv run verify_references.py
```

### `create_backup.py`

Creates a timestamped `.zip` archive of the SD card (or any configured source directory). Archives all XML and WAV files with compression.

```
uv run create_backup.py            # create a backup
uv run create_backup.py --dry-run  # preview file count and size only
```

### `fix_references.py`

**Status:** Work in progress

Fixes broken sample references after samples have been moved or renamed. Works in two steps:

1. **Snapshot** — hash all samples and save a manifest before reorganising:

   ```
   uv run fix_references.py snapshot
   ```

   This writes a dated JSON snapshot to `docs/manifests/`.

2. **Fix** — compare the snapshot against the current filesystem, find moved/renamed samples, and update XML references:

   ```
   uv run fix_references.py fix --snapshot docs/manifests/<snapshot>.json
   uv run fix_references.py fix --snapshot docs/manifests/<snapshot>.json --apply  # skip confirmation prompt
   ```

   Without `--apply`, the script previews the changes and prompts before writing.

Both scripts read `DELUGE_ROOT` from `scripts/.env`.

### `sync_samples_to_cloud.py`

Syncs all WAV files from `DELUGE/SAMPLES/` to a configurable local folder for cloud backup, preserving directory structure. Only WAV files are copied. Files removed from the source are deleted from the destination. Non-WAV files already at the destination are left untouched.

`CLOUD_BACKUP_PATH` must be set in `scripts/.env`.

```
uv run sync_samples_to_cloud.py            # preview changes, then prompt to apply
uv run sync_samples_to_cloud.py --dry-run  # preview only, no changes
```

### Ideas

- sync script can specify whether or not to sync samples?
- Consider a library for parsing and working with the SD card contents?
- Generate a manifest of all SD card contents for quick reference
- List of used and unused samples
- Lift kits and synths from songs to a dedicated location 
- Bulk rename songs with trailing numbers (after manually deleting old versions)

## Other Todos

- Re-arrange your samples into a structure that is actually usable
- Same with synths
- Same with kits

---

## AI-Assisted Development

This repository uses a structured agent system. See [AGENTS.md](AGENTS.md) for full details.

Key workflow: **Research → Plan → Implement** feature pipeline using specialist agents. Use the `orchestrator` agent mode as the default entry point.

