"""Tests for extraction.py — instrument extraction from Deluge song XMLs."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from deluge_lib.extraction import (
    ClipInfo,
    ExtractionResult,
    InstrumentClipGroup,
    InstrumentInfo,
    NormalisationConfig,
    VersionComparison,
    build_manifest_entry,
    compare_versions,
    discover_clips,
    discover_instruments,
    discover_songs,
    extract_kit,
    extract_synth,
    generate_filename,
    match_instruments_to_clips,
    normalise_params,
    select_default_clip,
    select_extended_clips,
    serialise_xml,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Task 1.2: Song discovery and firmware validation
# ---------------------------------------------------------------------------


class TestDiscoverSongs:
    def test_finds_xml_files_in_songs_dir(self, tmp_path: Path) -> None:
        """Should discover all *.XML files directly in SONGS/."""
        pytest.skip("Not implemented")

    def test_skips_non_c121_firmware(self, tmp_path: Path) -> None:
        """Should skip songs with firmwareVersion != c1.2.1 and print warning."""
        pytest.skip("Not implemented")

    def test_skips_unparseable_xml(self, tmp_path: Path) -> None:
        """Should skip songs that fail to parse and print warning."""
        pytest.skip("Not implemented")

    def test_returns_empty_for_no_songs(self, tmp_path: Path) -> None:
        """Should return empty list if SONGS/ has no XML files."""
        pytest.skip("Not implemented")


# ---------------------------------------------------------------------------
# Task 1.3: Instrument and clip discovery
# ---------------------------------------------------------------------------


class TestDiscoverInstruments:
    def test_discovers_synth_instruments(self) -> None:
        """Should find <sound> children of <instruments> as type='synth'."""
        song = etree.fromstring(
            b'<song><instruments>'
            b'<sound presetName="Bass" presetFolder="SYNTHS" />'
            b'</instruments></song>'
        )
        result = discover_instruments(song)
        assert len(result) == 1
        assert result[0].instrument_type == "synth"

    def test_discovers_kit_instruments(self) -> None:
        """Should find <kit> children of <instruments> as type='kit'."""
        song = etree.fromstring(
            b'<song><instruments>'
            b'<kit presetName="808" presetFolder="KITS" />'
            b'</instruments></song>'
        )
        result = discover_instruments(song)
        assert len(result) == 1
        assert result[0].instrument_type == "kit"

    def test_ignores_midi_and_audio_tracks(self) -> None:
        """Should skip <midi> and <audioTrack> elements."""
        song = etree.fromstring(
            b'<song><instruments>'
            b'<sound presetName="Lead" presetFolder="SYNTHS" />'
            b'<midi channel="1" />'
            b'<audioTrack name="Track1" />'
            b'<kit presetName="909" presetFolder="KITS" />'
            b'</instruments></song>'
        )
        result = discover_instruments(song)
        assert len(result) == 2
        assert result[0].instrument_type == "synth"
        assert result[1].instrument_type == "kit"

    def test_reads_preset_name_and_folder(self) -> None:
        """Should extract presetName and presetFolder from each instrument."""
        song = etree.fromstring(
            b'<song><instruments>'
            b'<sound presetName="K01Bass" presetFolder="SYNTHS/KERERU" />'
            b'</instruments></song>'
        )
        result = discover_instruments(song)
        assert result[0].preset_name == "K01Bass"
        assert result[0].preset_folder == "SYNTHS/KERERU"

    def test_returns_empty_for_no_instruments(self) -> None:
        """Should return empty list when <instruments> is missing."""
        song = etree.fromstring(b"<song></song>")
        result = discover_instruments(song)
        assert result == []


class TestDiscoverClips:
    def test_discovers_instrument_clips(self) -> None:
        """Should find <instrumentClip> children of <sessionClips>."""
        song = etree.fromstring(
            b'<song><sessionClips>'
            b'<instrumentClip instrumentPresetName="Bass" instrumentPresetFolder="SYNTHS" section="0" />'
            b'<instrumentClip instrumentPresetName="Lead" instrumentPresetFolder="SYNTHS" section="1" />'
            b'</sessionClips></song>'
        )
        result = discover_clips(song)
        assert len(result) == 2
        assert result[0].preset_name == "Bass"
        assert result[1].preset_name == "Lead"

    def test_reads_section_attribute(self) -> None:
        """Should read section attribute and convert to int."""
        song = etree.fromstring(
            b'<song><sessionClips>'
            b'<instrumentClip instrumentPresetName="Bass" instrumentPresetFolder="SYNTHS" section="7" />'
            b'</sessionClips></song>'
        )
        result = discover_clips(song)
        assert result[0].section == 7

    def test_missing_section_defaults_to_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should treat missing section attribute as section 0 with warning."""
        song = etree.fromstring(
            b'<song><sessionClips>'
            b'<instrumentClip instrumentPresetName="Bass" instrumentPresetFolder="SYNTHS" />'
            b'</sessionClips></song>'
        )
        result = discover_clips(song)
        assert result[0].section == 0
        captured = capsys.readouterr()
        assert "no section attribute" in captured.out

    def test_ignores_arrangement_only_clips(self) -> None:
        """Should not look in <arrangementOnlyClips>."""
        song = etree.fromstring(
            b'<song>'
            b'<sessionClips>'
            b'<instrumentClip instrumentPresetName="Bass" instrumentPresetFolder="SYNTHS" section="0" />'
            b'</sessionClips>'
            b'<arrangementOnlyClips>'
            b'<instrumentClip instrumentPresetName="Hidden" instrumentPresetFolder="SYNTHS" section="1" />'
            b'</arrangementOnlyClips>'
            b'</song>'
        )
        result = discover_clips(song)
        assert len(result) == 1
        assert result[0].preset_name == "Bass"

    def test_returns_empty_for_no_session_clips(self) -> None:
        """Should return empty list when <sessionClips> is missing."""
        song = etree.fromstring(b"<song></song>")
        result = discover_clips(song)
        assert result == []


