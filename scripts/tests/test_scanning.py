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
    def test_xml_and_wav_included(self, tmp_path: Path) -> None:
        _touch(tmp_path / "kit.xml")
        _touch(tmp_path / "kick.wav")

        result = scan_tree(tmp_path, progress=False)

        assert "kit.xml" in result.files
        assert "kick.wav" in result.files

    def test_ds_store_excluded(self, tmp_path: Path) -> None:
        _touch(tmp_path / ".DS_Store")
        result = scan_tree(tmp_path, progress=False)
        assert result.files == {}

    def test_txt_excluded(self, tmp_path: Path) -> None:
        _touch(tmp_path / "readme.txt")
        result = scan_tree(tmp_path, progress=False)
        assert result.files == {}

    def test_thumbs_db_excluded(self, tmp_path: Path) -> None:
        _touch(tmp_path / "Thumbs.db")
        result = scan_tree(tmp_path, progress=False)
        assert result.files == {}

    def test_mixed_files(self, tmp_path: Path) -> None:
        _touch(tmp_path / "good.xml")
        _touch(tmp_path / "good.wav")
        _touch(tmp_path / "bad.txt")
        _touch(tmp_path / ".DS_Store")

        result = scan_tree(tmp_path, progress=False)

        assert len(result.files) == 2
        assert "good.xml" in result.files
        assert "good.wav" in result.files


# -- Root-level files --------------------------------------------------------


class TestRootLevelFiles:
    def test_root_level_file_included(self, tmp_path: Path) -> None:
        _touch(tmp_path / "MIDIFollow.XML")
        result = scan_tree(tmp_path, progress=False)
        assert "midifollow.xml" in result.files

    def test_nested_and_root_files(self, tmp_path: Path) -> None:
        _touch(tmp_path / "Root.xml")
        _touch(tmp_path / "KITS" / "Kit.xml")

        result = scan_tree(tmp_path, progress=False)

        assert "root.xml" in result.files
        assert "kits/kit.xml" in result.files


# -- .trash exclusion --------------------------------------------------------


class TestTrashExclusion:
    def test_trash_directory_skipped(self, tmp_path: Path) -> None:
        _touch(tmp_path / ".trash" / "deleted.xml")
        _touch(tmp_path / "keep.xml")

        result = scan_tree(tmp_path, progress=False)

        assert len(result.files) == 1
        assert "keep.xml" in result.files

    def test_trash_case_insensitive(self, tmp_path: Path) -> None:
        _touch(tmp_path / ".Trash" / "junk.wav")
        result = scan_tree(tmp_path, progress=False)
        assert result.files == {}


# -- Symlinks ----------------------------------------------------------------


class TestSymlinks:
    def test_symlinked_file_skipped(self, tmp_path: Path) -> None:
        real = tmp_path / "real.xml"
        _touch(real)
        link = tmp_path / "link.xml"
        link.symlink_to(real)

        result = scan_tree(tmp_path, progress=False)

        assert "real.xml" in result.files
        assert "link.xml" not in result.files

    def test_symlinked_dir_skipped(self, tmp_path: Path) -> None:
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        _touch(real_dir / "inside.xml")
        link_dir = tmp_path / "link_dir"
        link_dir.symlink_to(real_dir)

        result = scan_tree(tmp_path, progress=False)

        # Files inside the real dir are found, but the symlinked dir is not traversed.
        assert "real_dir/inside.xml" in result.files
        assert "link_dir/inside.xml" not in result.files


# -- Stat capture ------------------------------------------------------------


class TestStatCapture:
    def test_returns_size_and_mtime(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xml"
        f.write_bytes(b"hello")

        result = scan_tree(tmp_path, progress=False)
        entry = result.files["test.xml"]

        assert isinstance(entry, FileEntry)
        assert entry.size == 5
        assert isinstance(entry.mtime, float)
        assert entry.mtime > 0

    def test_rel_path_preserved(self, tmp_path: Path) -> None:
        _touch(tmp_path / "KITS" / "Deep.xml", b"abc")
        result = scan_tree(tmp_path, progress=False)
        entry = result.files["kits/deep.xml"]
        assert entry.rel_path == Path("KITS") / "Deep.xml"


# -- Generic root path ------------------------------------------------------


class TestGenericRootPath:
    def test_works_on_arbitrary_directory(self, tmp_path: Path) -> None:
        custom = tmp_path / "my_custom_dir"
        custom.mkdir()
        _touch(custom / "song.xml")

        result = scan_tree(custom, progress=False)

        assert "song.xml" in result.files

    def test_scan_result_type(self, tmp_path: Path) -> None:
        result = scan_tree(tmp_path, progress=False)
        assert isinstance(result, ScanResult)


# -- Case-normalised keys ---------------------------------------------------


class TestCaseNormalisedKeys:
    def test_keys_are_lowercase(self, tmp_path: Path) -> None:
        _touch(tmp_path / "KITS" / "MyKit.XML")
        result = scan_tree(tmp_path, progress=False)
        assert "kits/mykit.xml" in result.files

    def test_original_casing_in_rel_path(self, tmp_path: Path) -> None:
        _touch(tmp_path / "SYNTHS" / "BassLead.XML")
        result = scan_tree(tmp_path, progress=False)
        entry = result.files["synths/basslead.xml"]
        assert entry.rel_path == Path("SYNTHS") / "BassLead.XML"


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
