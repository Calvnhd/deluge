"""Tests for deluge_lib.manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from deluge_lib.manifest import ManifestData, read_manifest, write_manifest


def _valid_manifest_dict(
    files: dict[str, Any] | None = None,
    **meta_overrides: Any,
) -> dict[str, Any]:
    """Build a valid manifest JSON structure for testing."""
    meta: dict[str, Any] = {
        "version": "1.0",
        "last_sync_timestamp": "2026-04-09T00:00:00+00:00",
        "last_sync_direction": "sd-to-local",
        "file_count": 0,
    }
    meta.update(meta_overrides)
    if files is None:
        files = {}
    meta["file_count"] = len(files)
    return {"metadata": meta, "files": files}


# -- read_manifest -----------------------------------------------------------


class TestReadManifest:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = read_manifest(tmp_path / "nonexistent.json")
        assert result.files == {}
        assert result.file_count == 0

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        bad = tmp_path / "manifest.json"
        bad.write_text("{invalid json!!!", encoding="utf-8")

        result = read_manifest(bad)

        assert result.files == {}
        assert result.file_count == 0

    def test_corrupt_json_no_bak_created(self, tmp_path: Path) -> None:
        bad = tmp_path / "manifest.json"
        bad.write_text("not-json", encoding="utf-8")

        read_manifest(bad)

        bak_files = list(tmp_path.glob("*.bak"))
        assert bak_files == []

    def test_corrupt_json_prints_warning(self, tmp_path: Path, capsys: object) -> None:
        bad = tmp_path / "manifest.json"
        bad.write_text("{broken", encoding="utf-8")

        read_manifest(bad)

        import _pytest.capture

        assert isinstance(capsys, _pytest.capture.CaptureFixture)
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "corrupt" in captured.out.lower()

    def test_valid_manifest_preserves_fields(self, tmp_path: Path) -> None:
        files = {
            "kits/mykit.xml": {"size": 1234, "mtime": 1712600000.0},
            "samples/kick.wav": {"size": 56789, "mtime": 1712600100.0},
        }
        payload = _valid_manifest_dict(
            files=files,
            last_sync_direction="sd-to-local",
            last_sync_timestamp="2026-04-09T12:00:00+00:00",
        )
        mf = tmp_path / "manifest.json"
        mf.write_text(json.dumps(payload), encoding="utf-8")

        result = read_manifest(mf)

        assert result.version == "1.0"
        assert result.last_sync_direction == "sd-to-local"
        assert result.last_sync_timestamp == "2026-04-09T12:00:00+00:00"
        assert result.file_count == 2
        assert len(result.files) == 2
        assert result.files["kits/mykit.xml"]["size"] == 1234


# -- write_manifest ----------------------------------------------------------


class TestWriteManifest:
    def test_creates_file_with_json(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "data" / "manifest.json"
        data = ManifestData(
            files={"kits/test.xml": {"size": 100, "mtime": 1.0}},
        )

        write_manifest(data, mf_path)

        assert mf_path.exists()
        raw = json.loads(mf_path.read_text(encoding="utf-8"))
        assert "metadata" in raw
        assert "files" in raw

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "scripts" / "data" / "manifest.json"
        write_manifest(ManifestData(), mf_path)
        assert mf_path.parent.is_dir()

    def test_atomic_write_no_temp_file_lingers(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "manifest.json"
        write_manifest(ManifestData(), mf_path)

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_file_count_synced(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "manifest.json"
        data = ManifestData(
            files={
                "a.xml": {"size": 1, "mtime": 1.0},
                "b.wav": {"size": 2, "mtime": 2.0},
            },
        )
        write_manifest(data, mf_path)

        raw = json.loads(mf_path.read_text(encoding="utf-8"))
        assert raw["metadata"]["file_count"] == 2


# -- Metadata section --------------------------------------------------------


class TestMetadata:
    def test_metadata_has_version(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "manifest.json"
        write_manifest(ManifestData(), mf_path)

        raw = json.loads(mf_path.read_text(encoding="utf-8"))
        assert "version" in raw["metadata"]

    def test_metadata_has_timestamp(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "manifest.json"
        data = ManifestData(last_sync_timestamp="2026-04-09T00:00:00+00:00")
        write_manifest(data, mf_path)

        raw = json.loads(mf_path.read_text(encoding="utf-8"))
        assert raw["metadata"]["last_sync_timestamp"] == "2026-04-09T00:00:00+00:00"

    def test_metadata_has_direction(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "manifest.json"
        data = ManifestData(last_sync_direction="sd-to-local")
        write_manifest(data, mf_path)

        raw = json.loads(mf_path.read_text(encoding="utf-8"))
        assert raw["metadata"]["last_sync_direction"] == "sd-to-local"

    def test_metadata_has_count(self, tmp_path: Path) -> None:
        mf_path = tmp_path / "manifest.json"
        data = ManifestData(files={"x.xml": {"size": 1, "mtime": 1.0}})
        write_manifest(data, mf_path)

        raw = json.loads(mf_path.read_text(encoding="utf-8"))
        assert raw["metadata"]["file_count"] == 1


# -- Extensibility (D30) ----------------------------------------------------


class TestExtensibility:
    def test_unknown_fields_survive_round_trip(self, tmp_path: Path) -> None:
        files = {
            "kits/kit.xml": {
                "size": 100,
                "mtime": 1.0,
                "sha256": "abc123",
                "custom_flag": True,
            },
        }
        payload = _valid_manifest_dict(files=files)
        mf = tmp_path / "manifest.json"
        mf.write_text(json.dumps(payload), encoding="utf-8")

        data = read_manifest(mf)

        assert data.files["kits/kit.xml"]["sha256"] == "abc123"
        assert data.files["kits/kit.xml"]["custom_flag"] is True

        # Write back and re-read — unknown fields must survive.
        write_manifest(data, mf)
        data2 = read_manifest(mf)
        assert data2.files["kits/kit.xml"]["sha256"] == "abc123"
        assert data2.files["kits/kit.xml"]["custom_flag"] is True


# -- Forward-slash keys (D32) ------------------------------------------------


class TestForwardSlashKeys:
    def test_keys_use_forward_slashes(self, tmp_path: Path) -> None:
        files = {"kits/sub/kit.xml": {"size": 10, "mtime": 1.0}}
        payload = _valid_manifest_dict(files=files)
        mf = tmp_path / "manifest.json"
        mf.write_text(json.dumps(payload), encoding="utf-8")

        data = read_manifest(mf)

        for key in data.files:
            assert "\\" not in key, f"Key contains backslash: {key}"
            assert "/" in key or "/" not in key  # single-component keys are fine

    def test_written_keys_use_forward_slashes(self, tmp_path: Path) -> None:
        mf = tmp_path / "manifest.json"
        data = ManifestData(
            files={"kits/deep/kit.xml": {"size": 1, "mtime": 1.0}},
        )
        write_manifest(data, mf)

        raw = json.loads(mf.read_text(encoding="utf-8"))
        for key in raw["files"]:
            assert "\\" not in key