class TestMatchInstrumentsToClips:
    def _make_instrument(
        self, name: str, folder: str, itype: str = "synth"
    ) -> InstrumentInfo:
        el = etree.Element("sound" if itype == "synth" else "kit")
        el.set("presetName", name)
        el.set("presetFolder", folder)
        return InstrumentInfo(
            element=el, instrument_type=itype, preset_name=name, preset_folder=folder
        )

    def _make_clip(self, name: str, folder: str, section: int = 0) -> ClipInfo:
        el = etree.Element("instrumentClip")
        el.set("instrumentPresetName", name)
        el.set("instrumentPresetFolder", folder)
        el.set("section", str(section))
        return ClipInfo(
            element=el, section=section, preset_name=name, preset_folder=folder
        )

    def test_matches_by_preset_name_and_folder(self) -> None:
        """Should match clips to instruments via presetName + presetFolder."""
        instruments = [self._make_instrument("Bass", "SYNTHS")]
        clips = [self._make_clip("Bass", "SYNTHS", section=0)]
        groups, warnings = match_instruments_to_clips(instruments, clips)
        assert len(groups) == 1
        assert groups[0].instrument.preset_name == "Bass"
        assert 0 in groups[0].clips_by_section

    def test_groups_clips_by_section(self) -> None:
        """Should group matched clips by section ID within each instrument."""
        instruments = [self._make_instrument("Bass", "SYNTHS")]
        clips = [
            self._make_clip("Bass", "SYNTHS", section=0),
            self._make_clip("Bass", "SYNTHS", section=3),
            self._make_clip("Bass", "SYNTHS", section=6),
        ]
        groups, warnings = match_instruments_to_clips(instruments, clips)
        assert len(groups) == 1
        assert set(groups[0].clips_by_section.keys()) == {0, 3, 6}

    def test_identifies_orphaned_instruments(self) -> None:
        """Should detect instruments with no matching clips and produce warning."""
        instruments = [self._make_instrument("Orphan", "SYNTHS")]
        clips: list[ClipInfo] = []
        groups, warnings = match_instruments_to_clips(instruments, clips)
        assert len(groups) == 0
        assert len(warnings) == 1
        assert "Orphaned instrument" in warnings[0]
        assert "'Orphan'" in warnings[0]

    def test_warns_on_duplicate_clips_in_same_section(self) -> None:
        """Should keep first clip and warn about duplicate in same section."""
        instruments = [self._make_instrument("Bass", "SYNTHS")]
        clip_a = self._make_clip("Bass", "SYNTHS", section=0)
        clip_b = self._make_clip("Bass", "SYNTHS", section=0)
        clips = [clip_a, clip_b]
        groups, warnings = match_instruments_to_clips(instruments, clips)
        assert len(groups) == 1
        # Should keep the first clip
        assert groups[0].clips_by_section[0] is clip_a
        assert len(warnings) == 1
        assert "Duplicate clip" in warnings[0]

    def test_does_not_match_different_folders(self) -> None:
        """Instruments and clips with same name but different folder should not match."""
        instruments = [self._make_instrument("Bass", "SYNTHS/A")]
        clips = [self._make_clip("Bass", "SYNTHS/B", section=0)]
        groups, warnings = match_instruments_to_clips(instruments, clips)
        assert len(groups) == 0
        assert len(warnings) == 1
        assert "Orphaned" in warnings[0]

    def test_multiple_instruments_matched_independently(self) -> None:
        """Each instrument should match its own clips independently."""
        instruments = [
            self._make_instrument("Bass", "SYNTHS"),
            self._make_instrument("808", "KITS", itype="kit"),
        ]
        clips = [
            self._make_clip("Bass", "SYNTHS", section=0),
            self._make_clip("808", "KITS", section=2),
        ]
        groups, warnings = match_instruments_to_clips(instruments, clips)
        assert len(groups) == 2
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Task 1.4: Default version selection
# ---------------------------------------------------------------------------


