# Deluge

Back-up and management scripts for a [Synthstrom Deluge](https://synthstrom.com/product/deluge/) SD card.

XML presets for kits, synths, and songs are backed up in version control. Due to their size, samples are gitignored and synced to cloud backup via scripts.

> **Note:** This repository is a work in progress.

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

### Sync manifest

The sync manifest (`scripts/data/sync_manifest.json`) tracks per-file SHA256 hashes and metadata (size, mtime) for both the SD card and local repository. It enables change detection during syncs and hash-based move detection when fixing broken references.

- **Updated by:** `sync_from_sd.py`, `sync_to_sd.py`, `fix_references.py`
- **Not used by:** `sync_samples_to_cloud.py`, `sample_overview.py`, `extract_instruments.py`, `create_backup.py`

---

## Scripts

### Overview

**Phase 1: Backup**

| Step | What you do | Script | Status |
|------|-------------|--------|--------|
| 1 | Pull everything off the SD card into the repo | `sync_from_sd.py` | ✅ |
| 2 | Sync samples to cloud backup | `sync_samples_to_cloud.py` | ✅ |
| 3 | Create a .zip backup (optional) | `create_backup.py` | ✅ |

**Phase 2: Organise**

| Step | What you do | Script | Status |
|------|-------------|--------|--------|
| 1 | Clean up songs — delete old versions, rename | (manual) | — |
| 2 | Extract kit and synth presets from songs | `extract_instruments.py` | ✅ |
| 3 | Add, remove, or rearrange synths and kits presets as desired | (manual) | — |
| 4 | Add, remove, or rearrange samples as desired | (manual) | — |

**Phase 3: Update**

| Step | What you do | Script | Status |
|------|-------------|--------|--------|
| 1 | Verify sample references are intact | `sample_overview.py missing` | ✅ |
| 2 | Fix any broken references (uses sync manifest) | `fix_references.py` | ✅ |
| 3 | Sync samples to cloud backup | `sync_samples_to_cloud.py` | ✅ |
| 4 | Sync repo back to SD card | `sync_to_sd.py` | ✅ |

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

### Script reference

#### `sync_from_sd.py`

Syncs the mounted SD card into the local `DELUGE/` directory. Uses the sync manifest for change detection. Deleted files are moved to `.trash/` rather than permanently removed. The SD card is not modified.

```
uv run sync_from_sd.py            # preview changes, then prompt to apply
uv run sync_from_sd.py --dry-run  # preview only
uv run sync_from_sd.py --xml      # sync only XML files
uv run sync_from_sd.py --wav      # sync only WAV files
```

#### `sync_samples_to_cloud.py`

Syncs WAV files from `DELUGE/SAMPLES/` to a local folder for cloud backup, preserving directory structure. Files removed from the source are deleted from the destination.

```
uv run sync_samples_to_cloud.py            # preview changes, then prompt to apply
uv run sync_samples_to_cloud.py --dry-run  # preview only
```

#### `create_backup.py`

Creates a timestamped `.zip` archive of all XML and WAV files.

```
uv run create_backup.py            # create backup
uv run create_backup.py --dry-run  # preview file count and size only
```

#### `extract_instruments.py`

Extracts standalone synth and kit presets from song XMLs into `SYNTHS/SONG-SYNTHS/` and `KITS/SONG-KITS/`. Includes cross-song deduplication to remove near-identical presets, and sidechain-only kit detection.

```
uv run extract_instruments.py                           # preview, then prompt to apply
uv run extract_instruments.py --dry-run                 # preview only
uv run extract_instruments.py --extended                # extract multiple versions when params differ
uv run extract_instruments.py --no-dedup                # disable cross-song deduplication
uv run extract_instruments.py --include-sidechain       # include sidechain-only kits (excluded by default)
uv run extract_instruments.py --exclude-dir testing     # skip songs in a subdirectory
uv run extract_instruments.py --sd-direct               # read/write directly to SD card
uv run extract_instruments.py --verbose                 # detailed dedup comparison logging
uv run extract_instruments.py --naming preset           # Preset-SongName filenames (default)
uv run extract_instruments.py --naming song             # SongName-Preset filenames
```

#### `fix_references.py`

Fixes broken sample references after samples have been moved or renamed. Reads the sync manifest for hash-based move detection and computes a migration map of moved, deleted, added, and stale files. 

Also includes duplicate detection with optional (naive) deletion.

```
uv run fix_references.py
```

#### `sync_to_sd.py`

Syncs the local `DELUGE/` directory back to the mounted SD card. Uses the sync manifest for change detection. Files on the SD card that don't exist in the local directory are hard-deleted (not trashed).

```
uv run sync_to_sd.py            # preview changes, then prompt to apply
uv run sync_to_sd.py --dry-run  # preview only
uv run sync_to_sd.py --xml      # sync only XML files
uv run sync_to_sd.py --wav      # sync only WAV files
```

#### `sample_overview.py`

Sample library overview and reference checking tool. Cross-references XML presets with the filesystem to show what's in use, what's unused, and what's missing.

```
uv run sample_overview.py                                   # library summary (equivalent to "summary --top 5")
uv run sample_overview.py summary --top N                   # summary with custom top-N most-referenced
uv run sample_overview.py unused                            # condensed per-folder summary of unreferenced samples
uv run sample_overview.py unused --all                      # full listing of all unreferenced samples grouped by folder
uv run sample_overview.py unused --folder DRUMS             # full listing filtered to specific folder(s)
uv run sample_overview.py unused --top N                    # top N largest unreferenced samples
uv run sample_overview.py missing                           # samples referenced in XML but missing from disk
uv run sample_overview.py duplicates                        # find duplicate samples by content hash
uv run sample_overview.py usage "Kick"                      # usage detail for samples matching a search term
```

