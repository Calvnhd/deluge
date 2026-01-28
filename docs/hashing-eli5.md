# Hashing Explained (ELI5)

This document explains how the sample migration scripts work, focusing on the hashing technique that makes them reliable.

## The Problem

You want to reorganize your `SAMPLES/` folder—maybe sort drums into subfolders, rename files with better names, or consolidate duplicates. But your Deluge XML files contain paths like:

```xml
<fileName>SAMPLES/DRUMS/kick.wav</fileName>
```

If you move `kick.wav` to `SAMPLES/DRUMS/Kicks/808/kick.wav`, every kit, synth, and song that references it will break. With hundreds of samples and dozens of XML files, manually updating references is tedious and error-prone.

**The core challenge:** How do we know that `SAMPLES/DRUMS/Kicks/808/kick.wav` is the same file that used to be at `SAMPLES/DRUMS/kick.wav`?

---

## What is Hashing?

A **hash** is like a fingerprint for a file. It's a fixed-length string of characters computed from the file's contents.

### Simple Analogy

Imagine you have a book. A hash is like saying:
- "The first letter of each chapter spells out DELUGE"
- Plus "it has exactly 50,000 words"
- Plus "the last sentence ends with 'synthesizer'"

If someone hands you a different book, you can quickly check these three things. If they all match, it's *probably* the same book. If any don't match, it's *definitely* a different book.

Real hashing algorithms (like SHA256) do this with math, checking millions of "things" about the file to create a unique fingerprint.

### Real Example

Here's what SHA256 hashes look like:

```
File: kick.wav (a 45KB drum sample)
Hash: a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456

File: snare.wav (a different sample)
Hash: 9f8e7d6c5b4a3210fedcba0987654321fedcba9876543210abcdef1234567890
```

The hash is always 64 characters (for SHA256), regardless of whether the file is 1KB or 1GB.

### Key Properties

1. **Deterministic**: The same file *always* produces the same hash
2. **Unique**: Different files produce different hashes (practically guaranteed)
3. **One-way**: You can't recreate the file from its hash
4. **Fixed-length**: Always 64 characters for SHA256

---

## How the Scripts Use Hashing

### Step 1: scan-samples.py --before

Before you reorganize, the script walks through every `.wav` file and computes its hash:

```json
{
  "by_hash": {
    "a1b2c3d4...": {
      "path": "SAMPLES/DRUMS/kick.wav",
      "size": 45000
    },
    "9f8e7d6c...": {
      "path": "SAMPLES/DRUMS/snare.wav",
      "size": 32000
    }
  }
}
```

This is your "before" snapshot—a map of "fingerprint → location".

### Step 2: You Reorganize

Move files however you want:
```
SAMPLES/DRUMS/kick.wav     →  SAMPLES/DRUMS/Kicks/808/BigKick.wav
SAMPLES/DRUMS/snare.wav    →  SAMPLES/DRUMS/Snares/Acoustic/Snare1.wav
```

### Step 3: scan-samples.py --after

The script scans again and computes hashes:

```json
{
  "by_hash": {
    "a1b2c3d4...": {
      "path": "SAMPLES/DRUMS/Kicks/808/BigKick.wav",
      "size": 45000
    },
    "9f8e7d6c...": {
      "path": "SAMPLES/DRUMS/Snares/Acoustic/Snare1.wav", 
      "size": 32000
    }
  }
}
```

Same hashes, different paths!

### Step 4: Generate Migration Map

The script compares the two manifests:

```json
{
  "moves": {
    "SAMPLES/DRUMS/kick.wav": "SAMPLES/DRUMS/Kicks/808/BigKick.wav",
    "SAMPLES/DRUMS/snare.wav": "SAMPLES/DRUMS/Snares/Acoustic/Snare1.wav"
  }
}
```

It matched files by their fingerprints, not their names or locations.

### Step 5: update-refs.py

Now updating XML is simple—find-and-replace each old path with its new path:

```xml
<!-- Before -->
<fileName>SAMPLES/DRUMS/kick.wav</fileName>

<!-- After -->
<fileName>SAMPLES/DRUMS/Kicks/808/BigKick.wav</fileName>
```

---

## Why Hashing Works Well Here

### ✅ Rename-Proof

You renamed `kick.wav` to `BigKick.wav`. A filename-based approach would fail—it would think the old file was deleted and a new file appeared. Hashing sees through the rename because the *content* is unchanged.

### ✅ Move-Proof

You moved a file through 5 nested folders. The path is completely different. Hashing doesn't care—same content, same hash.

### ✅ Handles Duplicates

What if you accidentally have the same sample in two places?

```
SAMPLES/DRUMS/kick.wav          (hash: a1b2c3d4...)
SAMPLES/OLD STUFF/kick.wav      (hash: a1b2c3d4...)  ← Same!
```

