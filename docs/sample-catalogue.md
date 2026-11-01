---
title: Sample catalogue
description: Generate a deterministic audio-only CSV inventory with sample sizes and preset and song reference counts
---

## Generate the catalogue

Run this command manually from the repository root after syncing or organising your library:

```powershell
uv run --directory scripts sample_overview.py catalogue
```

The command reads `DELUGE_ROOT` from the existing environment configuration in `scripts/.env` and writes `docs/sample-catalogue.csv` in this repository. It is not run automatically by any sync command. Generate the CSV when you want an updated snapshot, then review and commit the result.

From the scripts directory, the equivalent command is:

```powershell
uv run sample_overview.py catalogue
```

To write a separate copy without updating the official catalogue:

```powershell
uv run --directory scripts sample_overview.py catalogue --output C:\Temp\sample-catalogue.csv
```

The generator reuses the filesystem scanner, XML reference extractor, and usage index behind [sample_overview.py](../scripts/sample_overview.py). It does not read or modify the sync manifest, samples, or presets.

## Files and columns

Every WAV, AIF, or AIFF file under the configured `SAMPLES` directory gets one row. Extension matching is case-insensitive. TXT and other non-audio files, directories themselves, and `.trash` directory contents are excluded. Missing sample references are not inventory entries; use `sample_overview.py missing` to investigate them.

| Column          | Meaning                                                             |
|-----------------|---------------------------------------------------------------------|
| `sample_path`   | Full path relative to `DELUGE_ROOT`, beginning with `SAMPLES/`        |
| `size_mb`       | Decimal megabytes: bytes divided by 1,000,000, rounded to three decimal places |
| `kit_presets`   | Distinct standalone kit XML files referencing the file               |
| `synth_presets` | Distinct standalone synth XML files referencing the file             |
| `songs`         | Distinct song XML files referencing the file in any supported context |

Paths preserve filesystem spelling and use `/` separators on every platform. No machine-specific absolute paths are included. Sizes use consistent MB units, rounded to the nearest 0.001 MB (one kilobyte). Very small files can display as `0.000`.

Repeated references within one XML file count once. A song referencing a sample through both an embedded instrument and an audio clip still counts as one song. Separate saved versions of a song count as separate files. Standalone presets extracted from songs count as standalone kit or synth presets as well as any references still present in the source songs.

Song counts come directly from embedded instrument and audio-clip references, not by following names of standalone presets. A reference does not prove that a sample is audible: unused kit rows, untriggered ranges, or muted clips may still reference it. Zero counts mean unreferenced, not safe to delete.

## Stable updates

Rows are ordered by case-folded relative path, then the original path as an explicit tie-breaker. Ordering never depends on filesystem enumeration, size, usage count, or modification time.

The CSV has fixed columns, UTF-8 encoding without a byte-order mark, and LF line endings. It contains no generation timestamp or filesystem mtimes. Unchanged file paths, sizes, and references produce byte-identical output, even if files are discovered in a different order. Adding or deleting files does not rearrange existing rows.

The CSV describes paths, sizes, and reference counts, not content hashes. A same-size audio edit with unchanged references will not change its row. Size changes that round to the same three-decimal MB value also remain invisible. The catalogue is a snapshot of the filesystem and XMLs, not a record of the last sync; finish syncing or editing before generating it.

The generator fails on missing sample directories, traversal/stat errors, or case-colliding paths rather than silently dropping files. XMLs use the existing Deluge-compatible parser, including its warnings and legacy-format recovery. Failed scans, reads, or writes leave an existing catalogue intact; completed output replaces it atomically.

## AIFF and supporting text files

The current community firmware's [audio-file loader](https://github.com/SynthstromAudible/DelugeFirmware/blob/community/src/deluge/storage/audio/audio_file_manager.cpp) recognises both WAV and AIFF headers. Inclusion in the catalogue does not validate that every audio encoding will play on a particular firmware. AIF and AIFF are alternate extensions for the same format. AIFF-C is a related variant and is not assumed to be compatible.

The existing SD sync and ZIP backup scripts select XML and WAV files, and the cloud sample sync selects WAV files only. They currently skip AIFF/AIF and TXT files. Catalogue generation does not change those rules.

The Citizen DJ TXT files contain collection notes, item attribution, source links, and rights/access statements. Keep them with the library to preserve provenance. They remain untouched and are excluded from the catalogue.

## Unexpected files

After writing the CSV, the command prints a separate, path-sorted warning for unexpected non-audio files, including unsupported audio formats. These files are not catalogue rows. Investigate the list before deciding whether to convert, move, or remove anything; the command never deletes files.

TXT sidecars anywhere under `SAMPLES/CITIZEN-DJ` are recognised supporting material and are excluded without warnings. Other non-audio files, including TXT files outside Citizen DJ, are reported for investigation.
