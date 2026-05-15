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
    get_existing_samples,
    hash_file,
)
from deluge_lib.syncing import FilesDict, read_manifest, write_manifest
from deluge_lib.paths import SYNC_MANIFEST_PATH

@dataclass
class MigrationResult:
    """Result of comparing manifest state with the current filesystem.

    Attributes:
        moved: old_path → new_path for unambiguous moves (1:1 hash match,
            different paths).
        deleted: hash → list of old paths for samples present in the
            manifest but absent from the current filesystem.
        added: hash → list of new paths for samples present in the current
            filesystem but absent from the manifest.
        ambiguous: hash → (before_paths, after_paths) for hashes that map
            to multiple paths in either state.
    """

    moved: dict[str, str] = field(default_factory=dict)
    deleted: dict[str, list[str]] = field(default_factory=dict)
    added: dict[str, list[str]] = field(default_factory=dict)
    ambiguous: dict[str, tuple[list[str], list[str]]] = field(default_factory=dict)


def compute_migration_map(
    manifest: FilesDict,
    deluge_root: Path,
) -> MigrationResult:
    """Compare manifest state with the current filesystem to build a migration map.

    Uses the manifest as the "before" state (hash→paths) and the current
    filesystem as the "after" state.  The manifest's stat cache avoids
    re-hashing files that haven't moved.  Degrades gracefully when the
    manifest is empty or has no hashes.

    Keys in ``moved``, ``deleted``, and ``ambiguous`` before-paths are
    normalised (lowercase, forward-slash) to match manifest key format.
    After-paths use original case from the current filesystem.

    Args:
        manifest: Current sync manifest (may be empty for graceful degradation).
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        A :class:`MigrationResult` categorising every hash as moved, deleted,
        added, ambiguous, or unchanged (omitted).
    """
    # --- "before" state: invert manifest to hash → [normalised paths] ---
    before_hashes: dict[str, list[str]] = defaultdict(list)
    entries_with_hash = 0
    for path_key, record in manifest.items():
        h = record.get("hash")
        if h is not None:
            before_hashes[h].append(path_key)
            entries_with_hash += 1

    total_entries = len(manifest)
    if total_entries == 0:
        print("Manifest: empty or missing \u2014 move detection unavailable.")
    else:
        print(f"Manifest: {total_entries} entries ({entries_with_hash} with hashes).")
        if entries_with_hash == 0:
            print("Warning: No hashes in manifest \u2014 move detection unavailable.")

    # --- "after" state: scan current filesystem ---
    samples_dir = deluge_root / "SAMPLES"
    if not samples_dir.is_dir():
        return MigrationResult()

    scan = scan_tree(samples_dir, label="SAMPLES", file_filter="wav")

    after_hashes: dict[str, list[str]] = defaultdict(list)
    files_to_hash: list[tuple[str, Path]] = []

    for _scan_key, entry in scan.files.items():
        orig_path = str(PurePosixPath(Path("SAMPLES") / entry.rel_path))
        manifest_key = normalise_key(Path("SAMPLES") / entry.rel_path)
        abs_path = samples_dir / entry.rel_path

        # Check manifest stat cache
        manifest_entry = manifest.get(manifest_key)
        if manifest_entry is not None:
            cached_hash = manifest_entry.get("hash")
            if (
                cached_hash is not None
                and entry.mtime > 0
                and entry.size == manifest_entry["local_size"]
                and entry.mtime == manifest_entry["local_mtime"]
            ):
                # Stat-cache hit: trust cached hash without reading the file
                after_hashes[cached_hash].append(orig_path)
                continue

        files_to_hash.append((orig_path, abs_path))

    if files_to_hash:
        total = len(files_to_hash)
        for i, (orig_path, abs_path) in enumerate(files_to_hash, 1):
            if total > 10:
                print(f"\rHashing {i}/{total}...", end="", flush=True)
            after_hashes[hash_file(abs_path)].append(orig_path)
        if total > 10:
            print()

    # --- Compare before and after ---
    before_dict = dict(before_hashes)
    after_dict = dict(after_hashes)

    moved: dict[str, str] = {}
    deleted: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}
    ambiguous: dict[str, tuple[list[str], list[str]]] = {}

    for h in set(before_dict) | set(after_dict):
        bpaths = before_dict.get(h, [])
        apaths = after_dict.get(h, [])
        apaths_norm = [normalise_key(p) for p in apaths]

        if bpaths and not apaths:
            deleted[h] = list(bpaths)
        elif apaths and not bpaths:
            added[h] = list(apaths)
        elif len(bpaths) == 1 and len(apaths) == 1:
            if bpaths[0] != apaths_norm[0]:
                moved[bpaths[0]] = apaths[0]
            # else: unchanged — same hash, same normalised path
        else:
            ambiguous[h] = (list(bpaths), list(apaths))

    return MigrationResult(
        moved=moved,
        deleted=deleted,
        added=added,
        ambiguous=ambiguous,
    )


