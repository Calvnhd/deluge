"""Tests for manual, deterministic sample catalogue generation."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest
import sample_overview
from sample_overview import cmd_catalogue, main

from deluge_lib.analysis import SampleUsage, UsageIndex
from deluge_lib.scanning import FileFilter, ScanResult, scan_tree
from tests.conftest import _touch


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_catalogue_includes_audio_only_and_counts_distinct_xmls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "DELUGE"
    samples = root / "SAMPLES"
    _touch(samples / "DRUMS" / "Kick.wav", b"x" * 1_234_567)
    _touch(samples / "Tones" / "Bell.AIFF", b"x" * 23_000)
    _touch(samples / "Tones" / "Short, quiet.aif", b"x")
    _touch(samples / "CITIZEN-DJ" / "attributions" / "credit.txt", b"credits")
    _touch(samples / ".trash" / "deleted.wav")
    _touch(
        root / "KITS" / "Kit.XML",
        b'<kit><osc1 fileName="SAMPLES/DRUMS/Kick.wav"/>'
        b'<osc2 fileName="samples/drums/kick.WAV"/></kit>',
    )
    _touch(
        root / "KITS" / "Other.XML",
        b"<kit><osc1><fileName>SAMPLES/DRUMS/Kick.wav</fileName></osc1></kit>",
    )
    _touch(
        root / "SYNTHS" / "Bell.XML",
        b'<sound><osc1 fileName="SAMPLES/Tones/Bell.AIFF"/></sound>',
    )
    _touch(
        root / "SONGS" / "Song.XML",
        b'<song><instruments><kit><osc1 fileName="SAMPLES/DRUMS/Kick.wav"/>'
        b'</kit></instruments><audioClip filePath="SAMPLES/DRUMS/Kick.wav"/>'
        b'<audioClip filePath="SAMPLES/Tones/Bell.AIFF"/>'
        b'<audioClip filePath="SAMPLES/missing.wav"/></song>',
    )
    _touch(
        root / "SONGS" / "Song 2.XML",
        b'<song><audioClip filePath="SAMPLES/DRUMS/Kick.wav"/></song>',
    )
    output = tmp_path / "docs" / "sample-catalogue.csv"
    monkeypatch.setenv("DELUGE_ROOT", str(root))
    with patch("deluge_lib.cli_utils.load_dotenv"):
        main(["catalogue", "--output", str(output)])

    assert _read_rows(output) == [
        {
            "sample_path": "SAMPLES/DRUMS/Kick.wav",
            "size_mb": "1.235",
            "kit_presets": "2",
            "synth_presets": "0",
            "songs": "2",
        },
        {
            "sample_path": "SAMPLES/Tones/Bell.AIFF",
            "size_mb": "0.023",
            "kit_presets": "0",
            "synth_presets": "1",
            "songs": "1",
        },
        {
            "sample_path": "SAMPLES/Tones/Short, quiet.aif",
            "size_mb": "0.000",
            "kit_presets": "0",
            "synth_presets": "0",
            "songs": "0",
        },
    ]
    assert b"\r" not in output.read_bytes()
    assert str(root).encode() not in output.read_bytes()
    assert not list(output.parent.glob("*.tmp"))


@pytest.mark.parametrize(
    ("size", "expected"),
    [(0, "0.000"), (499, "0.000"), (501, "0.001"), (999_999, "1.000"), (10_000_000, "10.000")],
)
def test_catalogue_sizes_use_three_decimal_mb(tmp_path: Path, size: int, expected: str) -> None:
    output = tmp_path / "catalogue.csv"
    index = UsageIndex(entries={"sample.wav": SampleUsage("sample.wav", size)})

    cmd_catalogue(index, argparse.Namespace(output=output))

    assert _read_rows(output)[0]["size_mb"] == expected


def test_catalogue_reports_unexpected_files_but_ignores_citizen_dj_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "DELUGE"
    files = {
        "good.WAV": b"wave",
        "short.AIF": b"aiff",
        "long.aIfF": b"aiff",
        "CITIZEN-DJ/README.TXT": b"collection rights",
        "CITIZEN-DJ/collection/attributions/credit.txt": b"recording credit",
        "cover.JPG": b"image",
        "Loops/unsupported.mp3": b"unsupported audio",
        "compressed.aifc": b"unsupported variant",
        "Licenses/license.txt": b"unrecognised supporting file",
        "CITIZEN-DJ/collection/other.bin": b"unexpected file",
    }
    for relative, content in files.items():
        _touch(root / "SAMPLES" / relative, content)
    output = tmp_path / "catalogue.csv"
    monkeypatch.setenv("DELUGE_ROOT", str(root))

    with patch("deluge_lib.cli_utils.load_dotenv"):
        main(["catalogue", "--output", str(output)])

    assert [row["sample_path"] for row in _read_rows(output)] == [
        "SAMPLES/good.WAV",
        "SAMPLES/long.aIfF",
        "SAMPLES/short.AIF",
    ]
    report = capsys.readouterr().out
    assert "5 unexpected non-audio files" in report
    assert "Investigate before removal" in report
    reported_paths = [line.strip() for line in report.splitlines() if line.startswith("  SAMPLES/")]
    assert reported_paths == [
        "SAMPLES/CITIZEN-DJ/collection/other.bin",
        "SAMPLES/compressed.aifc",
        "SAMPLES/cover.JPG",
        "SAMPLES/Licenses/license.txt",
        "SAMPLES/Loops/unsupported.mp3",
    ]
    assert "README.TXT" not in report
    assert "credit.txt" not in report
    for relative, content in files.items():
        assert (root / "SAMPLES" / relative).read_bytes() == content


def test_catalogue_order_and_bytes_ignore_scan_order_and_mtimes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "DELUGE"
    for name in ("Z.wav", "a.wav", "Middle.aiff"):
        _touch(root / "SAMPLES" / name, name.encode())
    output = tmp_path / "sample-catalogue.csv"
    monkeypatch.setenv("DELUGE_ROOT", str(root))
    original_scan = scan_tree

    with patch("deluge_lib.cli_utils.load_dotenv"):
        main(["catalogue", "--output", str(output)])
        before = output.read_bytes()

        def scan_reversed(
            directory: Path,
            *,
            label: str,
            file_filter: FileFilter | Literal["all"],
            strict: bool,
        ) -> ScanResult:
            result = original_scan(directory, label=label, file_filter=file_filter, strict=strict)
            result.files = dict(reversed(list(result.files.items())))
            return result

        for path in (root / "SAMPLES").iterdir():
            os.utime(path, (1_700_000_000, 1_700_000_000))
        with patch("sample_overview.scan_tree", side_effect=scan_reversed):
            main(["catalogue", "--output", str(output)])
        assert output.read_bytes() == before

        _touch(root / "SAMPLES" / "New.wav", b"new")
        main(["catalogue", "--output", str(output)])
    after_lines = output.read_bytes().splitlines(keepends=True)
    assert [line for line in after_lines if not line.startswith(b"SAMPLES/New.wav,")] == (
        before.splitlines(keepends=True)
    )


def test_catalogue_default_output_is_repo_docs_and_requires_manual_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "DELUGE"
    _touch(root / "SAMPLES" / "sample.wav")
    output = tmp_path / "docs" / "sample-catalogue.csv"
    monkeypatch.setenv("DELUGE_ROOT", str(root))
    monkeypatch.setattr(sample_overview, "SAMPLE_CATALOGUE_PATH", output)
    with patch("deluge_lib.cli_utils.load_dotenv"):
        main([])
        assert not output.exists()
        main(["catalogue"])
    assert output.is_file()


def test_missing_samples_directory_does_not_replace_catalogue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "DELUGE"
    root.mkdir()
    output = tmp_path / "sample-catalogue.csv"
    output.write_bytes(b"existing catalogue\n")
    monkeypatch.setenv("DELUGE_ROOT", str(root))
    with (
        patch("deluge_lib.cli_utils.load_dotenv"),
        pytest.raises(NotADirectoryError, match="Scan directory"),
    ):
        main(["catalogue", "--output", str(output)])
    assert output.read_bytes() == b"existing catalogue\n"


def test_failed_catalogue_write_preserves_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "sample-catalogue.csv"
    output.write_bytes(b"existing catalogue\n")
    index = UsageIndex(entries={"sample.wav": SampleUsage("sample.wav", 100)})
    with (
        patch("sample_overview.csv.writer", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        cmd_catalogue(index, argparse.Namespace(output=output))
    assert output.read_bytes() == b"existing catalogue\n"
    assert list(tmp_path.iterdir()) == [output]


def test_xml_scan_error_does_not_replace_catalogue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "DELUGE"
    _touch(root / "SAMPLES" / "sample.wav")
    (root / "KITS").mkdir()
    output = tmp_path / "sample-catalogue.csv"
    output.write_bytes(b"existing catalogue\n")
    monkeypatch.setenv("DELUGE_ROOT", str(root))
    with (
        patch("deluge_lib.cli_utils.load_dotenv"),
        patch(
            "deluge_lib.deluge_sdk.scan_tree", side_effect=PermissionError("cannot read kits")
        ) as xml_scan,
        pytest.raises(PermissionError, match="cannot read kits"),
    ):
        main(["catalogue", "--output", str(output)])
    xml_scan.assert_called_once_with(root / "KITS", label="KITS", file_filter="xml", strict=True)
    assert output.read_bytes() == b"existing catalogue\n"


@pytest.mark.parametrize("with_text_files", [False, True])
def test_empty_audio_library_writes_header_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_text_files: bool
) -> None:
    root = tmp_path / "DELUGE"
    (root / "SAMPLES").mkdir(parents=True)
    if with_text_files:
        _touch(root / "SAMPLES" / "CITIZEN-DJ" / "README.txt", b"keep this notice")
    output = tmp_path / "sample-catalogue.csv"
    monkeypatch.setenv("DELUGE_ROOT", str(root))
    with patch("deluge_lib.cli_utils.load_dotenv"):
        main(["catalogue", "--output", str(output)])
    assert output.read_bytes() == b"sample_path,size_mb,kit_presets,synth_presets,songs\n"
