# Deluge CLI v0.1
"""Tests for deluge_lib.scanning."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest

from tests.conftest import _touch
from deluge_lib.scanning import FileEntry, ScanResult, normalise_key, scan_tree


# -- File-type filtering -----------------------------------------------------


class TestFileTypeFiltering:
    def test_mixed_files(self, tmp_path: Path) -> None:
        
        _touch(tmp_path / "good.xml")
        _touch(tmp_path / "good.wav")
        _touch(tmp_path / "bad.txt")
        _touch(tmp_path / ".DS_Store")

        result = scan_tree(tmp_path)

        assert len(result.files) == 2
        assert "good.xml" in result.files
        assert "good.wav" in result.files


# -- .trash exclusion --------------------------------------------------------


class TestTrashExclusion:
    def test_trash_directory_skipped(self, tmp_path: Path) -> None:
        
        _touch(tmp_path / ".trash" / "deleted.xml")
        _touch(tmp_path / "keep.xml")

        result = scan_tree(tmp_path)

        assert len(result.files) == 1
        assert "keep.xml" in result.files

    def test_trash_case_insensitive(self, tmp_path: Path) -> None:
        
        _touch(tmp_path / ".Trash" / "junk.wav")
        result = scan_tree(tmp_path)
        assert result.files == {}


# -- Stat capture ------------------------------------------------------------


class TestStatCapture:
    def test_rel_path_preserved(self, tmp_path: Path) -> None:
        
        _touch(tmp_path / "KITS" / "Deep.xml", b"abc")
        result = scan_tree(tmp_path)
        entry = result.files["kits/deep.xml"]
        assert entry.rel_path == Path("KITS") / "Deep.xml"


# -- Case-normalised keys ---------------------------------------------------


class TestCaseNormalisedKeys:
    def test_keys_are_lowercase(self, tmp_path: Path) -> None:
        
        _touch(tmp_path / "KITS" / "MyKit.XML")
        result = scan_tree(tmp_path)
        assert "kits/mykit.xml" in result.files


# -- normalise_key -----------------------------------------------------------


class TestNormaliseKey:
    def test_lowercase_conversion(self) -> None:
        
        assert normalise_key("KITS/MyKit.XML") == "kits/mykit.xml"

    def test_forward_slashes_from_path(self) -> None:
        
        assert normalise_key(Path("KITS") / "SubDir" / "Kit.XML") == "kits/subdir/kit.xml"

    def test_handles_path_object(self) -> None:
        
        assert normalise_key(Path("SYNTHS") / "Lead.XML") == "synths/lead.xml"

    def test_handles_already_normalised(self) -> None:
        
        assert normalise_key("samples/kick.wav") == "samples/kick.wav"

    def test_pure_posix_path_input(self) -> None:
        
        assert normalise_key(str(PurePosixPath("SONGS/My Song.XML"))) == "songs/my song.xml"

    def test_root_level_file(self) -> None:
        
        assert normalise_key("MIDIFollow.XML") == "midifollow.xml"


# -- file_filter parameter ----------------------------------------------------


class TestFileFilterParameter:
    def test_wav_only_scan(self, tmp_path: Path) -> None:
        
        _touch(tmp_path / "kick.wav")
        _touch(tmp_path / "preset.xml")
        _touch(tmp_path / "readme.txt")

        result = scan_tree(tmp_path, file_filter="wav")

        assert len(result.files) == 1
        assert "kick.wav" in result.files

    def test_xml_only_scan(self, tmp_path: Path) -> None:
        
        _touch(tmp_path / "kit.xml")
        _touch(tmp_path / "sample.wav")
        _touch(tmp_path / "notes.txt")

        result = scan_tree(tmp_path, file_filter="xml")

        assert len(result.files) == 1
        assert "kit.xml" in result.files

    def test_default_scan_unchanged(self, tmp_path: Path) -> None:
        
        _touch(tmp_path / "kit.xml")
        _touch(tmp_path / "sample.wav")
        _touch(tmp_path / "notes.txt")

        result = scan_tree(tmp_path)

        assert len(result.files) == 2
        assert "kit.xml" in result.files
        assert "sample.wav" in result.files

    def test_file_filter_case_insensitive_extension(self, tmp_path: Path) -> None:
        
        _touch(tmp_path / "sample.WAV")

        result = scan_tree(tmp_path, file_filter="wav")

        assert len(result.files) == 1


class TestCatalogueScanning:
    def test_all_filter_includes_audio_and_supporting_files(self, tmp_path: Path) -> None:
        names = {"kick.wav", "bell.AIFF", "short.aif", "README.txt", "other.bin"}
        for name in names:
            _touch(tmp_path / name)
        _touch(tmp_path / ".trash" / "deleted.wav")

        result = scan_tree(tmp_path, file_filter="all", strict=True)

        assert {entry.rel_path.name for entry in result.files.values()} == names

    def test_strict_scan_rejects_missing_directory(self, tmp_path: Path) -> None:
        with pytest.raises(NotADirectoryError, match="Scan directory"):
            scan_tree(tmp_path / "missing", file_filter="all", strict=True)

    def test_strict_scan_propagates_traversal_error(self, tmp_path: Path) -> None:
        def fail_walk(
            root: Path, *, onerror: Callable[[OSError], None]
        ) -> list[tuple[str, list[str], list[str]]]:
            onerror(PermissionError(f"cannot read {root}"))
            return []

        with (
            patch("deluge_lib.scanning.os.walk", side_effect=fail_walk),
            pytest.raises(PermissionError, match="cannot read"),
        ):
            scan_tree(tmp_path, file_filter="all", strict=True)

    @pytest.mark.parametrize("strict", [False, True])
    def test_stat_error_handling(self, tmp_path: Path, strict: bool) -> None:
        sample = tmp_path / "sample.wav"
        _touch(sample)
        original_stat = Path.stat

        def fail_sample_stat(
            path: Path, *, follow_symlinks: bool = True
        ) -> os.stat_result:
            if path == sample:
                raise PermissionError("cannot stat sample")
            return original_stat(path, follow_symlinks=follow_symlinks)

        with patch.object(Path, "stat", fail_sample_stat):
            if strict:
                with pytest.raises(PermissionError, match="cannot stat sample"):
                    scan_tree(tmp_path, file_filter="all", strict=True)
            else:
                assert scan_tree(tmp_path).files == {}

    def test_strict_scan_rejects_case_collisions(self, tmp_path: Path) -> None:
        _touch(tmp_path / "kick.wav")
        existing_stat = (tmp_path / "kick.wav").stat()
        original_stat = Path.stat

        def sample_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
            if path.name in {"kick.wav", "KICK.WAV"}:
                return existing_stat
            return original_stat(path, follow_symlinks=follow_symlinks)

        with (
            patch(
                "deluge_lib.scanning.os.walk",
                return_value=[(str(tmp_path), [], ["kick.wav", "KICK.WAV"])],
            ),
            patch.object(Path, "stat", sample_stat),
            pytest.raises(ValueError, match="Case-insensitive path collision"),
        ):
            scan_tree(tmp_path, file_filter="all", strict=True)