@dataclass
class PlannedChange:
    """A sample reference that can be automatically fixed via the migration map."""

    ref: SampleRef
    old_path: str
    new_path: str


@dataclass
class BrokenRefError:
    """A sample reference pointing to a deleted file — requires manual resolution."""

    ref: SampleRef
    deleted_path: str


@dataclass
class AmbiguousRefWarning:
    """A sample reference that cannot be auto-resolved due to ambiguous hash mapping."""

    ref: SampleRef
    ambiguous_path: str


@dataclass
class MissingRefError:
    """A sample reference that doesn't match any file on disk — wrong name or never existed."""

    ref: SampleRef
    missing_path: str


@dataclass
class BrokenRefResult:
    """Result of scanning XML references against a migration map.

    Attributes:
        changes: References that can be automatically updated (old → new path).
        errors: References pointing to deleted samples — user must resolve.
        warnings: References with ambiguous mappings — user must resolve.
    """

    changes: list[PlannedChange] = field(default_factory=list)
    errors: list[BrokenRefError] = field(default_factory=list)
    warnings: list[AmbiguousRefWarning] = field(default_factory=list)
    missing: list[MissingRefError] = field(default_factory=list)


def classify_ref_changes(
    migration: MigrationResult,
    deluge_root: Path,
) -> BrokenRefResult:
    """Scan all XML references and classify them against a migration map.

    For each sample reference found in KITS/, SYNTHS/, SONGS/ XMLs:
    - If the path is a key in ``migration.moved`` → planned change
    - If the path appears in any ``migration.deleted`` path list → error
    - If the path appears in any ``migration.ambiguous`` before-path list → warning
    - Otherwise (valid, unchanged) → not included in results

    Args:
        migration: Result from :func:`compute_migration_map`.
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        A :class:`BrokenRefResult` separating fixable changes, errors, and warnings.
    """
    # Build flat lookup sets for deleted and ambiguous paths
    deleted_paths: set[str] = set()
    for paths in migration.deleted.values():
        deleted_paths.update(paths)

    ambiguous_paths: set[str] = set()
    for before_paths, _after_paths in migration.ambiguous.values():
        ambiguous_paths.update(before_paths)

    existing = get_existing_samples(deluge_root)
    result = BrokenRefResult()

    xml_files = find_all_xml_files(deluge_root)
    for xml_path in xml_files:
        refs = extract_sample_refs(xml_path, deluge_root)
        for ref in refs:
            norm_ref = normalise_key(ref.path)
            if norm_ref in migration.moved:
                result.changes.append(
                    PlannedChange(
                        ref=ref,
                        old_path=ref.path,
                        new_path=migration.moved[norm_ref],
                    )
                )
            elif norm_ref in deleted_paths:
                result.errors.append(
                    BrokenRefError(ref=ref, deleted_path=ref.path)
                )
            elif norm_ref in ambiguous_paths:
                result.warnings.append(
                    AmbiguousRefWarning(ref=ref, ambiguous_path=ref.path)
                )
            elif norm_ref not in existing:
                result.missing.append(
                    MissingRefError(ref=ref, missing_path=ref.path)
                )

    return result


def update_sample_refs(xml_path: Path, mapping: dict[str, str]) -> int:
    """Update sample references in *xml_path* according to *mapping*.

    For each reference whose current path appears as a key in *mapping*, the
    value is written as the new path.  The file is only rewritten when at least
    one reference was changed.

    Returns the number of replacements made.
    """
    if not mapping:
        return 0

    data = xml_path.read_text(encoding="utf-8")
    count = 0

    for old_path, new_path in mapping.items():
        occurrences = data.count(old_path)
        if occurrences:
            data = data.replace(old_path, new_path)
            count += occurrences

    if count > 0:
        xml_path.write_text(data, encoding="utf-8")

    return count


