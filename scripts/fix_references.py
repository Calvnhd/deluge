"""Fix sample references in Deluge XML files after reorganising samples."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree

from deluge_lib.cli_utils import confirm_apply, get_deluge_root
from deluge_lib.scanning import normalise_key, print_path
from deluge_lib.deluge_sdk import (
    SampleRef,
    default_manifests_dir,
    extract_sample_refs,
    find_all_xml_files,
    get_existing_samples,
    hash_all_samples,
)

@dataclass
class MigrationResult:
    """Result of comparing a before-snapshot with the current filesystem state.

    Attributes:
        moved: old_path → new_path for unambiguous moves (1:1 hash match,
            different paths).
        deleted: hash → list of old paths for samples present in the
            before-snapshot but absent from the current filesystem.
        added: hash → list of new paths for samples present in the current
            filesystem but absent from the before-snapshot.
        ambiguous: hash → (before_paths, after_paths) for hashes that map
            to multiple paths in either state.
    """

    moved: dict[str, str] = field(default_factory=dict)
    deleted: dict[str, list[str]] = field(default_factory=dict)
    added: dict[str, list[str]] = field(default_factory=dict)
    ambiguous: dict[str, tuple[list[str], list[str]]] = field(default_factory=dict)


def compute_migration_map(
    before_snapshot: dict[str, Any],
    deluge_root: Path,
) -> MigrationResult:
    """Compare a before-snapshot with the current filesystem to build a migration map.

    Args:
        before_snapshot: Parsed JSON snapshot produced by the ``snapshot``
            subcommand.  Must contain a ``"hashes"`` key mapping SHA-256 hex
            digests to lists of paths relative to *deluge_root*.
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        A :class:`MigrationResult` categorising every hash as moved, deleted,
        added, ambiguous, or unchanged (omitted).
    """
    before_hashes: dict[str, list[str]] = before_snapshot["hashes"]

    # Build "after" state by hashing current samples
    after_hashes: dict[str, list[str]] = defaultdict(list)
    for digest, paths in hash_all_samples(deluge_root).items():
        after_hashes[digest].extend(paths)

    moved: dict[str, str] = {}
    deleted: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}
    ambiguous: dict[str, tuple[list[str], list[str]]] = {}

    all_hashes = set(before_hashes) | set(after_hashes)

    for h in all_hashes:
        before_paths = before_hashes.get(h, [])
        after_paths = after_hashes.get(h, [])

        if before_paths and not after_paths:
            deleted[h] = list(before_paths)
        elif after_paths and not before_paths:
            added[h] = list(after_paths)
        elif len(before_paths) == 1 and len(after_paths) == 1:
            if before_paths[0] != after_paths[0]:
                moved[before_paths[0]] = after_paths[0]
            # else: unchanged — same hash, same path — nothing to do
        else:
            ambiguous[h] = (list(before_paths), list(after_paths))

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
            if ref.path in migration.moved:
                result.changes.append(
                    PlannedChange(
                        ref=ref,
                        old_path=ref.path,
                        new_path=migration.moved[ref.path],
                    )
                )
            elif ref.path in deleted_paths:
                result.errors.append(
                    BrokenRefError(ref=ref, deleted_path=ref.path)
                )
            elif ref.path in ambiguous_paths:
                result.warnings.append(
                    AmbiguousRefWarning(ref=ref, ambiguous_path=ref.path)
                )
            elif normalise_key(ref.path) not in existing:
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
) -> bool:
    """Display planned changes, errors, and warnings, then optionally apply.

    Args:
        result: Output from :func:`classify_ref_changes`.
        deluge_root: Absolute path to the DELUGE directory.
        auto_apply: If True, skip the confirmation prompt and apply immediately.

    Returns:
        True if errors (deleted references) were found, False otherwise.
    """
    # Nothing to do
    if not result.changes and not result.errors and not result.warnings and not result.missing:
        print("No broken references found. Nothing to do.")
        return False

    # Group changes by XML file
    changes_by_file: dict[Path, list[PlannedChange]] = defaultdict(list)
    for change in result.changes:
        changes_by_file[change.ref.xml_file].append(change)

    # --- Preview changes ---
    if changes_by_file:
        print("CHANGES")
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
        print("ERRORS — Requires Manual Resolution")
        print("------------------------------------")
        for error in result.errors:
            print(f"  {print_path(error.ref.xml_file)}: \"{error.deleted_path}\" — sample deleted")

    # --- Warnings ---
    if result.warnings:
        print()
        print("WARNINGS — Ambiguous Mappings")
        print("-----------------------------")
        for warning in result.warnings:
            print(
                f"  {print_path(warning.ref.xml_file)}: \"{warning.ambiguous_path}\""
                " — multiple files share this hash"
            )

    # --- Missing ---
    if result.missing:
        print()
        print("MISSING — Sample Path Not Found")
        print("--------------------------------")
        for miss in result.missing:
            print(
                f"  {print_path(miss.ref.xml_file)}: \"{miss.missing_path}\""
                " — no matching file on disk"
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

    # Nothing to apply
    if not result.changes:
        return bool(result.errors) or bool(result.missing)

    # --- Confirm ---
    if not auto_apply and not confirm_apply(f"Apply {n_changes} changes to {n_files} files?"):
        print("No changes applied.")
        return bool(result.errors) or bool(result.missing)

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

    return bool(result.errors) or bool(result.missing)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the reference fixer."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix sample references in Deluge XML files after reorganising samples.",
    )
    parser.add_argument(
        "--snapshot",
        required=False,
        dest="snapshot_path",
        help="Path to the before-snapshot JSON file. Defaults to the most recent snapshot.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes without prompting for confirmation.",
    )

    args = parser.parse_args(argv)

    if args.snapshot_path:
        snapshot_path = Path(args.snapshot_path)
    else:
        manifests_dir = default_manifests_dir()
        snapshots = sorted(manifests_dir.glob("snapshot-*.json"))
        if not snapshots:
            raise SystemExit(f"No snapshots found in {manifests_dir}")
        snapshot_path = snapshots[-1]
        print(f"Using latest snapshot: {snapshot_path.name}")
    if not snapshot_path.is_file():
        raise SystemExit(f"Snapshot file not found: {snapshot_path}")
    deluge_root = get_deluge_root()
    before_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    migration = compute_migration_map(before_snapshot, deluge_root)
    broken = classify_ref_changes(migration, deluge_root)
    has_errors = preview_and_apply(broken, deluge_root, auto_apply=args.apply)
    if has_errors:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
