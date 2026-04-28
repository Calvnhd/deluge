# Deluge CLI v0.1
"""Tests for deluge_lib.analysis."""

from __future__ import annotations

from pathlib import Path

from deluge_lib.analysis import (
    FolderStats,
    LibrarySummary,
    build_usage_index,
    compute_folder_breakdown,
    compute_summary,
    filter_by_pattern,
    top_by_refs,
    top_by_size,
)
from deluge_lib.deluge_sdk import SampleRef
from deluge_lib.scanning import FileEntry, ScanResult

# ---------------------------------------------------------------------------
# Helpers — synthetic test data
# ---------------------------------------------------------------------------


def _file_entry(rel: str, size: int = 100) -> FileEntry:
    # TODO-v0.1-REVIEW
    """Create a FileEntry with defaults for testing."""
    return FileEntry(rel_path=Path(rel), size=size, mtime=0.0)


def _sample_ref(path: str, xml_file: str = "KITS/Kit.XML", preset: str = "Kit") -> SampleRef:
    # TODO-v0.1-REVIEW
    """Create a SampleRef with defaults for testing."""
    return SampleRef(
        path=path,
        xml_file=Path(xml_file),
        xml_type="kit",
        preset_name=preset,
        ref_type="fileName-element",
        element_tag="osc1",
    )


def _scan_result(entries: dict[str, FileEntry]) -> ScanResult:
    # TODO-v0.1-REVIEW
    """Wrap a dict of normalised-key → FileEntry into a ScanResult."""
    result = ScanResult()
    result.files = entries
    return result


# ---------------------------------------------------------------------------
# build_usage_index
# ---------------------------------------------------------------------------