class TestSelectDefaultClip:
    def _make_group(self, sections: list[int]) -> InstrumentClipGroup:
        """Helper: build an InstrumentClipGroup with clips at the given section IDs."""
        inst_el = etree.Element("sound")
        inst_el.set("presetName", "Bass")
        inst_el.set("presetFolder", "SYNTHS")
        instrument = InstrumentInfo(
            element=inst_el,
            instrument_type="synth",
            preset_name="Bass",
            preset_folder="SYNTHS",
        )
        clips_by_section: dict[int, ClipInfo] = {}
        for sec in sections:
            clip_el = etree.Element("instrumentClip")
            clip_el.set("section", str(sec))
            clips_by_section[sec] = ClipInfo(
                element=clip_el,
                section=sec,
                preset_name="Bass",
                preset_folder="SYNTHS",
            )
        return InstrumentClipGroup(
            instrument=instrument,
            clips_by_section=clips_by_section,
        )

    def test_selects_lowest_section_id(self) -> None:
        """Should return the clip with the lowest section ID."""
        group = self._make_group([3, 0, 7])
        result = select_default_clip(group)
        assert result.section == 0

    def test_handles_single_clip(self) -> None:
        """Should return the only clip when instrument has one clip."""
        group = self._make_group([5])
        result = select_default_clip(group)
        assert result.section == 5

    def test_returns_clipinfo_dataclass(self) -> None:
        """Should return a ClipInfo instance with correct fields."""
        group = self._make_group([2, 8])
        result = select_default_clip(group)
        assert isinstance(result, ClipInfo)
        assert result.section == 2
        assert result.preset_name == "Bass"
        assert result.preset_folder == "SYNTHS"


# ---------------------------------------------------------------------------
# Task 2.1: Synth extraction transformation
# ---------------------------------------------------------------------------


