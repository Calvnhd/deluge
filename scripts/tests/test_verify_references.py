"""Tests for verify_references.py — reference existence checking."""

from pathlib import Path
from unittest.mock import patch

import pytest
from verify_references import (
    check_references,
    check_special_dirs,
    find_unextracted_refs,
    main,
)

from deluge_lib.deluge_sdk import SampleRef

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestCheckReferences:
    """Tests for the check_references function."""

    def test_all_references_valid(self, tmp_path: Path) -> None:
        """When all referenced samples exist, result reports zero broken."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/kick.wav"/>'
            "</sound></soundSources></kit>"
        )
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        (samples / "kick.wav").write_bytes(b"\x00")

        result = check_references(tmp_path)

        assert result.total_refs == 1
        assert not result.broken

    def test_broken_reference_detected(self, tmp_path: Path) -> None:
        """When a referenced sample is missing, it appears in broken list."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/missing.wav"/>'
            "</sound></soundSources></kit>"
        )

        result = check_references(tmp_path)

        assert result.total_refs == 1
        assert len(result.broken) == 1
        assert result.broken[0].sample_path == "SAMPLES/missing.wav"
        assert result.broken[0].xml_file == Path("KITS/test.XML")

    def test_mix_of_valid_and_broken(self, tmp_path: Path) -> None:
        """Reports only missing references, not valid ones."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/exists.wav"/>'
            '<osc2 fileName="SAMPLES/gone.wav"/>'
            "</sound></soundSources></kit>"
        )
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        (samples / "exists.wav").write_bytes(b"\x00")

        result = check_references(tmp_path)

        assert result.total_refs == 2
        assert len(result.broken) == 1
        assert result.broken[0].sample_path == "SAMPLES/gone.wav"

    def test_broken_ref_includes_preset_name(self, tmp_path: Path) -> None:
        """BrokenRef carries the preset name from the source XML."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "MyKit.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/nope.wav"/>'
            "</sound></soundSources></kit>"
        )

        result = check_references(tmp_path)

        assert result.broken[0].preset_name == "MyKit"

    def test_multiple_xml_files(self, tmp_path: Path) -> None:
        """Collects broken refs across multiple XML files."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "A.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/a.wav"/>'
            "</sound></soundSources></kit>"
        )
        synths = tmp_path / "SYNTHS"
        synths.mkdir()
        (synths / "B.XML").write_text(
            '<?xml version="1.0"?>'
            '<sound><osc1 fileName="SAMPLES/b.wav"/></sound>'
        )

        result = check_references(tmp_path)

        assert result.total_refs == 2
        assert len(result.broken) == 2
        paths = {r.sample_path for r in result.broken}
        assert paths == {"SAMPLES/a.wav", "SAMPLES/b.wav"}

    def test_no_xml_files(self, tmp_path: Path) -> None:
        """Empty DELUGE directory returns zero refs, zero broken."""
        result = check_references(tmp_path)

        assert result.total_refs == 0
        assert not result.broken

    def test_with_fixtures(self) -> None:
        """Integration test using the real test fixtures."""
        result = check_references(FIXTURES_DIR)

        # Fixtures reference samples that don't exist on disk — all should be broken
        assert result.total_refs > 0
        assert len(result.broken) == result.total_refs


class TestFindUnextractedRefs:
    """Tests for the find_unextracted_refs function."""

    def test_no_unextracted_when_all_refs_extracted(self, tmp_path: Path) -> None:
        """When regex finds only paths that were already extracted, returns empty."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        xml_file = kits / "test.XML"
        xml_file.write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/kick.wav"/>'
            "</sound></soundSources></kit>"
        )
        extracted = [
            SampleRef(
                path="SAMPLES/kick.wav",
                xml_file=Path("KITS/test.XML"),
                xml_type="kit",
                preset_name="test",
                ref_type="fileName-attribute",
                element_tag="osc1",
            )
        ]

        result = find_unextracted_refs(xml_file, extracted)

        assert result == []

    def test_detects_path_in_unexpected_element(self, tmp_path: Path) -> None:
        """A sample path inside an element not handled by extract_sample_refs() is detected."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        xml_file = kits / "test.XML"
        xml_file.write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/kick.wav"/>'
            "<customData>SAMPLES/HIDDEN/secret.wav</customData>"
            "</sound></soundSources></kit>"
        )
        extracted = [
            SampleRef(
                path="SAMPLES/kick.wav",
                xml_file=Path("KITS/test.XML"),
                xml_type="kit",
                preset_name="test",
                ref_type="fileName-attribute",
                element_tag="osc1",
            )
        ]

        result = find_unextracted_refs(xml_file, extracted)

        assert len(result) == 1
        assert result[0] == "SAMPLES/HIDDEN/secret.wav"

    def test_case_insensitive_regex(self, tmp_path: Path) -> None:
        """Regex matches sample paths regardless of case."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        xml_file = kits / "test.XML"
        xml_file.write_text(
            '<?xml version="1.0"?>'
            "<kit><note>samples/Drums/kick.WAV</note></kit>"
        )

        result = find_unextracted_refs(xml_file, [])

        assert len(result) == 1
        assert result[0] == "samples/Drums/kick.WAV"

    def test_no_sample_paths_in_raw_text(self, tmp_path: Path) -> None:
        """When no sample paths appear in raw text, returns empty."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        xml_file = kits / "test.XML"
        xml_file.write_text(
            '<?xml version="1.0"?>'
            "<kit><soundSources></soundSources></kit>"
        )

        result = find_unextracted_refs(xml_file, [])

        assert result == []

    def test_with_fixture(self) -> None:
        """Integration test using the unextracted_ref_kit fixture."""
        from deluge_lib.deluge_sdk import extract_sample_refs

        fixture = FIXTURES_DIR / "KITS" / "unextracted_ref_kit.xml"
        extracted = extract_sample_refs(fixture, FIXTURES_DIR)

        result = find_unextracted_refs(fixture, extracted)

        # The fixture has SAMPLES/HIDDEN/SecretSample.wav in <customData>
        # which is not a known reference pattern
        assert len(result) == 1
        assert result[0] == "SAMPLES/HIDDEN/SecretSample.wav"


class TestCheckReferencesUnextracted:
    """Tests that check_references collects unextracted refs."""

    def test_unextracted_refs_collected(self, tmp_path: Path) -> None:
        """check_references populates the unextracted field."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/kick.wav"/>'
            "<extra>SAMPLES/BONUS/extra.wav</extra>"
            "</sound></soundSources></kit>"
        )

        result = check_references(tmp_path)

        assert len(result.unextracted) == 1
        assert result.unextracted[0] == (Path("KITS/test.XML"), "SAMPLES/BONUS/extra.wav")
        assert result.broken  # broken because file doesn't exist
        assert len(result.broken) == 1

    def test_unextracted_does_not_affect_broken(self, tmp_path: Path) -> None:
        """Unextracted warnings do not appear in broken list."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/kick.wav"/>'
            "<extra>SAMPLES/BONUS/extra.wav</extra>"
            "</sound></soundSources></kit>"
        )
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        (samples / "kick.wav").write_bytes(b"\x00")

        result = check_references(tmp_path)

        # kick.wav exists so no broken refs
        assert not result.broken
        # But we still have unextracted warnings
        assert len(result.unextracted) == 1


class TestCheckSpecialDirs:
    """Tests for the check_special_dirs function."""

    def test_all_dirs_present_no_subdirs(self, tmp_path: Path) -> None:
        """When all three directories exist, returns empty list."""
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        (samples / "CLIPS").mkdir()
        (samples / "RECORD").mkdir()
        (samples / "RESAMPLE").mkdir()

        result = check_special_dirs(tmp_path)

        assert result == []

    def test_missing_dirs_reported(self, tmp_path: Path) -> None:
        """Missing directories are returned in the list."""
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        # Only create CLIPS — RECORD and RESAMPLE are missing
        (samples / "CLIPS").mkdir()

        result = check_special_dirs(tmp_path)

        assert len(result) == 2
        assert set(result) == {"SAMPLES/RECORD", "SAMPLES/RESAMPLE"}

    def test_all_dirs_missing(self, tmp_path: Path) -> None:
        """When SAMPLES/ doesn't even exist, all three are returned."""
        result = check_special_dirs(tmp_path)

        assert len(result) == 3

    def test_subdirs_in_special_dirs_are_allowed(self, tmp_path: Path) -> None:
        """Subdirectories inside special dirs are not flagged (firmware creates them)."""
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        clips = samples / "CLIPS"
        clips.mkdir()
        (clips / "TEMP").mkdir()
        (samples / "RECORD").mkdir()
        (samples / "RESAMPLE").mkdir()

        result = check_special_dirs(tmp_path)

        assert result == []

    def test_files_in_special_dir_are_fine(self, tmp_path: Path) -> None:
        """Regular files inside special dirs are not flagged."""
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        clips = samples / "CLIPS"
        clips.mkdir()
        (clips / "recording.wav").write_bytes(b"\x00")
        (samples / "RECORD").mkdir()
        (samples / "RESAMPLE").mkdir()

        result = check_special_dirs(tmp_path)

        assert result == []

    def test_mixed_warnings_and_present(self, tmp_path: Path) -> None:
        """A mix of missing and present dirs."""
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        resample = samples / "RESAMPLE"
        resample.mkdir()
        (resample / "subdir").mkdir()  # subdirs are fine now
        # CLIPS and RECORD missing

        result = check_special_dirs(tmp_path)

        assert len(result) == 2


