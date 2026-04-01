"""Tests for deluge_sdk.py — XML discovery and reference extraction."""

from pathlib import Path

from lib.deluge_sdk import (
    detect_xml_type,
    extract_sample_refs,
    find_all_xml_files,
)

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

    def test_returns_absolute_paths(self, tmp_path: Path) -> None:
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text("<kit/>")

        result = find_all_xml_files(tmp_path)
        assert all(p.is_absolute() for p in result)

    def test_sorted_output(self, tmp_path: Path) -> None:
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "B.XML").write_text("<kit/>")
        (kits / "A.XML").write_text("<kit/>")

        result = find_all_xml_files(tmp_path)
        assert result == sorted(result)

    def test_ignores_non_xml_files(self, tmp_path: Path) -> None:
        kits = tmp_path / "KITS"
        kits.mkdir()
        (kits / "test.XML").write_text("<kit/>")
        (kits / "readme.txt").write_text("not xml")
        (kits / "data.json").write_text("{}")

        result = find_all_xml_files(tmp_path)
        assert len(result) == 1


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

    def test_element_kit_count(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/element_kit.xml", FIXTURES_DIR)
        assert len(refs) == 2

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

    def test_element_synth_multisample_count(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SYNTHS/element_synth_multisample.xml", FIXTURES_DIR)
        assert len(refs) == 2

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

    def test_attribute_kit_count(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/attribute_kit.xml", FIXTURES_DIR)
        assert len(refs) == 3

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

    def test_attribute_synth_multisample_count(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SYNTHS/attribute_synth_multisample.xml", FIXTURES_DIR)
        assert len(refs) == 2

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

    def test_song_count(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SONGS/song_with_clips.xml", FIXTURES_DIR)
        assert len(refs) == 4

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

    def test_empty_refs_count(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/empty_refs.xml", FIXTURES_DIR)
        assert len(refs) == 1

    def test_empty_refs_valid_path(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/empty_refs.xml", FIXTURES_DIR)
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
    def test_standalone_kit_uses_filename(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/element_kit.xml", FIXTURES_DIR)
        for ref in refs:
            assert ref.preset_name == "element_kit"

    def test_standalone_synth_uses_filename(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SYNTHS/element_synth_multisample.xml", FIXTURES_DIR)
        for ref in refs:
            assert ref.preset_name == "element_synth_multisample"

    def test_attribute_kit_uses_filename(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "KITS/attribute_kit.xml", FIXTURES_DIR)
        for ref in refs:
            assert ref.preset_name == "attribute_kit"

    def test_attribute_synth_uses_filename(self) -> None:
        refs = extract_sample_refs(FIXTURES_DIR / "SYNTHS/attribute_synth_multisample.xml", FIXTURES_DIR)
        for ref in refs:
            assert ref.preset_name == "attribute_synth_multisample"

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