The script detects this and flags it as "ambiguous"—you need to decide which location is the "real" one. This prevents accidentally breaking references.

### ✅ Detects Accidental Changes

If you accidentally modify a file (maybe your audio editor re-saved it with slight differences), the hash changes. The script will treat it as "file deleted, new file added" rather than "file moved"—which is correct behavior, because it's technically not the same file anymore.

---

## Limitations of Hashing

### ⚠️ Slow on Large Libraries

Computing SHA256 requires reading every byte of every file. For a 50GB sample library, this could take several minutes.

**Mitigation in our scripts:**
- Progress indicators show you it's working
- You only need to do this when reorganizing (not frequently)

### ⚠️ Duplicate Ambiguity

If you have identical files in multiple locations:
```
SAMPLES/DRUMS/kick.wav
SAMPLES/Archive/kick.wav
SAMPLES/Project-Old/kick.wav
```

All three have the same hash. If you delete two and keep one, the script can't know *which* original path should map to the remaining file. It flags these as "ambiguous" for manual review.

### ⚠️ Intentional Re-encoding

If you re-encode samples (e.g., convert 24-bit to 16-bit to save space), the hash changes. The script will see these as different files. For this scenario, you'd need to update references manually or use filename matching instead.

---

## Alternative Approaches

### Filename Matching

**How it works:** Match files by name only, ignoring path.

```python
# Before: SAMPLES/DRUMS/kick.wav
# After:  SAMPLES/DRUMS/Kicks/808/kick.wav
# Match:  Both named "kick.wav" ✓
```

**Pros:**
- Very fast (no need to read file contents)
- Works even if files are re-encoded

**Cons:**
- Fails if you rename files
- Fails if you have duplicate filenames (e.g., multiple `kick.wav` in different folders)

**When to use:** Quick reorganization where you're only moving files (not renaming) and have no duplicate filenames.

### Git Rename Detection

**How it works:** Git can detect when files are moved/renamed using its own similarity algorithm.

```bash
git add -A
git status  # Shows "renamed: old/path -> new/path"
```

**Pros:**
- Very sophisticated detection (works even with minor edits)
- Already integrated if you use version control

**Cons:**
- Requires temporarily tracking large binary files
- Git's rename detection can be confused by too many changes at once

**When to use:** You're already using git and moving a small number of samples.

### Database/Catalog Approach

**How it works:** Maintain a database that tracks files by a unique ID you assign.

```
ID: 001  | Path: SAMPLES/DRUMS/kick.wav | Hash: a1b2... | Tags: drums, 808
ID: 002  | Path: SAMPLES/DRUMS/snare.wav | Hash: 9f8e... | Tags: drums, acoustic
```

**Pros:**
- Survives re-encoding (ID stays the same)
- Can track metadata, tags, etc.
- Fast lookups

**Cons:**
- Requires maintaining the database
- Need to update it whenever you add files
- More complex implementation

**When to use:** Large sample libraries that you curate actively, or if you frequently re-encode/process samples.

### Interactive Move Tool

**How it works:** Instead of moving files manually, use a tool that moves the file AND updates all XML references in one atomic operation.

```bash
./move-sample.py "SAMPLES/DRUMS/kick.wav" "SAMPLES/DRUMS/Kicks/808/BigKick.wav"
# Moves file AND updates all 47 XML files that reference it
```

**Pros:**
- Impossible to break references (updates happen together)
- No "before/after" scanning needed

**Cons:**
- Must use the tool for every move (can't use Explorer/Finder)
- Slower for bulk reorganization
- More complex to implement (needs to find references first)

**When to use:** Occasional single-file moves, or environments where you want strict control.

---

## Summary

| Approach | Speed | Handles Renames | Handles Duplicates | Complexity |
|----------|-------|-----------------|-------------------|------------|
| **Hashing** (our scripts) | Slow | ✅ Yes | ⚠️ Flags for review | Medium |
| Filename matching | Fast | ❌ No | ❌ Ambiguous | Low |
| Git detection | Medium | ✅ Yes | ⚠️ Sometimes | Low |
| Database/catalog | Fast | ✅ Yes | ✅ Yes | High |
| Interactive move | N/A | ✅ Yes | ✅ Yes | Medium |

**Hashing is a good default** because it:
- Works with any folder structure
- Handles renames gracefully
- Requires no ongoing maintenance
- Warns you about duplicates instead of guessing wrong

The main cost is speed—but for a one-time reorganization, waiting a few minutes is worth the confidence that nothing will break.

---

## Quick Reference

```bash
# Full workflow
python scripts/verify-refs.py           # Check current state
python scripts/scan-samples.py --before # Snapshot before
# ... reorganize your samples ...
python scripts/scan-samples.py --after  # Detect moves
python scripts/update-refs.py --dry-run # Preview changes
python scripts/update-refs.py           # Apply changes
python scripts/verify-refs.py           # Verify result
```