class TestExtractSynth:
    """Tests for extract_synth() — Task 2.1."""

    @staticmethod
    def _make_embedded_synth(**extra_attrs: str) -> etree._Element:
        """Build a minimal embedded <sound> element mimicking song XML structure."""
        attrs = {
            "presetName": "Bass",
            "presetFolder": "SYNTHS",
            "defaultVelocity": "64",
            "isArmedForRecording": "0",
            "activeModFunction": "0",
            "colour": "4",
        }
        attrs.update(extra_attrs)
        sound = etree.Element("sound", attrib=attrs)
        sound.set("polyphonic", "1")
        sound.set("mode", "subtractive")
        etree.SubElement(sound, "osc1", type="saw")
        etree.SubElement(sound, "osc2", type="square")
        etree.SubElement(sound, "lfo1", type="sine")
        etree.SubElement(sound, "lfo2", type="sine")
        etree.SubElement(sound, "unison", num="4", detune="10")
        etree.SubElement(sound, "modKnobs")
        etree.SubElement(sound, "delay", pingPong="1")
        etree.SubElement(sound, "sidechain")
        etree.SubElement(sound, "audioCompressor")
        return sound

    @staticmethod
    def _make_clip(
        *,
        sound_params_attrs: dict[str, str] | None = None,
        arp_attrs: dict[str, str] | None = None,
        sound_params_children: list[etree._Element] | None = None,
    ) -> etree._Element:
        """Build a minimal <instrumentClip> with <soundParams> and optional <arpeggiator>."""
        clip = etree.Element("instrumentClip", section="0")

        if arp_attrs is not None:
            etree.SubElement(clip, "arpeggiator", **arp_attrs)

        sp = etree.SubElement(clip, "soundParams", **(sound_params_attrs or {}))
        if sound_params_children:
            for child in sound_params_children:
                sp.append(child)
        return clip

    def test_does_not_mutate_original(self) -> None:
        """Should deep-clone the instrument element, not modify the original tree."""
        instrument = self._make_embedded_synth()
        clip = self._make_clip(arp_attrs={"mode": "off"})
        original_xml = etree.tostring(instrument)
        extract_synth(instrument, clip)
        assert etree.tostring(instrument) == original_xml

    def test_strips_song_specific_attrs(self) -> None:
        """Should remove presetName, presetFolder, defaultVelocity, etc."""
        instrument = self._make_embedded_synth()
        clip = self._make_clip(arp_attrs={"mode": "off"})
        result = extract_synth(instrument, clip)
        for attr in (
            "presetName", "presetFolder", "defaultVelocity",
            "isArmedForRecording", "activeModFunction", "colour",
        ):
            assert attr not in result.attrib, f"{attr} should be stripped"

    def test_adds_firmware_version_attrs(self) -> None:
        """Should add firmwareVersion and earliestCompatibleFirmware."""
        instrument = self._make_embedded_synth()
        clip = self._make_clip(arp_attrs={"mode": "off"})
        result = extract_synth(instrument, clip)
        assert result.get("firmwareVersion") == "c1.2.1"
        assert result.get("earliestCompatibleFirmware") == "4.1.0-alpha"

    def test_renames_soundparams_to_defaultparams(self) -> None:
        """Should extract <soundParams> from clip and rename to <defaultParams>."""
        instrument = self._make_embedded_synth()
        clip = self._make_clip(
            sound_params_attrs={"volume": "0x50000000", "pan": "0x00000000"},
            arp_attrs={"mode": "off"},
        )
        result = extract_synth(instrument, clip)
        dp = result.find("defaultParams")
        assert dp is not None, "Should have <defaultParams>"
        assert dp.get("volume") == "0x50000000"
        assert dp.get("pan") == "0x00000000"
        # Should NOT have a <soundParams> child
        assert result.find("soundParams") is None

    def test_extracts_arpeggiator_from_clip(self) -> None:
        """Should extract <arpeggiator> from clip into the standalone synth."""
        instrument = self._make_embedded_synth()
        clip = self._make_clip(arp_attrs={"mode": "arp", "syncLevel": "7"})
        result = extract_synth(instrument, clip)
        arp = result.find("arpeggiator")
        assert arp is not None, "Should have <arpeggiator>"
        assert arp.get("mode") == "arp"
        assert arp.get("syncLevel") == "7"

    def test_strips_extra_arpeggiator_attrs(self) -> None:
        """Should strip gate, rate, ratchetProbability, etc. from arpeggiator."""
        instrument = self._make_embedded_synth()
        clip = self._make_clip(arp_attrs={
            "mode": "arp",
            "gate": "0x40000000",
            "rate": "0x20000000",
            "ratchetProbability": "0x00000000",
            "ratchetAmount": "0x00000000",
            "sequenceLength": "0x00000000",
            "rhythm": "0x00000000",
        })
        result = extract_synth(instrument, clip)
        arp = result.find("arpeggiator")
        assert arp is not None
        assert arp.get("mode") == "arp"
        for attr in ("gate", "rate", "ratchetProbability", "ratchetAmount",
                      "sequenceLength", "rhythm"):
            assert attr not in arp.attrib, f"{attr} should be stripped from arpeggiator"

    def test_correct_child_element_order(self) -> None:
        """Should reorder children: osc1, osc2, lfo, unison, defaultParams, arp, modKnobs, delay..."""
        instrument = self._make_embedded_synth()
        clip = self._make_clip(
            sound_params_attrs={"volume": "0x50000000"},
            arp_attrs={"mode": "off"},
        )
        result = extract_synth(instrument, clip)
        tags = [child.tag for child in result]
        expected = [
            "osc1", "osc2", "lfo1", "lfo2", "unison",
            "defaultParams", "arpeggiator", "modKnobs",
            "delay", "sidechain", "audioCompressor",
        ]
        assert tags == expected

    def test_preserves_automation_hex_strings(self) -> None:
        """Should preserve extended hex automation strings verbatim."""
        instrument = self._make_embedded_synth()
        long_hex = "0x50000000 0x60000000 0x70000000 0x7FFFFFFF"
        clip = self._make_clip(
            sound_params_attrs={"volume": long_hex},
            arp_attrs={"mode": "off"},
        )
        result = extract_synth(instrument, clip)
        dp = result.find("defaultParams")
        assert dp is not None
        assert dp.get("volume") == long_hex

    def test_preserves_defaultparams_children(self) -> None:
        """Should keep envelope1, envelope2, patchCables, equalizer in defaultParams."""
        instrument = self._make_embedded_synth()
        env1 = etree.Element("envelope1", attack="0x80000000", decay="0xE6666654")
        env2 = etree.Element("envelope2", attack="0xA3D70A37")
        patch_cables = etree.SubElement(etree.Element("patchCables"), "patchCable")
        pc_parent = patch_cables.getparent()
        equalizer = etree.Element("equalizer", bass="0x00000000")
        clip = self._make_clip(
            sound_params_attrs={"volume": "0x50000000"},
            arp_attrs={"mode": "off"},
            sound_params_children=[env1, env2, pc_parent, equalizer],
        )
        result = extract_synth(instrument, clip)
        dp = result.find("defaultParams")
        assert dp is not None
        assert dp.find("envelope1") is not None
        assert dp.find("envelope2") is not None
        assert dp.find("patchCables") is not None
        assert dp.find("equalizer") is not None
        # Verify attribute values preserved
        assert dp.find("envelope1").get("attack") == "0x80000000"

    def test_handles_fm_mode_with_modulators(self) -> None:
        """Should include modulator1/modulator2 for FM synths."""
        instrument = self._make_embedded_synth()
        # Insert modulators between lfo2 and unison (FM mode)
        lfo2 = instrument.find("lfo2")
        lfo2_idx = list(instrument).index(lfo2)
        mod1 = etree.Element("modulator1", transpose="0", cents="0")
        mod2 = etree.Element("modulator2", transpose="0", cents="0")
        instrument.insert(lfo2_idx + 1, mod1)
        instrument.insert(lfo2_idx + 2, mod2)

        clip = self._make_clip(
            sound_params_attrs={"volume": "0x50000000"},
            arp_attrs={"mode": "off"},
        )
        result = extract_synth(instrument, clip)
        tags = [child.tag for child in result]
        expected = [
            "osc1", "osc2", "lfo1", "lfo2",
            "modulator1", "modulator2",
            "unison", "defaultParams", "arpeggiator", "modKnobs",
            "delay", "sidechain", "audioCompressor",
        ]
        assert tags == expected


