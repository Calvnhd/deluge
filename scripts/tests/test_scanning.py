"""Tests for deluge_lib.scanning."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from deluge_lib.scanning import FileEntry, ScanResult, normalise_key, scan_tree


def _touch(path: Path, content: bytes = b"x") -> None:
    """Create a tiny file with some content so it has non-zero size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


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
