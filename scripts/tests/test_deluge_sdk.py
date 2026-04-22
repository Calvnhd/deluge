"""Tests for deluge_sdk.py — XML discovery, reference extraction, and unextracted ref detection."""

import shutil
from pathlib import Path

from deluge_lib.deluge_sdk import (
    SampleRef,
    detect_xml_type,
    extract_sample_refs,
    find_all_xml_files,
    find_unextracted_refs,
)
from fix_references import update_sample_refs

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- find_all_xml_files tests ---


class TestFindAllXmlFiles:
    def test_finds_xml_in_all_subdirs(self, tmp_path: Path) -> None:
        for subdir in ("KITS", "SYNTHS", "SONGS"):
            d = tmp_path / subdir
            d.mkdir()
            (d / "test.XML").write_text("<kit/>")

        result = find_all_xml_files(tmp_path)
        assert len(result) == 3

    def test_case_insensitive_extension(self, tmp_path: Path) -> None:
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "upper.XML").write_text("<kit/>")
        (kits / "lower.xml").write_text("<kit/>")

        result = find_all_xml_files(tmp_path)
        assert len(result) == 2

    def test_missing_subdirectories(self, tmp_path: Path) -> None:
        result = find_all_xml_files(tmp_path)
        assert result == []

    def test_partial_subdirectories(self, tmp_path: Path) -> None:
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text("<kit/>")

        result = find_all_xml_files(tmp_path)
        assert len(result) == 1

    def test_recursive_discovery(self, tmp_path: Path) -> None:
        nested = tmp_path / "KITS" / "COMMUNITY" / "subfolder"
        nested.mkdir(parents=True)
        (nested / "deep.XML").write_text("<kit/>")

        result = find_all_xml_files(tmp_path)
        assert len(result) == 1
        assert result[0].name == "deep.XML"


# --- detect_xml_type tests ---


class TestDetectXmlType:
    def test_kit(self, tmp_path: Path) -> None:
        kit_file = tmp_path / "KITS" / "test.XML"
        kit_file.parent.mkdir()
        kit_file.write_text('<?xml version="1.0"?><kit/>')
        assert detect_xml_type(kit_file) == "kit"

    def test_synth(self, tmp_path: Path) -> None:
        synth_file = tmp_path / "SYNTHS" / "test.XML"
        synth_file.parent.mkdir()
        synth_file.write_text('<?xml version="1.0"?><sound/>')
        assert detect_xml_type(synth_file) == "synth"

    def test_song(self, tmp_path: Path) -> None:
        song_file = tmp_path / "SONGS" / "test.XML"
        song_file.parent.mkdir()
        song_file.write_text('<?xml version="1.0"?><song/>')
        assert detect_xml_type(song_file) == "song"

    def test_raises_for_unknown_path(self, tmp_path: Path) -> None:
        import pytest

        unknown_file = tmp_path / "OTHER" / "test.XML"
        unknown_file.parent.mkdir()
        unknown_file.write_text('<?xml version="1.0"?><kit/>')
        with pytest.raises(ValueError, match="does not contain KITS"):
            detect_xml_type(unknown_file)

    def test_nested_kit(self) -> None:
        assert detect_xml_type(FIXTURES_DIR / "KITS/attribute_kit.xml") == "kit"

    def test_nested_synth(self) -> None:
        assert detect_xml_type(FIXTURES_DIR / "SYNTHS/attribute_synth_multisample.xml") == "synth"

    def test_nested_song(self) -> None:
        assert detect_xml_type(FIXTURES_DIR / "SONGS/song_with_clips.xml") == "song"


# --- extract_sample_refs tests ---