# ---------------------------------------------------------------------------
# Task 2.2: Kit extraction transformation
# ---------------------------------------------------------------------------


class TestExtractKit:
    """Tests for extract_kit() — Task 2.2."""

    @staticmethod
    def _make_embedded_kit(**extra_attrs: str) -> etree._Element:
        """Build a minimal embedded <kit> element mimicking song XML structure."""
        attrs = {
            "presetName": "808",
            "presetFolder": "KITS",
            "defaultVelocity": "64",
            "isArmedForRecording": "0",
            "activeModFunction": "0",
            "colour": "2",
        }
        attrs.update(extra_attrs)
        kit = etree.Element("kit", attrib=attrs)
        etree.SubElement(kit, "delay", pingPong="1")
        etree.SubElement(kit, "sidechain")
        etree.SubElement(kit, "audioCompressor")
        sound_sources = etree.SubElement(kit, "soundSources")
        # Add two sounds (kit rows)
        for i in range(2):
            sound = etree.SubElement(sound_sources, "sound")
            etree.SubElement(sound, "osc1", type="sample")
            etree.SubElement(sound, "osc2", type="square")
            etree.SubElement(sound, "lfo1", type="sine")
            etree.SubElement(sound, "lfo2", type="sine")
            etree.SubElement(sound, "unison", num="1", detune="0")
            etree.SubElement(sound, "arpeggiator", mode="off")
            etree.SubElement(sound, "modKnobs")
            etree.SubElement(sound, "delay", pingPong="0")
            etree.SubElement(sound, "sidechain")
            etree.SubElement(sound, "audioCompressor")
        etree.SubElement(kit, "selectedDrumIndex", value="0")
        return kit

    @staticmethod
    def _make_kit_clip(
        *,
        kit_params_attrs: dict[str, str] | None = None,
        noterows: list[tuple[int, dict[str, str]]] | None = None,
    ) -> etree._Element:
        """Build a minimal <instrumentClip> with <kitParams> and optional noteRows.

        noterows: list of (drumIndex, soundParams_attrs) tuples.
        """
        clip = etree.Element("instrumentClip", section="0")
        etree.SubElement(clip, "kitParams", **(kit_params_attrs or {}))
        if noterows is not None:
            note_rows_el = etree.SubElement(clip, "noteRows")
            for drum_index, sp_attrs in noterows:
                nr = etree.SubElement(note_rows_el, "noteRow", drumIndex=str(drum_index))
                etree.SubElement(nr, "soundParams", **sp_attrs)
        return clip

    def test_does_not_mutate_original(self) -> None:
        """Should deep-clone the kit element, not modify the original tree."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip()
        original_xml = etree.tostring(instrument)
        extract_kit(instrument, clip)
        assert etree.tostring(instrument) == original_xml

    def test_strips_song_specific_attrs(self) -> None:
        """Should remove presetName, presetFolder, defaultVelocity, etc."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip()
        result = extract_kit(instrument, clip)
        for attr in (
            "presetName", "presetFolder", "defaultVelocity",
            "isArmedForRecording", "activeModFunction", "colour",
        ):
            assert attr not in result.attrib, f"{attr} should be stripped"

    def test_adds_firmware_version_attrs(self) -> None:
        """Should add firmwareVersion and earliestCompatibleFirmware."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip()
        result = extract_kit(instrument, clip)
        assert result.get("firmwareVersion") == "c1.2.1"
        assert result.get("earliestCompatibleFirmware") == "4.1.0-alpha"

    def test_renames_kitparams_to_defaultparams(self) -> None:
        """Should extract <kitParams> from clip and rename to <defaultParams>."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            kit_params_attrs={"volume": "0x50000000", "pan": "0x00000000"},
        )
        result = extract_kit(instrument, clip)
        dp = result.find("defaultParams")
        assert dp is not None, "Should have <defaultParams>"
        assert dp.get("volume") == "0x50000000"
        assert dp.get("pan") == "0x00000000"

    def test_inserts_kit_defaultparams_as_first_child(self) -> None:
        """Should insert kit-level <defaultParams> before <delay>."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            kit_params_attrs={"volume": "0x50000000"},
        )
        result = extract_kit(instrument, clip)
        children = list(result)
        assert children[0].tag == "defaultParams"

    def test_merges_noterow_params_into_sounds(self) -> None:
        """Should rename each noteRow's <soundParams> to <defaultParams> and insert into matching sound."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            noterows=[
                (0, {"volume": "0xAAAAAAAA", "pan": "0x11111111"}),
                (1, {"volume": "0xBBBBBBBB", "pan": "0x22222222"}),
            ],
        )
        result = extract_kit(instrument, clip)
        sound_sources = result.find("soundSources")
        sounds = list(sound_sources)
        # Sound 0 should have <defaultParams> with the first noteRow's values
        dp0 = sounds[0].find("defaultParams")
        assert dp0 is not None
        assert dp0.get("volume") == "0xAAAAAAAA"
        assert dp0.get("pan") == "0x11111111"
        # Sound 1 should have <defaultParams> with the second noteRow's values
        dp1 = sounds[1].find("defaultParams")
        assert dp1 is not None
        assert dp1.get("volume") == "0xBBBBBBBB"

    def test_matches_noterow_by_drumindex(self) -> None:
        """Should use drumIndex as 0-based index into <soundSources>."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            noterows=[
                (1, {"volume": "0xCCCCCCCC"}),  # Only drum index 1
            ],
        )
        result = extract_kit(instrument, clip)
        sound_sources = result.find("soundSources")
        sounds = list(sound_sources)
        # Sound 0 should NOT have <defaultParams>
        assert sounds[0].find("defaultParams") is None
        # Sound 1 should have <defaultParams>
        dp1 = sounds[1].find("defaultParams")
        assert dp1 is not None
        assert dp1.get("volume") == "0xCCCCCCCC"

    def test_warns_on_invalid_drumindex(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should warn and skip noteRows with out-of-range drumIndex."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            noterows=[
                (99, {"volume": "0xDDDDDDDD"}),
            ],
        )
        result = extract_kit(instrument, clip)
        captured = capsys.readouterr()
        assert "drumIndex 99 out of range" in captured.out
        # No sound should have defaultParams from the invalid noteRow
        sound_sources = result.find("soundSources")
        for sound in sound_sources:
            assert sound.find("defaultParams") is None

    def test_kit_arpeggiator_stays_in_place(self) -> None:
        """Should leave kit sound <arpeggiator> elements untouched."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            noterows=[(0, {"volume": "0xAAAAAAAA"})],
        )
        result = extract_kit(instrument, clip)
        sound_sources = result.find("soundSources")
        sound0 = list(sound_sources)[0]
        arp = sound0.find("arpeggiator")
        assert arp is not None
        assert arp.get("mode") == "off"

    def test_correct_kit_level_element_order(self) -> None:
        """Should order: defaultParams, delay, sidechain, audioCompressor, soundSources, selectedDrumIndex."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            kit_params_attrs={"volume": "0x50000000"},
        )
        result = extract_kit(instrument, clip)
        tags = [child.tag for child in result]
        expected = [
            "defaultParams", "delay", "sidechain", "audioCompressor",
            "soundSources", "selectedDrumIndex",
        ]
        assert tags == expected

    def test_correct_kit_sound_element_order(self) -> None:
        """Should order per-row: osc1, osc2, lfo, unison, defaultParams, arp, modKnobs, delay..."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            noterows=[(0, {"volume": "0xAAAAAAAA"})],
        )
        result = extract_kit(instrument, clip)
        sound_sources = result.find("soundSources")
        sound0 = list(sound_sources)[0]
        tags = [child.tag for child in sound0]
        expected = [
            "osc1", "osc2", "lfo1", "lfo2", "unison",
            "defaultParams", "arpeggiator", "modKnobs",
            "delay", "sidechain", "audioCompressor",
        ]
        assert tags == expected


