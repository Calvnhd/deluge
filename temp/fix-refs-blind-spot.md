# fix_references blind spot: pre-existing broken refs (17 Apr 2026)

## The problem

`verify_references.py` finds 2 broken references that `fix_references.py` silently ignores:

```
KITS/030 Chaz Bundick.XML — SAMPLES/ARTISTS/CHAZ/CB1-BD~1.WAV
KITS/030 Chaz Bundick.XML — SAMPLES/ARTISTS/CHAZ/CB2-BD~1.WAV
```

## Why verify catches them

`verify_references` does a straightforward existence check: for every sample path in every XML, does the file exist on disk? It builds a case-insensitive set of all files under `SAMPLES/` (via `normalise_key`), then checks each XML reference against it. Simple and complete.

## Why fix misses them

`fix_references` only knows about changes *relative to a snapshot*. `classify_ref_changes` checks each ref against three categories from the migration map:

1. `migration.moved` — the file was at path A in the snapshot and is now at path B → auto-fixable
2. `migration.deleted` — the file was in the snapshot but no longer exists → error
3. `migration.ambiguous` — multiple files share a hash → warning

Anything not matching these three is silently assumed valid. But these 8.3 short-name refs were **never in any snapshot** — they were broken before the first snapshot was taken. So the migration map has no knowledge of them and they fall through every check.

## Why the Deluge plays them fine

These are Windows 8.3 short filenames (`CB1-BD~1.WAV` = `CB1-bdrum1.wav`). FAT32 stores both the long name and the 8.3 alias in the same directory entry. The Deluge firmware reads FAT32 directly and resolves the alias transparently. On Linux ext4, there's no 8.3 aliasing, so the literal path doesn't exist.

There's also a case mismatch: the XML says `SAMPLES/ARTISTS/CHAZ/` but the disk has `SAMPLES/Artists/Chaz/`. FAT32 is case-insensitive so both work on the Deluge; ext4 is case-sensitive so neither resolves.

## The actual files

XML references → actual files on disk:
- `SAMPLES/ARTISTS/CHAZ/CB1-BD~1.WAV` → `SAMPLES/Artists/Chaz/CB1-bdrum1.wav`
- `SAMPLES/ARTISTS/CHAZ/CB2-BD~1.WAV` → `SAMPLES/Artists/Chaz/CB2-bdrum2.wav`

## What needs fixing

`classify_ref_changes` needs a fourth check: if a ref doesn't match moved/deleted/ambiguous, verify the file actually exists on disk (case-insensitively). If it doesn't, report it as an error.

### Key consideration: case sensitivity

Any existence check must be case-insensitive to match FAT32 behaviour. A naive `Path.is_file()` on Linux will produce false positives (e.g. `808 Clap.wav` vs `808 Clap.WAV` — same file on FAT32, different on ext4).

`verify_references` solves this with `normalise_key()` (lowercases everything). The same approach should work here.

### Where to source the file list

`compute_migration_map` already calls `hash_all_samples(deluge_root)` which walks every sample on disk. The set of existing paths is right there — it just isn't surfaced. Options:

1. **Add to MigrationResult**: store a normalised set of current paths on the dataclass, built from the `after_hashes` that `compute_migration_map` already computes. No extra I/O.
2. **Pass separately**: have `classify_ref_changes` accept an existing-samples set as a parameter alongside the migration result.
3. **Decouple from snapshot**: add a snapshot-independent mode to `fix_references` that just does existence checking (like verify does), so it works even without a snapshot.
4. **Flip the dependency**: have `classify_ref_changes` call `check_references` first to get all broken refs, then overlay the migration map to classify them. Flow becomes: (a) `check_references` finds all broken refs via existence check, (b) migration map classifies which are auto-fixable (moved), deleted, or ambiguous, (c) anything broken but not in the migration map = pre-existing broken ref. Cleaner conceptually but doubles sample scanning (once for hashing in migration map, once for existence in verify) — unless the sample walk is factored out as a shared step. Note: `check_references` is currently a monolith with print statements baked in, so it would need to be split into a pure logic function and a CLI wrapper before it could be reused.
