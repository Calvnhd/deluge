# Deluge CLI v0.2
"""Sample library analysis — cross-reference XML refs against disk state.

This module receives pre-collected data (sample references and scan results)
and produces structured analysis results.  It performs no filesystem or XML
access itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deluge_lib.deluge_sdk import SampleRef
from deluge_lib.scanning import ScanResult, normalise_key, print_path


@dataclass
class SampleUsage:
    """Per-sample usage record."""

    # Path (for output display) relative to SAMPLES/
    path: str
    # File size in bytes; None when the sample is missing
    size: int | None
    # Every SampleRef that points to this sample.
    refs: list[SampleRef] = field(default_factory=list)
    # Whether the sample exists on disk.
    on_disk: bool = True

    @property
    def ref_count(self) -> int:
        return len(self.refs)


@dataclass(frozen=True)
class FolderStats:
    """Per-folder breakdown (top-level folder under SAMPLES/)."""

    folder: str
    file_count: int
    total_size: int


@dataclass(frozen=True)
class LibrarySummary:
    """Library-wide aggregate statistics."""

    on_disk_count: int
    on_disk_size: int
    referenced_count: int
    referenced_size: int
    unreferenced_count: int
    unreferenced_size: int
    missing_count: int


@dataclass
class UsageIndex:
    """Complete cross-reference of samples on disk and in XML.

    Attributes:
        entries: All known samples.
            k: normalised path (lowercase, forward-slash) relative to SAMPLES/, v: SampleUsage
    """

    entries: dict[str, SampleUsage] = field(default_factory=dict)

    @property
    def referenced(self) -> dict[str, SampleUsage]:
        """Samples that exist on disk AND are referenced by at least one XML."""
        return {k: v for k, v in self.entries.items() if v.on_disk and v.ref_count > 0}

    @property
    def unreferenced(self) -> dict[str, SampleUsage]:
        """Samples that exist on disk but are NOT referenced by any XML."""
        return {k: v for k, v in self.entries.items() if v.on_disk and v.ref_count == 0}

    @property
    def missing(self) -> dict[str, SampleUsage]:
        """Samples referenced in XML but not found on disk."""
        return {k: v for k, v in self.entries.items() if not v.on_disk}


def _ref_key(ref_path: str) -> str:
    """Normalise a SampleRef path to match ScanResult keys.

    SampleRef.path is relative to DELUGE/ (e.g. "SAMPLES/DRUMS/Kick/808.wav").
    ScanResult keys are normalised relative to SAMPLES/ (e.g. "drums/kick/808.wav").
    """
    key = normalise_key(ref_path)
    if key.startswith("samples/"):
        key = key[len("samples/") :]
    return key


def top_folder(path: str) -> str:
    """Extract the first path component (top-level folder under SAMPLES/).

    >>> top_folder("DRUMS/Kick/808.wav")
    'DRUMS'
    >>> top_folder("single.wav")
    ''
    """
    slash = path.find("/")
    if slash == -1:
        return ""
    return path[:slash]


def build_usage_index(
    refs: list[SampleRef],
    sample_scan: ScanResult,
) -> UsageIndex:
    """Cross-reference XML sample refs against a SAMPLES/ disk scan.

    Args:
        refs: All sample references extracted from Deluge XMLs.
        sample_scan: Result of ``scan_tree()`` run on the SAMPLES/ directory.

    Returns:
        UsageIndex covering every known sample — on disk, in XML, or both.
    """
    entries: dict[str, SampleUsage] = {}

    # 1. Seed the index with every file found on disk.
    for norm_key, file_entry in sample_scan.files.items():
        entries[norm_key] = SampleUsage(
            path=print_path(file_entry.rel_path),
            size=file_entry.size,
            refs=[],
            on_disk=True,
        )

    # 2. Walk each XML reference and attach it to the matching entry.
    for ref in refs:
        key = _ref_key(ref.path)
        if key in entries:
            entries[key].refs.append(ref)
        else:
            # Sample referenced in XML but missing from disk.
            # Strip SAMPLES/ prefix for display path, preserving original case.
            display = ref.path
            upper_prefix = "SAMPLES/"
            if display.upper().startswith(upper_prefix):
                display = display[len(upper_prefix) :]
            entries[key] = SampleUsage(
                path=display,
                size=None,
                refs=[ref],
                on_disk=False,
            )

    return UsageIndex(entries=entries)


def compute_summary(index: UsageIndex) -> LibrarySummary:
    """Compute library-wide aggregate statistics from a usage index."""
    on_disk_count = 0
    on_disk_size = 0
    referenced_count = 0
    referenced_size = 0
    unreferenced_count = 0
    unreferenced_size = 0
    missing_count = 0

    for usage in index.entries.values():
        if usage.on_disk:
            on_disk_count += 1
            on_disk_size += usage.size or 0
            if usage.ref_count > 0:
                referenced_count += 1
                referenced_size += usage.size or 0
            else:
                unreferenced_count += 1
                unreferenced_size += usage.size or 0
        else:
            missing_count += 1

    return LibrarySummary(
        on_disk_count=on_disk_count,
        on_disk_size=on_disk_size,
        referenced_count=referenced_count,
        referenced_size=referenced_size,
        unreferenced_count=unreferenced_count,
        unreferenced_size=unreferenced_size,
        missing_count=missing_count,
    )


def compute_folder_breakdown(index: UsageIndex) -> list[FolderStats]:
    """Group on-disk samples by top-level folder under SAMPLES/.

    Returns a list of ``FolderStats`` sorted by folder name.
    """
    folders: dict[str, tuple[int, int]] = {}  # folder → (count, size)

    for usage in index.entries.values():
        if not usage.on_disk:
            continue
        folder = top_folder(usage.path)
        count, size = folders.get(folder, (0, 0))
        folders[folder] = (count + 1, size + (usage.size or 0))

    return sorted(
        (FolderStats(folder=f, file_count=c, total_size=s) for f, (c, s) in folders.items()),
        key=lambda fs: fs.folder,
    )


def top_by_refs(index: UsageIndex, n: int) -> list[SampleUsage]:
    """Return the *n* most-referenced samples currently on-disk, sorted by reference count descending."""
    return sorted(
        (u for u in index.entries.values() if u.ref_count > 0 and u.on_disk),
        key=lambda u: u.ref_count,
        reverse=True,
    )[:n]


def filter_by_pattern(index: UsageIndex, term: str) -> list[SampleUsage]:
    """Return samples whose path contains *term* (case-insensitive substring match)."""
    needle = term.lower()
    return [u for u in index.entries.values() if needle in u.path.lower()]