class TestMain:
    """Tests for the main() CLI entry point."""

    def _setup_valid_deluge(self, tmp_path: Path) -> None:
        """Create a minimal DELUGE directory where all references are valid."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/kick.wav"/>'
            "</sound></soundSources></kit>"
        )
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        (samples / "kick.wav").write_bytes(b"\x00")
        (samples / "CLIPS").mkdir()
        (samples / "RECORD").mkdir()
        (samples / "RESAMPLE").mkdir()

    def test_exit_0_when_all_valid(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Exit code 0 when all references are valid."""
        self._setup_valid_deluge(tmp_path)

        with (
            patch("verify_references.get_deluge_root", return_value=tmp_path),
            pytest.raises(SystemExit) as exc_info,
        ):
            main([])

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "All references valid." in out
        assert "0 broken" in out

    def test_exit_1_when_broken(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Exit code 1 when broken references exist."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/missing.wav"/>'
            "</sound></soundSources></kit>"
        )

        with (
            patch("verify_references.get_deluge_root", return_value=tmp_path),
            pytest.raises(SystemExit) as exc_info,
        ):
            main([])

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "Broken references (1):" in out
        assert "SAMPLES/missing.wav" in out
        assert "1 broken" in out

    def test_missing_dirs_are_warnings_only(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Missing special directories produce warnings but exit code stays 0."""
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text(
            '<?xml version="1.0"?>'
            '<kit><soundSources><sound>'
            '<osc1 fileName="SAMPLES/kick.wav"/>'
            "</sound></soundSources></kit>"
        )
        samples = tmp_path / "SAMPLES"
        samples.mkdir()
        (samples / "kick.wav").write_bytes(b"\x00")
        # No CLIPS, RECORD, RESAMPLE

        with (
            patch("verify_references.get_deluge_root", return_value=tmp_path),
            pytest.raises(SystemExit) as exc_info,
        ):
            main([])

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "Missing special directories (warning):" in out
        assert "3 directory warnings" in out