class TestExtractSampleRefs:
    """Test reference extraction for all 6 fixture files."""

    def test_element_kit_paths(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/element_kit.xml", FIXTURES_DIR)
        paths = {r.path for r in refs}
        assert paths == {
            "SAMPLES/DRUMS/Kick/808 Kick.wav",
            "SAMPLES/DRUMS/Snare/TR-909 Snare.wav",
        }

    def test_element_kit_ref_types(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/element_kit.xml", FIXTURES_DIR)
        for ref in refs:
            assert ref.ref_type == "fileName-element"
            assert ref.element_tag == "osc1"
            assert ref.xml_type == "kit"

    def test_element_synth_multisample_paths(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SYNTHS/element_synth_multisample.xml", FIXTURES_DIR)
        paths = {r.path for r in refs}
        assert paths == {
            "SAMPLES/Artists/Leonard Ludvigsen/Hangdrum/1.wav",
            "SAMPLES/Artists/Leonard Ludvigsen/Hangdrum/2.wav",
        }

    def test_element_synth_ref_types(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SYNTHS/element_synth_multisample.xml", FIXTURES_DIR)
        for ref in refs:
            assert ref.ref_type == "fileName-element"
            assert ref.element_tag == "sampleRange"
            assert ref.xml_type == "synth"

    def test_attribute_kit_paths(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/attribute_kit.xml", FIXTURES_DIR)
        paths = {r.path for r in refs}
        assert paths == {
            "SAMPLES/DRUMS/Kick/Deep Sky Kick HQ9094.wav",
            "SAMPLES/WAVETABLES/Basic Shapes.wav",
            "SAMPLES/DRUMS/Hat/CR-78 Hat.wav",
        }

    def test_attribute_kit_wavetable_not_filtered(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/attribute_kit.xml", FIXTURES_DIR)
        wavetable_refs = [r for r in refs if "Basic Shapes" in r.path]
        assert len(wavetable_refs) == 1
        assert wavetable_refs[0].element_tag == "osc1"

    def test_attribute_kit_ref_types(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/attribute_kit.xml", FIXTURES_DIR)
        for ref in refs:
            assert ref.ref_type == "fileName-attribute"

    def test_attribute_kit_element_tags(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/attribute_kit.xml", FIXTURES_DIR)
        by_path = {r.path: r for r in refs}
        assert by_path["SAMPLES/DRUMS/Kick/Deep Sky Kick HQ9094.wav"].element_tag == "osc1"
        assert by_path["SAMPLES/WAVETABLES/Basic Shapes.wav"].element_tag == "osc1"
        assert by_path["SAMPLES/DRUMS/Hat/CR-78 Hat.wav"].element_tag == "osc2"

    def test_attribute_synth_multisample_paths(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SYNTHS/attribute_synth_multisample.xml", FIXTURES_DIR)
        paths = {r.path for r in refs}
        assert paths == {
            "SAMPLES/Artists/Leonard Ludvigsen/Double bass/Lo/36 b.WAV",
            "SAMPLES/Artists/Leonard Ludvigsen/Double bass/Lo/39 b.WAV",
        }

    def test_attribute_synth_ref_types(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SYNTHS/attribute_synth_multisample.xml", FIXTURES_DIR)
        for ref in refs:
            assert ref.ref_type == "fileName-attribute"
            assert ref.element_tag == "sampleRange"

    def test_song_paths(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SONGS/song_with_clips.xml", FIXTURES_DIR)
        paths = {r.path for r in refs}
        assert paths == {
            "SAMPLES/DRUMS/Kick/Rhythmace Kick.wav",
            "SAMPLES/Artists/Leonard Ludvigsen/Double bass/Lo/36 b.WAV",
            "SAMPLES/Artists/Leonard Ludvigsen/Double bass/Lo/39 b.WAV",
            "SAMPLES/CLIPS/REC00040.WAV",
        }

    def test_song_ref_types(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SONGS/song_with_clips.xml", FIXTURES_DIR)
        by_path = {r.path: r for r in refs}

        kick = by_path["SAMPLES/DRUMS/Kick/Rhythmace Kick.wav"]
        assert kick.ref_type == "fileName-attribute"
        assert kick.element_tag == "osc1"

        clip = by_path["SAMPLES/CLIPS/REC00040.WAV"]
        assert clip.ref_type == "filePath-attribute"
        assert clip.element_tag == "audioClip"

        for sr_path in (
            "SAMPLES/Artists/Leonard Ludvigsen/Double bass/Lo/36 b.WAV",
            "SAMPLES/Artists/Leonard Ludvigsen/Double bass/Lo/39 b.WAV",
        ):
            assert by_path[sr_path].ref_type == "fileName-attribute"
            assert by_path[sr_path].element_tag == "sampleRange"

    def test_empty_refs_valid_path(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/empty_refs.xml", FIXTURES_DIR)
        assert len(refs) == 1
        assert refs[0].path == "SAMPLES/DRUMS/Kick/Validate.wav"

    def test_preserves_path_case(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SYNTHS/attribute_synth_multisample.xml", FIXTURES_DIR)
        paths = {r.path for r in refs}
        assert "SAMPLES/Artists/Leonard Ludvigsen/Double bass/Lo/36 b.WAV" in paths

    def test_xml_file_is_relative(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/element_kit.xml", FIXTURES_DIR)
        for ref in refs:
            assert not ref.xml_file.is_absolute()
            assert ref.xml_file == Path("KITS/element_kit.xml")


# --- Preset name extraction tests ---


class TestPresetNameExtraction:
    def test_standalone_preset_uses_filename(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/element_kit.xml", FIXTURES_DIR)
        for ref in refs:
            assert ref.preset_name == "element_kit"

    def test_song_embedded_kit_preset_name(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SONGS/song_with_clips.xml", FIXTURES_DIR)
        kick = [r for r in refs if "Rhythmace Kick" in r.path][0]
        assert kick.preset_name == "K01Perc2"

    def test_song_embedded_synth_preset_name(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SONGS/song_with_clips.xml", FIXTURES_DIR)
        bass_refs = [r for r in refs if "Double bass" in r.path]
        assert len(bass_refs) == 2
        for ref in bass_refs:
            assert ref.preset_name == "DoubleBass"

    def test_song_audio_clip_track_name(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SONGS/song_with_clips.xml", FIXTURES_DIR)
        clip = [r for r in refs if "REC00040" in r.path][0]
        assert clip.preset_name == "AUDIO2"

    def test_empty_refs_uses_filename(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/empty_refs.xml", FIXTURES_DIR)
        assert len(refs) == 1
        assert refs[0].preset_name == "empty_refs"


# --- update_sample_refs tests ---


def _copy_fixture(fixture_rel: str, tmp_path: Path) -> Path:
    """Copy a fixture file to tmp_path preserving directory structure."""
    src = FIXTURES_DIR / fixture_rel
    dest = tmp_path / fixture_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


class TestUpdateSampleRefsElementKit:
    """Round-trip tests for element-style kit."""

    def test_updates_targeted_ref(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("KITS/element_kit.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        target = refs_before[0]
        new_path = "SAMPLES/DRUMS/Kick/New Kick.wav"

        count = update_sample_refs(xml_path, {target.path: new_path})

        assert count == 1
        refs_after = extract_sample_refs(xml_path, tmp_path)
        assert len(refs_after) == len(refs_before)
        assert any(r.path == new_path for r in refs_after)
        assert not any(r.path == target.path for r in refs_after)

    def test_leaves_other_refs_unchanged(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("KITS/element_kit.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        target = refs_before[0]
        other_paths_before = {r.path for r in refs_before if r.path != target.path}

        update_sample_refs(xml_path, {target.path: "SAMPLES/NEW.wav"})

        refs_after = extract_sample_refs(xml_path, tmp_path)
        other_paths_after = {r.path for r in refs_after if r.path != "SAMPLES/NEW.wav"}
        assert other_paths_after == other_paths_before


class TestUpdateSampleRefsElementSynth:
    """Round-trip tests for element-style synth with multisamples."""

    def test_updates_targeted_ref(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("SYNTHS/element_synth_multisample.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        target = refs_before[0]
        new_path = "SAMPLES/Artists/Replaced/new.wav"

        count = update_sample_refs(xml_path, {target.path: new_path})

        assert count == 1
        refs_after = extract_sample_refs(xml_path, tmp_path)
        assert len(refs_after) == len(refs_before)
        assert any(r.path == new_path for r in refs_after)
        assert not any(r.path == target.path for r in refs_after)

    def test_leaves_other_refs_unchanged(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("SYNTHS/element_synth_multisample.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        target = refs_before[0]
        other_paths_before = {r.path for r in refs_before if r.path != target.path}

        update_sample_refs(xml_path, {target.path: "SAMPLES/NEW.wav"})

        refs_after = extract_sample_refs(xml_path, tmp_path)
        other_paths_after = {r.path for r in refs_after if r.path != "SAMPLES/NEW.wav"}
        assert other_paths_after == other_paths_before


class TestUpdateSampleRefsAttributeKit:
    """Round-trip tests for attribute-style kit."""

    def test_updates_targeted_ref(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("KITS/attribute_kit.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        target = refs_before[0]
        new_path = "SAMPLES/DRUMS/Kick/Replaced Kick.wav"

        count = update_sample_refs(xml_path, {target.path: new_path})

        assert count == 1
        refs_after = extract_sample_refs(xml_path, tmp_path)
        assert len(refs_after) == len(refs_before)
        assert any(r.path == new_path for r in refs_after)
        assert not any(r.path == target.path for r in refs_after)

    def test_leaves_other_refs_unchanged(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("KITS/attribute_kit.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        target = refs_before[0]
        other_paths_before = {r.path for r in refs_before if r.path != target.path}

        update_sample_refs(xml_path, {target.path: "SAMPLES/NEW.wav"})

        refs_after = extract_sample_refs(xml_path, tmp_path)
        other_paths_after = {r.path for r in refs_after if r.path != "SAMPLES/NEW.wav"}
        assert other_paths_after == other_paths_before


class TestUpdateSampleRefsAttributeSynth:
    """Round-trip tests for attribute-style synth with multisamples."""

    def test_updates_targeted_ref(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("SYNTHS/attribute_synth_multisample.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        target = refs_before[0]
        new_path = "SAMPLES/Artists/Replaced/new bass.WAV"

        count = update_sample_refs(xml_path, {target.path: new_path})

        assert count == 1
        refs_after = extract_sample_refs(xml_path, tmp_path)
        assert len(refs_after) == len(refs_before)
        assert any(r.path == new_path for r in refs_after)
        assert not any(r.path == target.path for r in refs_after)

    def test_leaves_other_refs_unchanged(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("SYNTHS/attribute_synth_multisample.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        target = refs_before[0]
        other_paths_before = {r.path for r in refs_before if r.path != target.path}

        update_sample_refs(xml_path, {target.path: "SAMPLES/NEW.wav"})

        refs_after = extract_sample_refs(xml_path, tmp_path)
        other_paths_after = {r.path for r in refs_after if r.path != "SAMPLES/NEW.wav"}
        assert other_paths_after == other_paths_before


class TestUpdateSampleRefsSong:
    """Round-trip tests for song with embedded instruments and audioClip."""

    def test_updates_filename_attribute_ref(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("SONGS/song_with_clips.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        kick = [r for r in refs_before if "Rhythmace Kick" in r.path][0]
        new_path = "SAMPLES/DRUMS/Kick/New Kick.wav"

        count = update_sample_refs(xml_path, {kick.path: new_path})

        assert count == 1
        refs_after = extract_sample_refs(xml_path, tmp_path)
        assert len(refs_after) == len(refs_before)
        assert any(r.path == new_path for r in refs_after)
        assert not any(r.path == kick.path for r in refs_after)

    def test_updates_filepath_attribute_ref(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("SONGS/song_with_clips.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        clip = [r for r in refs_before if "REC00040" in r.path][0]
        new_path = "SAMPLES/CLIPS/REC99999.WAV"

        count = update_sample_refs(xml_path, {clip.path: new_path})

        assert count == 1
        refs_after = extract_sample_refs(xml_path, tmp_path)
        assert any(r.path == new_path for r in refs_after)
        assert not any(r.path == clip.path for r in refs_after)

    def test_leaves_other_refs_unchanged(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("SONGS/song_with_clips.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        kick = [r for r in refs_before if "Rhythmace Kick" in r.path][0]
        other_paths_before = {r.path for r in refs_before if r.path != kick.path}

        update_sample_refs(xml_path, {kick.path: "SAMPLES/NEW.wav"})

        refs_after = extract_sample_refs(xml_path, tmp_path)
        other_paths_after = {r.path for r in refs_after if r.path != "SAMPLES/NEW.wav"}
        assert other_paths_after == other_paths_before


class TestUpdateSampleRefsEmptyRefs:
    """Round-trip tests for empty_refs fixture (one valid ref among empties)."""

    def test_updates_the_valid_ref(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("KITS/empty_refs.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        assert len(refs_before) == 1
        new_path = "SAMPLES/DRUMS/Kick/Replaced.wav"

        count = update_sample_refs(xml_path, {refs_before[0].path: new_path})

        assert count == 1
        refs_after = extract_sample_refs(xml_path, tmp_path)
        assert len(refs_after) == 1
        assert refs_after[0].path == new_path


class TestUpdateSampleRefsUnextractedKit:
    """Round-trip tests for unextracted_ref_kit fixture."""

    def test_updates_normal_ref(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("KITS/unextracted_ref_kit.xml", tmp_path)
        refs_before = extract_sample_refs(xml_path, tmp_path)
        assert len(refs_before) == 1
        new_path = "SAMPLES/DRUMS/Kick/ReplacedNormal.wav"

        count = update_sample_refs(xml_path, {refs_before[0].path: new_path})

        assert count == 1
        refs_after = extract_sample_refs(xml_path, tmp_path)
        assert len(refs_after) == 1
        assert refs_after[0].path == new_path


class TestUpdateSampleRefsNoMatch:
    """Test that non-matching mappings produce no changes."""

    def test_no_match_returns_zero(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("KITS/attribute_kit.xml", tmp_path)
        mapping = {"NONEXISTENT/path.wav": "OTHER/path.wav"}

        count = update_sample_refs(xml_path, mapping)

        assert count == 0

    def test_no_match_leaves_file_unchanged(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("KITS/attribute_kit.xml", tmp_path)
        original_bytes = xml_path.read_bytes()
        mapping = {"NONEXISTENT/path.wav": "OTHER/path.wav"}

        update_sample_refs(xml_path, mapping)

        assert xml_path.read_bytes() == original_bytes

    def test_empty_mapping(self, tmp_path: Path) -> None:
        xml_path = _copy_fixture("KITS/attribute_kit.xml", tmp_path)
        original_bytes = xml_path.read_bytes()

        count = update_sample_refs(xml_path, {})

        assert count == 0
        assert xml_path.read_bytes() == original_bytes


# --- find_unextracted_refs tests ---


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
        fixture = FIXTURES_DIR / "KITS" / "unextracted_ref_kit.xml"
        extracted = extract_sample_refs(fixture, FIXTURES_DIR)

        result = find_unextracted_refs(fixture, extracted)

        # The fixture has SAMPLES/HIDDEN/SecretSample.wav in <customData>
        # which is not a known reference pattern
        assert len(result) == 1
        assert result[0] == "SAMPLES/HIDDEN/SecretSample.wav"