def preview_and_apply(
    result: BrokenRefResult,
    deluge_root: Path,
    *,
    auto_apply: bool = False,
) -> tuple[bool, bool]:
    """Display planned changes, errors, and warnings, then optionally apply.

    Args:
        result: Output from :func:`classify_ref_changes`.
        deluge_root: Absolute path to the DELUGE directory.
        auto_apply: If True, skip the confirmation prompt and apply immediately.

    Returns:
        Tuple of ``(has_issues, applied)``.  *has_issues* is True when errors
        or missing refs were found.  *applied* is True when XML changes were
        actually written to disk.
    """
    # Nothing to do
    if not result.changes and not result.errors and not result.warnings and not result.missing:
        print("No broken references found. Nothing to do.")
        return (False, False)

    # Group changes by XML file
    changes_by_file: dict[Path, list[PlannedChange]] = defaultdict(list)
    for change in result.changes:
        changes_by_file[change.ref.xml_file].append(change)

    # --- Preview changes ---
    if changes_by_file:
        print("\nCHANGES")
        print("-------")
        for xml_file in sorted(changes_by_file):
            # Deduplicate same old→new pairs and count occurrences
            pair_counts: dict[tuple[str, str], int] = defaultdict(int)
            for change in changes_by_file[xml_file]:
                pair_counts[(change.old_path, change.new_path)] += 1
            for (old, new), count in pair_counts.items():
                suffix = f" (× {count} refs)" if count > 1 else ""
                print(f'  {print_path(xml_file)}: "{old}" → "{new}"{suffix}')

    # --- Errors ---
    if result.errors:
        print()
        print("ERRORS \u2014 Requires Manual Resolution")
        print("------------------------------------")
        for error in result.errors:
            print(f"  {print_path(error.ref.xml_file)}: \"{error.deleted_path}\" \u2014 sample deleted")

    # --- Warnings ---
    if result.warnings:
        print()
        print("WARNINGS \u2014 Ambiguous Mappings")
        print("-----------------------------")
        for warning in result.warnings:
            print(
                f"  {print_path(warning.ref.xml_file)}: \"{warning.ambiguous_path}\""
                " \u2014 multiple files share this hash"
            )

    # --- Missing ---
    if result.missing:
        print()
        print("MISSING \u2014 Sample Path Not Found")
        print("--------------------------------")
        for miss in result.missing:
            print(
                f"  {print_path(miss.ref.xml_file)}: \"{miss.missing_path}\""
                " \u2014 no matching file on disk"
            )

    # --- Summary ---
    n_changes = len(result.changes)
    n_files = len(changes_by_file)
    n_errors = len(result.errors)
    n_warnings = len(result.warnings)
    n_missing = len(result.missing)
    print()
    print(f"{n_changes} changes across {n_files} files. {n_errors} errors, {n_warnings} warnings, {n_missing} missing.")

    if result.errors:
        print("WARNING: Resolve errors before applying to avoid broken references.")

    has_issues = bool(result.errors) or bool(result.missing)

    # Nothing to apply
    if not result.changes:
        return (has_issues, False)

    # --- Confirm ---
    if not auto_apply and not confirm_apply(f"Apply {n_changes} changes to {n_files} files?"):
        print("No changes applied.")
        return (has_issues, False)

    # --- Apply ---
    # Build per-file mappings and apply
    total_updated = 0
    files_modified = 0
    for xml_file in sorted(changes_by_file):
        mapping: dict[str, str] = {}
        for change in changes_by_file[xml_file]:
            mapping[change.old_path] = change.new_path
        updated = update_sample_refs(deluge_root / xml_file, mapping)
        if updated > 0:
            files_modified += 1
            total_updated += updated

    print(f"Applied: {files_modified} files modified, {total_updated} references updated.")

    return (has_issues, True)


def update_manifest_keys(
    manifest: FilesDict,
    moved: dict[str, str],
    manifest_path: Path,
) -> None:
    """Rename manifest keys for moved files and write the updated manifest.

    For each entry in *moved* (normalised_old_key → original_new_path),
    renames the manifest key to the normalised new path, preserving hash
    and stat data.  Write failures produce a warning rather than an error.
    """
    if not moved:
        return

    updated = 0
    for old_key, new_orig_path in moved.items():
        new_key = normalise_key(new_orig_path)
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


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the reference fixer."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix sample references in Deluge XML files after reorganising samples.",
    )
    parser.add_argument(
        "--manifest",
        required=False,
        dest="manifest_path",
        help="Path to the sync manifest JSON file. Defaults to the standard sync manifest.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes without prompting for confirmation.",
    )

    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest_path) if args.manifest_path else SYNC_MANIFEST_PATH
    deluge_root = get_deluge_root()

    manifest = read_manifest(manifest_path)
    migration = compute_migration_map(manifest, deluge_root)
    broken = classify_ref_changes(migration, deluge_root)
    has_issues, applied = preview_and_apply(broken, deluge_root, auto_apply=args.apply)

    if applied and migration.moved:
        update_manifest_keys(manifest, migration.moved, manifest_path)

    if has_issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