# ---------------------------------------------------------------------------
# Task 2.3: Volume and pan normalisation
# ---------------------------------------------------------------------------


class TestNormaliseParams:
    """Tests for normalise_params() — Task 2.3."""

    @staticmethod
    def _make_synth_with_params(volume: str = "0x50000000", pan: str = "0x10000000") -> etree._Element:
        """Build a minimal standalone <sound> with <defaultParams>."""
        sound = etree.Element("sound", firmwareVersion="c1.2.1")
        dp = etree.SubElement(sound, "defaultParams", volume=volume, pan=pan)
        pc_el = etree.SubElement(dp, "patchCables")
        etree.SubElement(pc_el, "patchCable", source="velocity", destination="volume", amount="0x3FFFFFE8")
        return sound

    @staticmethod
    def _make_kit_with_params(
        kit_volume: str = "0x50000000",
        kit_pan: str = "0x10000000",
        row_volume: str = "0xAAAAAAAA",
        row_pan: str = "0xBBBBBBBB",
    ) -> etree._Element:
        """Build a minimal standalone <kit> with kit-level and row-level <defaultParams>."""
        kit = etree.Element("kit", firmwareVersion="c1.2.1")
        etree.SubElement(kit, "defaultParams", volume=kit_volume, pan=kit_pan)
        sound_sources = etree.SubElement(kit, "soundSources")
        sound = etree.SubElement(sound_sources, "sound")
        etree.SubElement(sound, "defaultParams", volume=row_volume, pan=row_pan)
        return kit

    def test_synth_volume_normalised(self) -> None:
        """Should set synth <defaultParams> volume to init synth value."""
        sound = self._make_synth_with_params(volume="0x60000000")
        normalise_params(sound, "synth", NormalisationConfig())
        dp = sound.find("defaultParams")
        assert dp is not None
        assert dp.get("volume") == "0x4CCCCCA8"

    def test_kit_volume_normalised(self) -> None:
        """Should set kit <defaultParams> volume to init kit value."""
        kit = self._make_kit_with_params(kit_volume="0x60000000")
        normalise_params(kit, "kit", NormalisationConfig())
        dp = kit.find("defaultParams")
        assert dp is not None
        assert dp.get("volume") == "0x3504F334"

    def test_pan_normalised_to_centre(self) -> None:
        """Should set pan to 0x00000000 for both types."""
        sound = self._make_synth_with_params(pan="0x20000000")
        normalise_params(sound, "synth", NormalisationConfig())
        dp = sound.find("defaultParams")
        assert dp is not None
        assert dp.get("pan") == "0x00000000"

        kit = self._make_kit_with_params(kit_pan="0x30000000")
        normalise_params(kit, "kit", NormalisationConfig())
        dp_kit = kit.find("defaultParams")
        assert dp_kit is not None
        assert dp_kit.get("pan") == "0x00000000"

    def test_kit_row_volume_preserved(self) -> None:
        """Should NOT modify volume on kit row <defaultParams> in <soundSources>."""
        kit = self._make_kit_with_params(row_volume="0xAAAAAAAA")
        normalise_params(kit, "kit", NormalisationConfig())
        row_dp = kit.find("soundSources/sound/defaultParams")
        assert row_dp is not None
        assert row_dp.get("volume") == "0xAAAAAAAA"

    def test_kit_row_pan_preserved(self) -> None:
        """Should NOT modify pan on kit row <defaultParams> in <soundSources>."""
        kit = self._make_kit_with_params(row_pan="0xBBBBBBBB")
        normalise_params(kit, "kit", NormalisationConfig())
        row_dp = kit.find("soundSources/sound/defaultParams")
        assert row_dp is not None
        assert row_dp.get("pan") == "0xBBBBBBBB"

    def test_patchcable_volume_untouched(self) -> None:
        """Should NOT modify <patchCable> entries with destination='volume'."""
        sound = self._make_synth_with_params()
        normalise_params(sound, "synth", NormalisationConfig())
        pc = sound.find("defaultParams/patchCables/patchCable")
        assert pc is not None
        assert pc.get("destination") == "volume"
        assert pc.get("amount") == "0x3FFFFFE8"


