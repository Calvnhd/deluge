# Scripts Overview

## Configuration

### `.env` / `.env.example`
**Purpose:** Store machine-specific paths for scripts (SD card mount point, backup destinations).

**Reasoning:** Different users have different folder structures (Linux, WSL, Windows). Centralizing config avoids hardcoded paths and keeps sensitive paths out of version control.

---

## Core Library

### `deluge_sdk.py`
**Purpose:** Shared Python library for parsing Deluge XML files (kits, synths, songs) and extracting data.

**Reasoning:** All scripts that need to read Deluge XML share common parsing logic. Centralizing this avoids code duplication and ensures consistent handling of old/new firmware formats. **Read-only by design.**

---

## Backup & Sync Scripts

### `sync-samples.sh`
**Purpose:** Mirror the SAMPLES folder to a backup location using rsync.

**Reasoning:** SAMPLES contains large audio files that shouldn't live in git. This script provides a simple way to back them up to cloud storage (e.g., OneDrive via WSL). Uses rsync's `--delete` for true mirroring with safety checks.

### `sd-to-repo.py`
**Purpose:** Sync contents FROM a physical Deluge SD card INTO this repository.

**Reasoning:** When you've been working on the Deluge, you need to pull changes back to the repo. This script safely copies new/modified files and moves deleted files to `.trash/` rather than permanently deleting. **Read-only to SD card.**

### `sd-to-zip.sh`
**Purpose:** Create a complete zip backup of the SD card for cloud storage.

**Reasoning:** Provides a point-in-time snapshot of the entire SD card. Useful before major reorganization or as an offsite backup. Only includes `.xml` and `.wav` files.

---

## Sample Management Scripts

### `scan-samples.py`
**Purpose:** Generate SHA256 hash manifests of all samples to detect moved/renamed files.

**Reasoning:** When reorganizing the SAMPLES folder, file paths break XML references. By hashing files BEFORE and AFTER reorganization, this script creates a migration map that identifies where files moved to (regardless of rename). **Read-only.**

### `update-refs.py`
**Purpose:** Update sample path references in XML files based on a migration map.

**Reasoning:** After samples are moved/renamed, all XML files referencing them break. This script reads the migration map from `scan-samples.py` and rewrites XML files with corrected paths. **Modifies XML files** - use with caution.

### `verify-refs.py`
**Purpose:** Verify that all sample references in XML files point to files that actually exist.

**Reasoning:** Pre-flight check before reorganizing samples, or post-migration validation. Finds broken references so you can fix them before they cause problems on the Deluge. **Read-only.**

---

## Manifest & Documentation Scripts

### `create-manifest.py`
**Purpose:** Generate human-readable manifests (markdown + CSV) of all kits, synths, songs, and samples.

**Reasoning:** Provides documentation of SD card contents - what samples each kit uses, what instruments each song contains, which samples are unused, etc. Output goes to `docs/`. **Read-only to DELUGE folder.**

---

## Utility Scripts

### `rename_songs.py`
**Purpose:** Clean up song filenames by removing trailing version numbers after old versions are deleted.

**Reasoning:** Deluge auto-increments song saves (`MySong.XML` → `MySong 2.XML` → `MySong 3.XML`). After manually deleting old versions, this script renames the remaining file back to the base name. **Dry-run by default.**

---

## Script Safety Matrix

| Script | Reads DELUGE/ | Writes DELUGE/ | Reads SD Card | Writes SD Card |
|--------|---------------|----------------|---------------|----------------|
| `deluge_sdk.py` | ✓ | ✗ | - | - |
| `sync-samples.sh` | ✓ | ✗ | - | - |
| `sd-to-repo.py` | ✓ | ✓ | ✓ | ✗ |
| `sd-to-zip.sh` | ✗ | ✗ | ✓ | ✗ |
| `scan-samples.py` | ✓ | ✗ | - | - |
| `update-refs.py` | ✓ | **✓** | - | - |
| `verify-refs.py` | ✓ | ✗ | - | - |
| `create-manifest.py` | ✓ | ✗ | - | - |
| `rename_songs.py` | ✓ | **✓** | - | - |

---

## Typical Workflows

### After a Deluge session
1. `sd-to-repo.py` - Pull changes from SD card to repo
2. `sync-samples.sh` - Back up any new samples
3. Commit XML changes to git

### Before reorganizing samples
1. `scan-samples.py --before` - Create baseline hash manifest
2. Reorganize files manually
3. `scan-samples.py --after` - Create post-reorganization manifest
4. `update-refs.py --dry-run` - Preview XML updates
5. `update-refs.py` - Apply XML updates
6. `verify-refs.py` - Confirm all references are valid

### Creating documentation
1. `create-manifest.py` - Generate all manifests in `docs/`
