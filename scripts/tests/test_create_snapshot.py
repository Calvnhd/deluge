# Deluge CLI v0.1
"""Tests for create_snapshot.py."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from create_snapshot import snapshot

from deluge_lib.deluge_sdk import hash_file


def _make_deluge_tree(tmp_path: Path, wav_files: dict[str, bytes]) -> Path:
    # TODO-v0.1-REVIEW
    """Helper: create a DELUGE/SAMPLES/ tree with given WAV files."""
    deluge_root = tmp_path / "DELUGE"
    samples = deluge_root / "SAMPLES"
    for rel_path, content in wav_files.items():
        full = samples / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
    return deluge_root


class TestHashFile:
    """Tests for the hash_file function."""

    def test_correct_sha256(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        """hash_file returns the correct SHA256 hex digest for known content."""
        f = tmp_path / "test.wav"
        content = b"known content for hashing"
        f.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()

        assert hash_file(f) == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        """hash_file handles an empty file (SHA256 of empty bytes)."""
        f = tmp_path / "empty.wav"
        f.write_bytes(b"")

        expected = hashlib.sha256(b"").hexdigest()

        assert hash_file(f) == expected


class TestSnapshot:
    """Tests for the snapshot function."""

    def test_json_structure(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        """Snapshot JSON has the required top-level keys and format."""
        deluge_root = _make_deluge_tree(tmp_path, {"kick.wav": b"kick"})
        output_dir = tmp_path / "manifests"

        with patch("create_snapshot.SNAPSHOTS_DIR", output_dir), \
             patch("create_snapshot.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-04-02"
            result_path = snapshot(deluge_root)

        data = json.loads(result_path.read_text())
        assert data["date"] == "2026-04-02"
        assert data["deluge_root"] == str(deluge_root)
        assert "hashes" in data

        # Verify the hash entry
        expected_hash = hashlib.sha256(b"kick").hexdigest()
        assert expected_hash in data["hashes"]
        assert data["hashes"][expected_hash] == ["SAMPLES/kick.wav"]

    def test_snapshot_filename(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        """Snapshot file is named snapshot-<date>.json."""
        deluge_root = _make_deluge_tree(tmp_path, {"a.wav": b"a"})
        output_dir = tmp_path / "manifests"

        with patch("create_snapshot.SNAPSHOTS_DIR", output_dir), \
             patch("create_snapshot.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-04-02"
            result_path = snapshot(deluge_root)

        assert result_path.name == "snapshot-2026-04-02.json"

    def test_paths_relative_to_deluge_root(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        """Paths in the snapshot are relative to DELUGE_ROOT."""
        deluge_root = _make_deluge_tree(
            tmp_path, {"DRUMS/Kicks/808.wav": b"808"}
        )
        output_dir = tmp_path / "manifests"

        with patch("create_snapshot.SNAPSHOTS_DIR", output_dir):
            result_path = snapshot(deluge_root)
        data = json.loads(result_path.read_text())

        all_paths = [p for paths in data["hashes"].values() for p in paths]
        assert "SAMPLES/DRUMS/Kicks/808.wav" in all_paths

    def test_duplicate_hash_grouping(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        """Files with identical content are grouped under the same hash."""
        content = b"identical audio data"
        deluge_root = _make_deluge_tree(tmp_path, {
            "kick1.wav": content,
            "kick2.wav": content,
        })
        output_dir = tmp_path / "manifests"

        with patch("create_snapshot.SNAPSHOTS_DIR", output_dir):
            result_path = snapshot(deluge_root)
        data = json.loads(result_path.read_text())

        expected_hash = hashlib.sha256(content).hexdigest()
        paths = data["hashes"][expected_hash]
        assert len(paths) == 2
        assert "SAMPLES/kick1.wav" in paths
        assert "SAMPLES/kick2.wav" in paths

    def test_duplicate_hash_warning(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # TODO-v0.1-REVIEW
        """Duplicate content produces a console warning."""
        content = b"duplicate content"
        deluge_root = _make_deluge_tree(tmp_path, {
            "a.wav": content,
            "b.wav": content,
        })
        output_dir = tmp_path / "manifests"

        with patch("create_snapshot.SNAPSHOTS_DIR", output_dir):
            snapshot(deluge_root)

        captured = capsys.readouterr()
        assert "WARNING: duplicate content" in captured.out

    def test_console_summary(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # TODO-v0.1-REVIEW
        """Console output includes total files hashed and snapshot path."""
        deluge_root = _make_deluge_tree(tmp_path, {
            "a.wav": b"a",
            "b.wav": b"b",
        })
        output_dir = tmp_path / "manifests"

        with patch("create_snapshot.SNAPSHOTS_DIR", output_dir):
            result_path = snapshot(deluge_root)

        captured = capsys.readouterr()
        assert "Hashed 2 files" in captured.out
        assert str(result_path) in captured.out

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        """Snapshot creates the output directory if it doesn't exist."""
        deluge_root = _make_deluge_tree(tmp_path, {"a.wav": b"a"})
        output_dir = tmp_path / "new" / "nested" / "manifests"

        assert not output_dir.exists()

        with patch("create_snapshot.SNAPSHOTS_DIR", output_dir):
            snapshot(deluge_root)

        assert output_dir.is_dir()

    def test_empty_samples_dir(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        """Snapshot handles empty SAMPLES directory (no WAV files)."""
        deluge_root = tmp_path / "DELUGE"
        (deluge_root / "SAMPLES").mkdir(parents=True)
        output_dir = tmp_path / "manifests"

        with patch("create_snapshot.SNAPSHOTS_DIR", output_dir):
            result_path = snapshot(deluge_root)
        data = json.loads(result_path.read_text())

        assert data["hashes"] == {}

    def test_no_samples_dir(self, tmp_path: Path) -> None:
        # TODO-v0.1-REVIEW
        """Snapshot handles missing SAMPLES directory gracefully."""
        deluge_root = tmp_path / "DELUGE"
        deluge_root.mkdir()
        output_dir = tmp_path / "manifests"

        with patch("create_snapshot.SNAPSHOTS_DIR", output_dir):
            result_path = snapshot(deluge_root)
        data = json.loads(result_path.read_text())

        assert data["hashes"] == {}


class TestMain:
    """Tests for the CLI entry point."""

    def test_snapshot_runs(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # TODO-v0.1-REVIEW
        """The script creates a snapshot when run."""
        from create_snapshot import main

        deluge_root = _make_deluge_tree(tmp_path, {"kick.wav": b"kick"})
        output_dir = tmp_path / "manifests"

        with patch("create_snapshot.get_deluge_root", return_value=deluge_root), patch(
            "create_snapshot.SNAPSHOTS_DIR", output_dir
        ):
            main([])

        captured = capsys.readouterr()
        assert "Hashed 1 files" in captured.out
