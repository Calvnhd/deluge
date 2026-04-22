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

Syncs the mounted SD card into the local `DELUGE/` directory. The SD card is not modified.

```
uv run sync_from_sd.py            # preview changes, then prompt to apply
uv run sync_from_sd.py --dry-run  # preview only
```

#### `sync_samples_to_cloud.py`

Syncs WAV files from `DELUGE/SAMPLES/` to a local folder for cloud backup, preserving directory structure. Files removed from the source are deleted from the destination.

```
uv run sync_samples_to_cloud.py            # preview changes, then prompt to apply
uv run sync_samples_to_cloud.py --dry-run  # preview only
```

#### `create_snapshot.py`

Hashes all samples and saves a dated JSON snapshot to `docs/manifests/`. Take a snapshot before reorganising samples so `fix_references.py` can detect what moved.

```
uv run create_snapshot.py
```

#### `create_backup.py`

Creates a timestamped `.zip` archive of all XML and WAV files.

```
uv run create_backup.py            # create backup
uv run create_backup.py --dry-run  # preview file count and size only
```

#### `extract_instruments.py` 🚧

Extracts standalone synth and kit presets from song XMLs into `SYNTHS/SONG-SYNTHS/` and `KITS/SONG-KITS/`.

```
uv run extract_instruments.py              # preview, then prompt to apply
uv run extract_instruments.py --dry-run    # preview only
uv run extract_instruments.py --extended   # extract multiple versions when params differ (WIP)
```

#### `fix_references.py`

Fixes broken sample references after samples have been moved or renamed. Compares a before-snapshot against the current filesystem and updates XML paths. Auto-finds the latest snapshot if `--snapshot` is omitted.

```
uv run fix_references.py                                             # use latest snapshot, preview and prompt
uv run fix_references.py --snapshot docs/manifests/<snapshot>.json   # use specific snapshot
uv run fix_references.py --apply                                     # skip confirmation prompt
```

#### `sync_to_sd.py` 🚧

Syncs the local `DELUGE/` directory back to the mounted SD card. Files to be deleted from the SD card are first backed up to `DELUGE/.trash/` in the repo before removal.

```
uv run sync_to_sd.py            # preview changes, then prompt to apply
uv run sync_to_sd.py --dry-run  # preview only
```

#### `sample_overview.py`

Sample library overview and reference checking tool. Cross-references XML presets with the filesystem to show what's in use, what's unused, and what's missing.

```
uv run sample_overview.py                  # library summary (equivalent to "summary --top 5")
uv run sample_overview.py summary --top N  # summary with custom top-N most-referenced
uv run sample_overview.py unused           # unreferenced samples grouped by folder
uv run sample_overview.py unused  --top N  # top N largest unreferenced samples
uv run sample_overview.py missing          # samples referenced in XML but missing from disk
uv run sample_overview.py usage "Kick"     # usage detail for samples matching a pattern
```

### Ideas

- sync script can specify whether or not to sync samples?
- Consider a library for parsing and working with the SD card contents?
- Generate a manifest of all SD card contents for quick reference
- Bulk rename songs with trailing numbers (after manually deleting old versions)

## Other Todos

- Re-arrange your samples into a structure that is actually usable
- Same with synths
- Same with kits

---

## AI-Assisted Development

This repository uses a structured agent system. See [AGENTS.md](AGENTS.md) for full details.

Key workflow: **Research → Plan → Implement** feature pipeline using specialist agents. Use the `orchestrator` agent mode as the default entry point.

