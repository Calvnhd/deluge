# Copilot Instructions for Deluge Project

## Overview

This repo manages the SD card contents for a Synthstrom Deluge hardware sampler/synth. It stores XML presets (kits, synths, songs) in version control while keeping large sample files backed up separately via sync scripts.

## Architecture

### Directory Layout (mirrors Deluge SD card)
```
DELUGE/
├── KITS/      # Drum kit XMLs - reference samples via relative paths
├── SYNTHS/    # Synth preset XMLs - oscillator/filter/envelope configs
├── SONGS/     # Full song XMLs - embed instrument configs + patterns
└── SAMPLES/   # Audio files (NOT in git - backed up via scripts/)
```

### Critical: Sample Path References
Kit and song XMLs reference samples using **relative paths from DELUGE/**:
```xml
<fileName>SAMPLES/DRUMS/Kick/808 Kick.wav</fileName>
```
- Paths are case-sensitive on the Deluge
- Moving/renaming samples **breaks** all referencing presets
- When modifying sample paths, grep all XMLs for affected references

### XML File Structure
- **Kits** (`<kit>`): Collection of `<sound>` elements in `<soundSources>`, each with oscillator/sample config
- **Synths** (`<sound>`): Single instrument with oscillators, filters, envelopes, modulation
- **Songs** (`<song>`): Full project with `<instruments>` containing embedded kit/synth configs plus `<tracks>` with note data

All XMLs include `firmwareVersion` - preserve this when editing to maintain compatibility.

## Conventions

### When Creating Scripts
- Use bash with `set -e` style error handling
- Load config from `.env` files (see `scripts/.env.example` pattern)
- Validate paths before destructive operations
- Support Linux, WSL `/mnt/c/` style, and Windows 11 paths

## Common Tasks

| Task | Approach |
|------|----------|
| Find samples used by a kit | `grep -h "fileName" DELUGE/KITS/KIT000.XML` |
| Find all kits using a sample | `grep -rl "SAMPLES/DRUMS/Kick" DELUGE/KITS/` |
| Check for broken sample refs | Compare `<fileName>` paths against actual SAMPLES/ contents |
| Backup samples | `./scripts/sync-samples.sh` |

## Deluge firmware

The firmware used by the Deluge is available in this workspace in the repository DelugeFirmware/.
If required, use the firmware to deepen your understanding of the Deluge's functionality