class TestBuildUsageIndex:
    def test_sample_on_disk_and_referenced(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({"drums/kick/808.wav": _file_entry("DRUMS/Kick/808.wav", 5000)})
        refs = [_sample_ref("SAMPLES/DRUMS/Kick/808.wav")]

        index = build_usage_index(refs, scan)

        assert "drums/kick/808.wav" in index.entries
        usage = index.entries["drums/kick/808.wav"]
        assert usage.on_disk is True
        assert usage.size == 5000
        assert usage.ref_count == 1
        assert usage.refs[0].path == "SAMPLES/DRUMS/Kick/808.wav"

    def test_sample_on_disk_unreferenced(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({"drums/snare/rim.wav": _file_entry("DRUMS/Snare/rim.wav", 2000)})

        index = build_usage_index([], scan)

        usage = index.entries["drums/snare/rim.wav"]
        assert usage.on_disk is True
        assert usage.ref_count == 0
        assert usage.size == 2000

    def test_sample_referenced_but_missing(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({})
        refs = [_sample_ref("SAMPLES/DRUMS/Kick/missing.wav")]

        index = build_usage_index(refs, scan)

        usage = index.entries["drums/kick/missing.wav"]
        assert usage.on_disk is False
        assert usage.size is None
        assert usage.ref_count == 1
        assert usage.path == "DRUMS/Kick/missing.wav"

    def test_case_insensitive_matching(self) -> None:
        # TODO-v0.1-REVIEW
        """SampleRef with different casing should match the on-disk entry."""
        scan = _scan_result({"drums/kick/808.wav": _file_entry("DRUMS/Kick/808.wav", 3000)})
        refs = [_sample_ref("SAMPLES/drums/KICK/808.WAV")]

        index = build_usage_index(refs, scan)

        # Should match the existing on-disk entry, not create a missing entry.
        assert len(index.entries) == 1
        usage = index.entries["drums/kick/808.wav"]
        assert usage.on_disk is True
        assert usage.ref_count == 1

    def test_multiple_refs_to_same_sample(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({"drums/kick/808.wav": _file_entry("DRUMS/Kick/808.wav")})
        refs = [
            _sample_ref("SAMPLES/DRUMS/Kick/808.wav", xml_file="KITS/Kit1.XML", preset="Kit1"),
            _sample_ref("SAMPLES/DRUMS/Kick/808.wav", xml_file="SONGS/Song1.XML", preset="Song1"),
        ]

        index = build_usage_index(refs, scan)

        usage = index.entries["drums/kick/808.wav"]
        assert usage.ref_count == 2

    def test_convenience_properties(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({
            "drums/kick/808.wav": _file_entry("DRUMS/Kick/808.wav"),
            "drums/snare/rim.wav": _file_entry("DRUMS/Snare/rim.wav"),
        })
        refs = [
            _sample_ref("SAMPLES/DRUMS/Kick/808.wav"),
            _sample_ref("SAMPLES/SYNTHS/Lead/missing.wav"),
        ]

        index = build_usage_index(refs, scan)

        assert len(index.referenced) == 1
        assert "drums/kick/808.wav" in index.referenced

        assert len(index.unreferenced) == 1
        assert "drums/snare/rim.wav" in index.unreferenced

        assert len(index.missing) == 1
        assert "synths/lead/missing.wav" in index.missing

    def test_missing_sample_strips_samples_prefix(self) -> None:
        # TODO-v0.1-REVIEW
        """Display path for missing samples should not include SAMPLES/ prefix."""
        scan = _scan_result({})
        refs = [_sample_ref("SAMPLES/Artists/SomeArtist/loop.wav")]

        index = build_usage_index(refs, scan)

        usage = index.entries["artists/someartist/loop.wav"]
        assert usage.path == "Artists/SomeArtist/loop.wav"


# ---------------------------------------------------------------------------
# compute_summary
# ---------------------------------------------------------------------------


class TestComputeSummary:
    def test_summary_counts_and_sizes(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({
            "drums/kick/808.wav": _file_entry("DRUMS/Kick/808.wav", 5000),
            "drums/snare/rim.wav": _file_entry("DRUMS/Snare/rim.wav", 3000),
            "clips/recording.wav": _file_entry("CLIPS/recording.wav", 10000),
        })
        refs = [
            _sample_ref("SAMPLES/DRUMS/Kick/808.wav"),
            _sample_ref("SAMPLES/MISSING/gone.wav"),
        ]

        index = build_usage_index(refs, scan)
        summary = compute_summary(index)

        assert summary.on_disk_count == 3
        assert summary.on_disk_size == 18000
        assert summary.referenced_count == 1
        assert summary.referenced_size == 5000
        assert summary.unreferenced_count == 2
        assert summary.unreferenced_size == 13000
        assert summary.missing_count == 1

    def test_empty_library(self) -> None:
        # TODO-v0.1-REVIEW
        index = build_usage_index([], _scan_result({}))
        summary = compute_summary(index)

        assert summary == LibrarySummary(0, 0, 0, 0, 0, 0, 0)


# ---------------------------------------------------------------------------
# compute_folder_breakdown
# ---------------------------------------------------------------------------


class TestComputeFolderBreakdown:
    def test_groups_by_top_level_folder(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({
            "drums/kick/808.wav": _file_entry("DRUMS/Kick/808.wav", 1000),
            "drums/snare/rim.wav": _file_entry("DRUMS/Snare/rim.wav", 2000),
            "clips/recording.wav": _file_entry("CLIPS/recording.wav", 5000),
        })

        index = build_usage_index([], scan)
        breakdown = compute_folder_breakdown(index)

        assert len(breakdown) == 2
        clips = next(fs for fs in breakdown if fs.folder == "CLIPS")
        drums = next(fs for fs in breakdown if fs.folder == "DRUMS")
        assert clips == FolderStats(folder="CLIPS", file_count=1, total_size=5000)
        assert drums == FolderStats(folder="DRUMS", file_count=2, total_size=3000)

    def test_missing_samples_excluded(self) -> None:
        # TODO-v0.1-REVIEW
        """Missing samples have no size and should not appear in folder breakdown."""
        scan = _scan_result({})
        refs = [_sample_ref("SAMPLES/DRUMS/Kick/missing.wav")]

        index = build_usage_index(refs, scan)
        breakdown = compute_folder_breakdown(index)

        assert breakdown == []

    def test_sorted_by_folder_name(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({
            "z_folder/a.wav": _file_entry("Z_Folder/a.wav", 100),
            "a_folder/b.wav": _file_entry("A_Folder/b.wav", 200),
        })

        index = build_usage_index([], scan)
        breakdown = compute_folder_breakdown(index)

        assert breakdown[0].folder == "A_Folder"
        assert breakdown[1].folder == "Z_Folder"

    def test_root_level_files(self) -> None:
        # TODO-v0.1-REVIEW
        """Files directly under SAMPLES/ (no subfolder) get empty-string folder."""
        scan = _scan_result({
            "loose.wav": _file_entry("loose.wav", 500),
        })

        index = build_usage_index([], scan)
        breakdown = compute_folder_breakdown(index)

        assert len(breakdown) == 1
        assert breakdown[0].folder == ""
        assert breakdown[0].file_count == 1


# ---------------------------------------------------------------------------
# top_by_refs
# ---------------------------------------------------------------------------


class TestTopByRefs:
    def test_returns_top_n(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({
            "a.wav": _file_entry("a.wav"),
            "b.wav": _file_entry("b.wav"),
            "c.wav": _file_entry("c.wav"),
        })
        refs = [
            _sample_ref("SAMPLES/a.wav", xml_file="KITS/K1.XML", preset="K1"),
            _sample_ref("SAMPLES/b.wav", xml_file="KITS/K1.XML", preset="K1"),
            _sample_ref("SAMPLES/b.wav", xml_file="KITS/K2.XML", preset="K2"),
            _sample_ref("SAMPLES/c.wav", xml_file="KITS/K1.XML", preset="K1"),
            _sample_ref("SAMPLES/c.wav", xml_file="KITS/K2.XML", preset="K2"),
            _sample_ref("SAMPLES/c.wav", xml_file="SONGS/S1.XML", preset="S1"),
        ]

        index = build_usage_index(refs, scan)
        top = top_by_refs(index, 2)

        assert len(top) == 2
        assert top[0].ref_count == 3  # c.wav
        assert top[1].ref_count == 2  # b.wav

    def test_excludes_unreferenced(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({"a.wav": _file_entry("a.wav")})
        index = build_usage_index([], scan)

        assert top_by_refs(index, 5) == []


# ---------------------------------------------------------------------------
# top_by_size
# ---------------------------------------------------------------------------


class TestTopBySize:
    def test_returns_top_n_largest(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({
            "small.wav": _file_entry("small.wav", 100),
            "medium.wav": _file_entry("medium.wav", 5000),
            "large.wav": _file_entry("large.wav", 50000),
        })

        index = build_usage_index([], scan)
        top = top_by_size(index, 2)

        assert len(top) == 2
        assert top[0].size == 50000
        assert top[1].size == 5000

    def test_excludes_missing(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({})
        refs = [_sample_ref("SAMPLES/gone.wav")]

        index = build_usage_index(refs, scan)

        assert top_by_size(index, 5) == []


# ---------------------------------------------------------------------------
# filter_by_pattern
# ---------------------------------------------------------------------------


class TestFilterByPattern:
    def test_case_insensitive_match(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({
            "drums/kick/808.wav": _file_entry("DRUMS/Kick/808.wav"),
            "drums/snare/rim.wav": _file_entry("DRUMS/Snare/rim.wav"),
        })
        index = build_usage_index([], scan)

        result = filter_by_pattern(index, "kick")
        assert len(result) == 1
        assert result[0].path == "DRUMS/Kick/808.wav"

    def test_matches_on_full_path(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({
            "drums/kick/808.wav": _file_entry("DRUMS/Kick/808.wav"),
        })
        index = build_usage_index([], scan)

        result = filter_by_pattern(index, "DRUMS/Kick")
        assert len(result) == 1

    def test_no_matches(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({"drums/kick/808.wav": _file_entry("DRUMS/Kick/808.wav")})
        index = build_usage_index([], scan)

        assert filter_by_pattern(index, "nonexistent") == []

    def test_includes_missing_samples(self) -> None:
        # TODO-v0.1-REVIEW
        scan = _scan_result({})
        refs = [_sample_ref("SAMPLES/DRUMS/Kick/missing.wav")]

        index = build_usage_index(refs, scan)

        result = filter_by_pattern(index, "kick")
        assert len(result) == 1
        assert result[0].on_disk is False
