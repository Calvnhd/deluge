# Project Standards

## Overview

Project-wide standards that apply to all code and scripts in this repository.

---

## SD Card Safety

This repository manages a backup of a physical Deluge SD card. The physical SD card and the repository copy (`DELUGE/`) have different protection levels.

### Rules

1. **The physical SD card is read-only.** Scripts MUST NOT write to, modify, or delete data on the mounted SD card. The only permitted operations on the SD card are **read** and **copy-from**.
2. **The `DELUGE/` directory in this repository is editable.** Modifying, reorganising, and fixing files within `DELUGE/` is a core purpose of this repository. Scripts may freely read and write to `DELUGE/`.
3. When syncing from the SD card into the repository, the sync direction is **SD card → `DELUGE/`**, treating the SD card as the source of truth.
4. When syncing from the repository back to the SD card for deployment, the sync direction is **`DELUGE/` → SD card**. This is the only scenario where writing to the SD card is permitted, and it must require explicit user confirmation (e.g. a `--confirm` flag or interactive prompt). Dry-run should be the default behaviour.
5. Scripts must never assume the SD card is mounted. Always validate the mount point before attempting read operations.

### Rationale

The physical SD card contains the live data used by the hardware device. Accidental writes to the SD card risk corrupting working data. The repository copy exists to be worked on safely — edits are made here, reviewed via version control, and deliberately deployed back to the SD card when ready.

---

## Platform Requirements

Scripts in this repository must work on two target environments without modification.

### Target Platforms

| Platform | OS | Shell | Role |
|---|---|---|---|
| WSL | Linux (Ubuntu) | bash | Development machine |
| Cmder | Windows 11 | bash (Git for Windows) | Music/production machine |

### Rules

1. **Cross-platform by default.** All scripts must run on both platforms. Do not use platform-specific external tools (e.g. `rsync`, `ln -s`) unless a pure Python fallback is provided.
2. **Python is the common runtime.** Use Python with `pathlib` for all file and path operations. This eliminates path-separator and drive-letter issues across platforms.
3. **No subprocess calls to OS-specific tools** unless absolutely necessary. Prefer Python standard library equivalents (`shutil`, `filecmp`, `os`, `pathlib`).
4. **SD card paths differ by platform.** On Linux the SD card is typically mounted at `/media/$USER/DELUGE`; on Windows it appears as a drive letter (e.g. `D:\`). Users configure the path via `SD_CARD_PATH` in `scripts/.env`.
5. **FAT32 timestamp tolerance.** The Deluge SD card uses FAT32, which has 2-second mtime resolution. Any file-comparison logic that uses modification times must allow a ±2-second tolerance.

### Rationale

The music/production machine runs Windows natively with Cmder and has no WSL. Scripts that depend on Unix-only tools would be unusable on the machine that syncs with the physical SD card most often. Python + pathlib provides a single portable foundation for both environments.
