# Deluge agent instructions

## Project overview

This repository contains a back-up of a Synthstrom Deluge (hardware sampler/synth) SD card and scripts for managing its contents. XML presets for kits, synths, and songs are backed up in version control, audio files are backed up separately in cloud storage and synced via scripts.

**Note:** This repository is a work in progress. Some folders (e.g. `scripts/`) may be empty or incomplete

### Repository structure

```
deluge/
├── DELUGE/        # SD card backup (see below)
├── scripts/       # Scripts for managing SD card contents
├── docs/          # Project documentation
└── agent-system/  # AI-assisted development configuration
```

---

## Deluge SD card 

### Directory layout

```
DELUGE/
├── KITS/         # Kit XMLs
├── SYNTHS/       # Synth XMLs
├── SONGS/        # Song XMLs
├── SAMPLES/      # Audio samples (gitignored)
│   ├── ARTISTS/  # Pre-made samples from various artists shipped with the Deluge
    ├── CLIPS/    # User recordings created with the internal mic or line-in during AUDIO CLIP VIEW
    │   └── TEMP/ # Clip recordings are initially saved here and moved into CLIPS/ when the SONG is saved
    ├── RECORD/   # User recordings created with the internal mic or line-in during KIT CLIP VIEW
│   ├── RESAMPLE/ # User recordings created with the resample feature
│   └── .../      # Additional user-created folders
└── MIDIFollow.XML # MIDI Follow Mode config — maps MIDI CCs to Deluge parameters
```

This structure mirrors that of a Deluge SD card, where DELUGE is the name of the SD card while KITS, SYNTHS, SONGS, SAMPLES are the four top level folders the card contains.

### Dependencies and interactions

- Song XMLs store their own kit and synth information to maintain song-specific edits to presets loaded from KITS and SYNTHS, therefore KITS and SYNTHS can be altered without breaking SONGS
- Kit, song, and synth XMLs reference audio samples using hardcoded, case-sensitive paths from `DELUGE/` e.g. `fileName="SAMPLES/DRUMS/Kick/XV5080 Kick.wav"`, therefore moving or renaming samples breaks all referencing presets

### Firmware version

- The Deluge associated with this repository is currently running the latest Community Firmware version `firmwareVersion="c1.2.1"`
- Each XML file specifies the firmware version that produced it
- The XML structures have significantly changed over time.

---

## Additional resources

- The firmware used by the Deluge is available in this workspace in the repository `DelugeFirmware`
- The wiki for the Deluge firmware is available in this workspace in the repository `DelugeFirmware.wiki`

---

## AI-Assisted Development

This repository uses the agent-system for AI-assisted engineering.

- **Agents** are registered in `.github/agents/` (VS Code discovery path)
- **Skills, standards, and routing** live in `agent-system/`
- The **orchestrator** (`.github/agents/orchestrator.agent.md`) is the recommended default mode — it enforces routing by lacking edit/execute tools

### Pre-Flight Checklist (MANDATORY)

Before responding to ANY user request:

1. [ ] Read [`agent-system/AGENTS.md`](agent-system/AGENTS.md)
2. [ ] Check routing table for keyword matches
3. [ ] Delegate to subagent if domain match found

**DO NOT PROCEED** until you have completed the checklist.

---
