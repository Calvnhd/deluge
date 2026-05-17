# Deluge CLI v0.1
"""Fix sample references in Deluge XML files after reorganising samples."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from deluge_lib.cli_utils import confirm_apply, get_deluge_root
from deluge_lib.scanning import normalise_key, print_path, scan_tree
from deluge_lib.deluge_sdk import (
    SampleRef,
    extract_sample_refs,
    find_all_xml_files,
    hash_file,
)
from deluge_lib.syncing import FilesDict, read_manifest, write_manifest
from deluge_lib.paths import SYNC_MANIFEST_PATH

# ===== DATA CLASSES =====

@dataclass
class MigrationResult:
    """Result of comparing sample data in manifest state with the current library

    Attributes:
        moved: Unambiguous 1:1 moves
            k: old_path, v: new_path
        deleted: Sample present in manifest, absent from library
            k: hash, v: list of old path(s)
        added: Sample present in library, absent from manifest
            k: hash, v: list of new path(s)
        stale: Sample present in both, manifest entry count exceeds library entry count
            k: hash, v: list of manifest path(s)
        lib_duplicates: Sample exists at multiple library locations
            k: hash, v: list of current path(s)
        library_hashes: Full index of unique hashes present in sample library
            k: hash, v: list of current path(s)
    """

    moved: dict[str, str] = field(default_factory=dict)
    deleted: dict[str, list[str]] = field(default_factory=dict)
    added: dict[str, list[str]] = field(default_factory=dict)
    stale: dict[str, list[str]] = field(default_factory=dict)
    lib_duplicates: dict[str, list[str]] = field(default_factory=dict)
    library_hashes: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class PlannedChange:
    """A sample reference that can be automatically fixed via the migration map."""

    ref: SampleRef
    old_path: str
    new_path: str


@dataclass
class BrokenRefError:
    """A sample reference pointing to file that does not exist"""

    ref: SampleRef
    broken_path: str


@dataclass
class ReferenceStatus:
    """Result of scanning SAMPLE references in all XMLs against a migration map"""

    changes: list[PlannedChange] = field(default_factory=list)
    errors: list[BrokenRefError] = field(default_factory=list)

# ===== HELPER FUNCTIONS =====

def _compute_migration_map(
    manifest: FilesDict,
    deluge_root: Path,
) -> MigrationResult:
    """Compare manifest state (most recent sync) with the current state 
    of the sample library, and record the differences

    Args:
        manifest: Current sync manifest (or empty if none exists)
        deluge_root: Absolute path to the DELUGE directory

    Returns:
        A :class:`MigrationResult` categorising every hash as moved, deleted,
        added, duplicate, or unchanged (omitted).
    """
    # ----- Get hashes from manifest, mapped to path(s) -----
    manifest_hashes: dict[str, list[str]] = defaultdict(list)
    if len(manifest) == 0:
        print("Warning: Manifest is empty or missing \u2014 move detection unavailable")
    else:
        for path, file_record in manifest.items():
            h = file_record.get("hash")
            if h is not None:
                manifest_hashes[h].append(path)

    # ----- Scan local sample library -----
    samples_dir = deluge_root / "SAMPLES"
    if not samples_dir.is_dir():
        print(f"Warning: SAMPLES directory {samples_dir} does not exist")
        return MigrationResult()
    wav_scan = scan_tree(samples_dir, label="SAMPLES", file_filter="wav")

    # ----- Get current hashes from library, mapped to path(s) -----
    library_hashes: dict[str, list[str]] = defaultdict(list)
    files_to_hash: list[tuple[str, Path]] = []

    for _wav_scan_key, library_entry in wav_scan.files.items():
        library_path = str(PurePosixPath(Path("SAMPLES") / library_entry.rel_path))
        manifest_key = normalise_key(library_path)
        abs_library_path = samples_dir / library_entry.rel_path

        # Check if this library entry exists and matches manifest
        manifest_entry = manifest.get(manifest_key)
        if manifest_entry is not None:
            cached_hash = manifest_entry.get("hash")
            if (
                cached_hash is not None
                and library_entry.mtime > 0 # guard against FAT32 and Deluge quirks
                and library_entry.size == manifest_entry["local_size"]
                # Both mtime values are FAT32-normalised: library by scan_tree(), manifest at write time
                and library_entry.mtime == manifest_entry["local_mtime"]
            ):
                # Cache hit: trust the manifest hash
                library_hashes[cached_hash].append(library_path)
                continue
        files_to_hash.append((library_path, abs_library_path))
        
    # Hash library files that do not have a trustworthy manifest entry
    if files_to_hash:
        total = len(files_to_hash)
        for i, (library_path, abs_library_path) in enumerate(files_to_hash, 1):
            print(f"\rHashing {i}/{total}...", end="", flush=True)
            library_hashes[hash_file(abs_library_path)].append(library_path)
        print()

    # ----- Compare manifest data with actual library -----
    deleted: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}
    moved: dict[str, str] = {}
    stale: dict[str, list[str]] = {}
    lib_duplicates: dict[str, list[str]] = {}

    # loop through ALL unique hashes and compare
    for h in set(manifest_hashes) | set(library_hashes):

        manifest_paths = manifest_hashes.get(h, [])
        library_paths = library_hashes.get(h, [])

        if len(manifest_paths) == 1 and len(library_paths) == 1:
            if manifest_paths[0] != normalise_key(library_paths[0]):
                moved[manifest_paths[0]] = library_paths[0]
        elif manifest_paths and not library_paths:
            deleted[h] = list(manifest_paths)
        elif library_paths and not manifest_paths:
            added[h] = list(library_paths)
        elif len(manifest_paths) > 1 and len(library_paths) > 0:
            library_paths_norm = {normalise_key(p) for p in library_paths}
            stale_path = [mp for mp in manifest_paths if mp not in library_paths_norm]
            if stale_path:
                stale[h] = stale_path

        if len(library_paths) > 1:
            lib_duplicates[h] = list(library_paths)

    return MigrationResult(
        moved=moved,
        deleted=deleted,
        added=added,
        lib_duplicates=lib_duplicates,
        stale=stale,
        library_hashes=dict(library_hashes)
    )


def _classify_ref_changes(
    migration: MigrationResult,
    deluge_root: Path,
) -> ReferenceStatus:
    """Scan all XML references and classify them against a manifest-library migration map

    Args:
        migration: Result from :func:`_compute_migration_map`.
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        A :class:`ReferenceStatus` separating fixable changes, errors, and warnings.
    """

    result = ReferenceStatus()

    # ----- Build flat lookup sets -----

    deleted_paths: set[str] = set()
    for paths in migration.deleted.values():
        deleted_paths.update(paths)

    library_paths: set[str] = set()
    for paths in migration.library_hashes.values():
        for p in paths:
                library_paths.add(normalise_key(p))

    stale_entry_hashes: dict[str, str] = {}
    for file_hash, paths in migration.stale.items():
        for p in paths:
            stale_entry_hashes[p] = file_hash

    # ----- Build index that matches lowercase basename to list of (library_path, hash) -----

    basename_index: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for file_hash, paths in migration.library_hashes.items():
        for p in paths:
            basename_index[PurePosixPath(p).name.lower()].append((p, file_hash))

    # ----- Iterate through each xml and check each SAMPLE reference -----

    xml_files = find_all_xml_files(deluge_root)
    for xml_path in xml_files:
        refs = extract_sample_refs(xml_path, deluge_root)
        for xml_ref in refs:
            xml_ref_norm = normalise_key(xml_ref.path)

            # Moved? We need to update reference path from old to new
            if xml_ref_norm in migration.moved:
                result.changes.append(
                    PlannedChange(ref=xml_ref, old_path=xml_ref.path, new_path=migration.moved[xml_ref_norm])
                )
            # Deleted? We need to notify user about broken reference
            elif xml_ref_norm in deleted_paths:
                result.errors.append(
                    BrokenRefError(ref=xml_ref, broken_path=xml_ref.path)
                )
            # No matching library path but not deleted or moved
            elif xml_ref_norm not in library_paths:

                # Can we find a hash in the stale manifest data?
                stale_entry_hash = stale_entry_hashes.get(xml_ref_norm)
                if stale_entry_hash is not None:
                    matching_lib_paths = migration.library_hashes[stale_entry_hash]
                    # Could be duplicates, doesn't matter, just take first
                    recovered_path = matching_lib_paths[0]
                    result.changes.append(
                        PlannedChange(ref=xml_ref, old_path=xml_ref.path, new_path=recovered_path)
                    )
                    continue

                # Can we match the basename to another existing file?
                xml_ref_basename = PurePosixPath(xml_ref.path).name.lower()
                recovery_candidates = basename_index.get(xml_ref_basename, [])

                if len(recovery_candidates) == 0:
                    # File is either genuinely missing or has been renamed on move
                    result.errors.append(
                        BrokenRefError(ref=xml_ref, broken_path=xml_ref.path)
                    )
                elif len(recovery_candidates) == 1:
                    # Unique name match. Treat like a planned change
                    matched_path, _matched_hash = recovery_candidates[0]
                    result.changes.append(
                        PlannedChange(ref=xml_ref, old_path=xml_ref.path, new_path=matched_path)
                    )
                else:
                    # Multiple candidates - check for duplicated files
                    hashes = {h for _, h in recovery_candidates}
                    if len(hashes) == 1:
                        # Same hashes, same files. Take first match and treat as a planned change
                        matched_path, _matched_hash = recovery_candidates[0]
                        result.changes.append(
                            PlannedChange(ref=xml_ref, old_path=xml_ref.path, new_path=matched_path)
                        )
                    else:
                        # Different hashes, ambiguous match. Treat as broken
                        print(f"WARNING: No file at {xml_ref_norm}. Insufficient data for recovery.")
                        result.errors.append(
                            BrokenRefError(ref=xml_ref, broken_path=xml_ref.path)
                        )
    return result


def _update_sample_refs(xml_path: Path, mapping: dict[str, str]) -> int:
    """Update sample references in *xml_path* according to *mapping*
    Uses simple string replacement to avoid large unreadable diffs

    Args:
        xml_path: Absolute path to the XML file to update
        mapping: Sample reference replacements to apply
            k: current_path, v: new_path

    Returns the number of replacements made.
    """
    if not mapping:
        return 0

    xml_data = xml_path.read_text(encoding="utf-8")
    count = 0

    for old_path, new_path in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        occurrences = xml_data.count(old_path)
        if occurrences:
            xml_data = xml_data.replace(old_path, new_path)
            count += occurrences

    if count > 0:
        xml_path.write_text(xml_data, encoding="utf-8")

    return count


def _preview_and_apply(
    ref_classification: ReferenceStatus,
    deluge_root: Path,
) -> bool:
    """Display planned changes, errors, and warnings, then optionally apply.

    Args:
        ref_classification: Output from :func:`_classify_ref_changes`.
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        bool indicating whether the planned changes were applied
    """
    # Nothing to do
    if (
        not ref_classification.changes
        and not ref_classification.errors
    ):
        print("All sample references are intact. Nothing to do.")
        return False

    # --- Preview changes ---
    changes_by_file: dict[Path, list[PlannedChange]] = defaultdict(list)
    for change in ref_classification.changes:
        changes_by_file[change.ref.xml_file].append(change)
    if changes_by_file:
        print()
        print("-----------")
        print("  CHANGES")
        print("-----------")
        for xml_file in sorted(changes_by_file):
            print(f"  {print_path(xml_file)}:")
            # Deduplicate same old→new pairs and count occurrences
            pair_counts: dict[tuple[str, str], int] = defaultdict(int)
            for change in changes_by_file[xml_file]:
                pair_counts[(change.old_path, change.new_path)] += 1
            # Align arrows based on longest quoted old path in this group
            max_old_len = max(len(f'"{old}"') for old, _ in pair_counts)
            for (old, new), count in pair_counts.items():
                suffix = f" (× {count} refs)" if count > 1 else ""
                quoted_old = f'"{old}"'
                print(f"    {quoted_old:<{max_old_len}} → \"{new}\"{suffix}")

    # --- Errors ---
    if ref_classification.errors:
        print()
        print("----------------------------------------------")
        print("  WAV not found, manual resolution required:")
        print("----------------------------------------------")
        error_counts: dict[tuple[Path, str], int] = defaultdict(int)
        for error in ref_classification.errors:
            error_counts[(error.ref.xml_file, error.broken_path)] += 1
        for (xml_file, broken_path), count in sorted(error_counts.items()):
            suffix = f" (× {count} refs)" if count > 1 else ""
            print(f'  {print_path(xml_file)}: "{broken_path}" {suffix}')

    # --- Summary ---
    print()
    num_changes = len(ref_classification.changes)
    if num_changes == 0:
        print("No sample references to fix")
        print(f"{len(ref_classification.errors)} errors to be manually resolved")
        return False

    print(f"{num_changes} sample reference fixes planned")
    print(f"{len(ref_classification.errors)} to be manually resolved")      

    # --- Confirm ---
    if not confirm_apply(f"\nApply {num_changes} changes to {len(changes_by_file)} files?"):
        print("\nNo changes applied")
        return False

    # --- Apply ---
    total_updated = 0
    files_modified = 0
    for xml_file, planned_changes in sorted(changes_by_file.items()):
        mapping: dict[str, str] = {}
        for change in planned_changes:
            mapping[change.old_path] = change.new_path
        updated = _update_sample_refs(deluge_root / xml_file, mapping)
        if updated > 0:
            files_modified += 1
            total_updated += updated

    print(f"\n*** Applied! ***\n{files_modified} files modified\n{total_updated} references updated")
    return True


def _update_manifest_keys(
    manifest: FilesDict,
    moved: dict[str, str],
    manifest_path: Path,
) -> None:
    """Rename manifest keys for moved files and write the updated manifest

    Args:
        moved: Moved file mappings.
            k: normalised_old_key, v: original_new_path
    """
    if not moved:
        return
    print("\nUpdating manifest...")

    updated = 0
    for old_key, new_library_path in moved.items():
        new_key = normalise_key(new_library_path)
        if old_key in manifest:
            manifest[new_key] = manifest.pop(old_key)
            updated += 1

    if updated == 0:
        return

    try:
        write_manifest(manifest_path, files=manifest)
        print(f"Updated {updated} manifest key{'s' if updated != 1 else ''} for moved files.")
    except Exception as exc:
        print(f"Warning: Failed to update manifest: {exc}")

def _handle_duplicates(
    migration_map: MigrationResult,
    manifest: FilesDict,
    deluge_root: Path,
) -> MigrationResult:
    """Remove duplicate WAVs from SAMPLES and re-compute the migration map.

    For each group of identical files, keeps the first path and deletes the rest.
    Re-runs migration map computation so deleted duplicates are recovered
    via stale manifest entries during reference classification.

    Args:
        migration_map: Current migration result containing lib_duplicates.
        manifest: Current sync manifest.
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        Fresh :class:`MigrationResult` reflecting the de-duplicated library.
    """

    # Build deletion plan
    to_delete: list[tuple[str, str]] = []  # (keeper, dupe_to_delete)
    for _h, paths in migration_map.lib_duplicates.items():
        keeper = paths[0]
        for dupe in paths[1:]:
            to_delete.append((keeper, dupe))
    if not to_delete:
        return migration_map

    # Preview
    print(f"\nWanna delete some duplicates?\n")
    groups: dict[str, list[str]] = {}
    for keeper, dupe in to_delete:
        groups.setdefault(keeper, []).append(dupe)
    for keeper, dupes in groups.items():
        print(f"  **  KEEP   -- {keeper}")
        for dupe in dupes:
            print(f"      DELETE -- {dupe}")

    if not confirm_apply(f"\nDelete {len(to_delete)} file(s)?"):
        print("No duplicates removed.\n")
        return migration_map

    # Delete
    deleted_count = 0
    for _keeper, dupe in to_delete:
        abs_path = deluge_root / dupe
        try:
            abs_path.unlink()
            deleted_count += 1
        except OSError as exc:
            print(f"  Warning: could not delete {dupe}: {exc}")
    print()
    print(f"Deleted {deleted_count} duplicate file(s)")
    print()

    # Re-compute migration map with updated library state
    return _compute_migration_map(manifest, deluge_root)

# ===== MAIN =====

def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the reference fixer."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Fix sample references in Deluge XML files after reorganising samples.",
    )
    parser.parse_args(argv)

    deluge_root = get_deluge_root()
    manifest = read_manifest(SYNC_MANIFEST_PATH)

    migration_map = _compute_migration_map(manifest, deluge_root)
    if migration_map.lib_duplicates:
        migration_map = _handle_duplicates(migration_map, manifest, deluge_root)
    ref_classification_result = _classify_ref_changes(migration_map, deluge_root)
    apply_changes_confirmed = _preview_and_apply(ref_classification_result, deluge_root)

    if apply_changes_confirmed:
        if migration_map.moved:
            _update_manifest_keys(manifest, migration_map.moved, SYNC_MANIFEST_PATH)
        # Added samples (in library, not in manifest) are not handled here —
        # manifest population is the sync scripts' responsibility


if __name__ == "__main__":
    main()