# ---------------------------------------------------------------------------
# Task 3.1: Filename generation
# ---------------------------------------------------------------------------


class TestGenerateFilename:
    def test_default_mode_format(self) -> None:
        """Default mode: <SongName>-<PresetName>.XML."""
        used: set[str] = set()
        result = generate_filename("Bloop", "133", "synth", 0, False, used)
        assert result == "Bloop-133.XML"
        assert "Bloop-133.XML" in used

    def test_extended_mode_format(self) -> None:
        """Extended mode: <SongName>-<PresetName>-<Abbr>.XML."""
        used: set[str] = set()
        result = generate_filename("Bloop", "133", "synth", 0, True, used)
        assert result == "Bloop-133-Lbl.XML"
        assert "Bloop-133-Lbl.XML" in used

    def test_colour_abbreviation_mapping(self) -> None:
        """Should use correct 3-letter abbreviation for each section ID."""
        from deluge_lib.extraction import SECTION_COLOURS

        for section_id, (_name, abbr) in SECTION_COLOURS.items():
            used: set[str] = set()
            result = generate_filename("Song", "Preset", "synth", section_id, True, used)
            assert result == f"Song-Preset-{abbr}.XML"

    def test_collision_appends_number(self) -> None:
        """Should append -2, -3 etc. on filename collision."""
        used: set[str] = {"Bloop-133.XML"}
        result = generate_filename("Bloop", "133", "synth", 0, False, used)
        assert result == "Bloop-133-2.XML"
        assert "Bloop-133-2.XML" in used

        # Third collision
        result2 = generate_filename("Bloop", "133", "synth", 0, False, used)
        assert result2 == "Bloop-133-3.XML"

    def test_preserves_spaces_and_hyphens(self) -> None:
        """Should keep spaces and hyphens in names."""
        used: set[str] = set()
        result = generate_filename("My Song", "Rich Saw-Bass", "synth", 0, False, used)
        assert result == "My Song-Rich Saw-Bass.XML"


