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

### Config

All scripts read configuration from `scripts/.env`

### `sync_from_sd.py`

Syncs the mounted SD card into the local `DELUGE/` directory so it mirrors the card exactly. The SD card is never modified — all changes flow one way (SD card → repo).

**Usage** (run from the `scripts/` directory):

```
python sync_from_sd.py            # preview changes, then prompt to apply
python sync_from_sd.py --dry-run  # preview only, no changes
python sync_from_sd.py --confirm  # skip preview, go straight to confirmation
```

### Ideas

- Creates a complete backup of the SD card as a `.zip` file 
- Sync the local gitignored `SAMPLES` folder to a another cloud-synced folder for back-up
- Consider a library for parsing and working with the SD card contents?
- Generate a manifest of all SD card contents for quick reference
- Identify and fix broken sample references
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