# ---------------------------------------------------------------------------
# Task 3.2: XML serialisation
# ---------------------------------------------------------------------------


class TestSerialiseXml:
    def test_writes_xml_declaration(self, tmp_path: Path) -> None:
        """Should write <?xml version='1.0' encoding='UTF-8'?> header."""
        el = etree.Element("sound", firmwareVersion="c1.2.1")
        out = tmp_path / "test.XML"
        serialise_xml(el, out)
        content = out.read_bytes()
        assert content.startswith(b"<?xml version='1.0' encoding='UTF-8'?>")

    def test_output_matches_standalone_format(self, tmp_path: Path) -> None:
        """Should produce well-formed XML with pretty printing and parent dirs created."""
        el = etree.Element("sound", firmwareVersion="c1.2.1")
        etree.SubElement(el, "osc1", type="saw")
        etree.SubElement(el, "defaultParams", volume="0x50000000")
        out = tmp_path / "sub" / "dir" / "test.XML"
        serialise_xml(el, out)
        assert out.is_file()
        content = out.read_bytes()
        # Should contain the root element and children
        assert b"<sound" in content
        assert b"<osc1" in content
        assert b"<defaultParams" in content
        # Pretty-print should produce newlines between elements
        assert b"\n" in content


# ---------------------------------------------------------------------------
# Task 4.1: Version comparison (extended mode)
# ---------------------------------------------------------------------------


class TestCompareVersions:
    def test_identical_versions_not_distinct(self) -> None:
        """Two clips with identical params should not be distinct."""
        pytest.skip("Not implemented")

    def test_structural_change_always_distinct(self) -> None:
        """Any structural change (osc type, filter mode) → distinct."""
        pytest.skip("Not implemented")

    def test_non_numerical_change_always_distinct(self) -> None:
        """Non-numerical changes in envelopes, patchCables, arpeggiator → distinct."""
        pytest.skip("Not implemented")

    def test_numerical_below_threshold_not_distinct(self) -> None:
        """Fewer than threshold numerical param changes → not distinct."""
        pytest.skip("Not implemented")

    def test_numerical_above_threshold_distinct(self) -> None:
        """At or above threshold numerical param changes → distinct."""
        pytest.skip("Not implemented")

    def test_ignores_volume_and_pan(self) -> None:
        """Should exclude volume and pan from numerical comparison."""
        pytest.skip("Not implemented")

    def test_ignores_automation_data(self) -> None:
        """Should use first hex value only for extended automation strings."""
        pytest.skip("Not implemented")


# ---------------------------------------------------------------------------
# Task 4.2: Extended mode multi-version selection
# ---------------------------------------------------------------------------


class TestSelectExtendedClips:
    def test_baseline_always_included(self) -> None:
        """Lowest section ID clip is always in the result."""
        pytest.skip("Not implemented")

    def test_distinct_versions_included(self) -> None:
        """Clips that are distinct from baseline should be included."""
        pytest.skip("Not implemented")

    def test_non_distinct_versions_excluded(self) -> None:
        """Clips that are not distinct from baseline should be excluded."""
        pytest.skip("Not implemented")


# ---------------------------------------------------------------------------
# Task 5.2: Firmware validation
# ---------------------------------------------------------------------------


class TestFirmwareValidation:
    def test_c121_accepted(self, tmp_path: Path) -> None:
        """Songs with firmwareVersion='c1.2.1' should be accepted."""
        pytest.skip("Not implemented")

    def test_other_firmware_skipped(self, tmp_path: Path) -> None:
        """Songs with other firmware versions should be skipped with warning."""
        pytest.skip("Not implemented")


# ---------------------------------------------------------------------------
# Task 5.2: Arpeggiator handling
# ---------------------------------------------------------------------------


class TestArpeggiatorHandling:
    def test_synth_arpeggiator_extracted_from_clip(self) -> None:
        """Synth clips should have arpeggiator extracted from <instrumentClip>."""
        pytest.skip("Not implemented")

    def test_extra_arpeggiator_attrs_stripped(self) -> None:
        """Extra numeric attrs (gate, rate, etc.) should be stripped from arpeggiator."""
        pytest.skip("Not implemented")

    def test_kit_arpeggiator_left_in_instrument(self) -> None:
        """Kit sound arpeggiators should remain in the instrument definition."""
        pytest.skip("Not implemented")
