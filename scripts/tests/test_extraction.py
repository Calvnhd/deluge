"""Tests for extraction.py — instrument extraction from Deluge song XMLs."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from deluge_lib.extraction import (
    ClipInfo,
    ComparisonConfig,
    ComparisonResult,
    DedupResult,
    ExtractionResult,
    InstrumentClipGroup,
    InstrumentInfo,
    NormalisationConfig,
    RejectedResult,
    SIDECHAIN_LOW_VOLUME_THRESHOLD,
    SIDECHAIN_SEND_MAX,
    SIDECHAIN_SEND_THRESHOLD,
    _strip_automation,
    build_manifest_entry,
    compare_instruments,
    deduplicate_results,
    discover_clips,
    discover_instruments,
    discover_songs,
    extract_kit,
    extract_synth,
    generate_filename,
    is_sidechain_kit,
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
        assert "no clips in session or arrangement view" in warnings[0]

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
        assert "no clips in session or arrangement view" in warnings[0]

    def test_orphan_with_arrangement_clip_shows_arrangement_only_message(self) -> None:
        """When an instrument has no session clips but exists in arrangementOnlyClips."""
        instruments = [self._make_instrument("Pad", "SYNTHS")]
        clips: list[ClipInfo] = []
        # Build a song_tree with arrangementOnlyClips referencing the instrument
        song_tree = etree.fromstring(
            b'<song>'
            b'<sessionClips></sessionClips>'
            b'<arrangementOnlyClips>'
            b'<instrumentClip instrumentPresetName="Pad" instrumentPresetFolder="SYNTHS" section="0" />'
            b'</arrangementOnlyClips>'
            b'</song>'
        )
        groups, warnings = match_instruments_to_clips(instruments, clips, song_tree=song_tree)
        assert len(groups) == 0
        assert len(warnings) == 1
        assert "arrangement-only clips" in warnings[0]
        assert "'Pad'" in warnings[0]
        assert "Orphaned" not in warnings[0]

    def test_orphan_without_arrangement_clip_shows_orphaned_message(self) -> None:
        """When an instrument has no clips in session or arrangement views."""
        instruments = [self._make_instrument("Ghost", "SYNTHS")]
        clips: list[ClipInfo] = []
        song_tree = etree.fromstring(
            b'<song>'
            b'<sessionClips></sessionClips>'
            b'<arrangementOnlyClips></arrangementOnlyClips>'
            b'</song>'
        )
        groups, warnings = match_instruments_to_clips(instruments, clips, song_tree=song_tree)
        assert len(groups) == 0
        assert len(warnings) == 1
        assert "Orphaned instrument" in warnings[0]
        assert "no clips in session or arrangement view" in warnings[0]

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
        result, _ = extract_kit(instrument, clip)
        for attr in (
            "presetName", "presetFolder", "defaultVelocity",
            "isArmedForRecording", "activeModFunction", "colour",
        ):
            assert attr not in result.attrib, f"{attr} should be stripped"

    def test_adds_firmware_version_attrs(self) -> None:
        """Should add firmwareVersion and earliestCompatibleFirmware."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip()
        result, _ = extract_kit(instrument, clip)
        assert result.get("firmwareVersion") == "c1.2.1"
        assert result.get("earliestCompatibleFirmware") == "4.1.0-alpha"

    def test_renames_kitparams_to_defaultparams(self) -> None:
        """Should extract <kitParams> from clip and rename to <defaultParams>."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            kit_params_attrs={"volume": "0x50000000", "pan": "0x00000000"},
        )
        result, _ = extract_kit(instrument, clip)
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
        result, _ = extract_kit(instrument, clip)
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
        result, _ = extract_kit(instrument, clip)
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
        result, _ = extract_kit(instrument, clip)
        sound_sources = result.find("soundSources")
        sounds = list(sound_sources)
        # Sound 0 should have <defaultParams> from the safety pass (cloned defaults)
        dp0 = sounds[0].find("defaultParams")
        assert dp0 is not None
        # Sound 1 should have <defaultParams> from the noteRow merge
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
        result, _ = extract_kit(instrument, clip)
        captured = capsys.readouterr()
        assert "drumIndex 99 out of range" in captured.out
        # Sounds should still have <defaultParams> from the safety pass,
        # but NOT the invalid noteRow's values
        sound_sources = result.find("soundSources")
        for sound in sound_sources:
            dp = sound.find("defaultParams")
            assert dp is not None, "Safety pass should provide defaultParams"
            assert dp.get("volume") != "0xDDDDDDDD", (
                "Invalid noteRow values should not appear"
            )

    def test_kit_arpeggiator_stays_in_place(self) -> None:
        """Should leave kit sound <arpeggiator> elements untouched."""
        instrument = self._make_embedded_kit()
        clip = self._make_kit_clip(
            noterows=[(0, {"volume": "0xAAAAAAAA"})],
        )
        result, _ = extract_kit(instrument, clip)
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
        result, _ = extract_kit(instrument, clip)
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
        result, _ = extract_kit(instrument, clip)
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
# Kit extraction: defaultParams safety pass
# ---------------------------------------------------------------------------


class TestKitDefaultParamsSafetyPass:
    """Tests for the safety pass that ensures all kit sounds have <defaultParams>."""

    @staticmethod
    def _make_embedded_kit(num_sounds: int = 3, sound_names: list[str] | None = None) -> etree._Element:
        """Build a kit with the given number of sounds, none having <defaultParams>."""
        kit = etree.Element(
            "kit",
            presetName="TestKit",
            presetFolder="KITS",
        )
        etree.SubElement(kit, "delay", pingPong="1")
        etree.SubElement(kit, "sidechain")
        etree.SubElement(kit, "audioCompressor")
        sound_sources = etree.SubElement(kit, "soundSources")
        names = sound_names or [f"U{i + 1}" for i in range(num_sounds)]
        for name in names:
            sound = etree.SubElement(sound_sources, "sound", name=name)
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
        kit_params_attrs: dict[str, str] | None = None,
        noterows: list[tuple[int, dict[str, str]]] | None = None,
    ) -> etree._Element:
        clip = etree.Element("instrumentClip", section="0")
        etree.SubElement(clip, "kitParams", **(kit_params_attrs or {}))
        if noterows is not None:
            note_rows_el = etree.SubElement(clip, "noteRows")
            for drum_index, sp_attrs in noterows:
                nr = etree.SubElement(note_rows_el, "noteRow", drumIndex=str(drum_index))
                etree.SubElement(nr, "soundParams", **sp_attrs)
        return clip

    def test_sound_without_noterow_gets_default_params(self) -> None:
        """A sound with no matching noteRow should still get <defaultParams> after extraction."""
        kit = self._make_embedded_kit(num_sounds=3)
        # Only provide noteRow for sound 0 — sounds 1 and 2 have no noteRow
        clip = self._make_kit_clip(
            noterows=[(0, {"volume": "0xAAAAAAAA", "pan": "0x00000000"})],
        )
        result, _ = extract_kit(kit, clip)
        sound_sources = result.find("soundSources")
        sounds = list(sound_sources)

        # All three sounds must have <defaultParams>
        for i, sound in enumerate(sounds):
            dp = sound.find("defaultParams")
            assert dp is not None, f"Sound {i} should have <defaultParams>"

        # Sound 0 should have its own values from the noteRow
        assert sounds[0].find("defaultParams").get("volume") == "0xAAAAAAAA"

    def test_default_params_cloned_from_sibling(self) -> None:
        """Sounds getting defaults should clone from a sibling that has <defaultParams>."""
        kit = self._make_embedded_kit(num_sounds=2)
        clip = self._make_kit_clip(
            noterows=[(0, {"volume": "0xBBBBBBBB", "pan": "0x11111111"})],
        )
        result, _ = extract_kit(kit, clip)
        sound_sources = result.find("soundSources")
        sounds = list(sound_sources)

        # Sound 1's <defaultParams> should be a clone of sound 0's
        dp0 = sounds[0].find("defaultParams")
        dp1 = sounds[1].find("defaultParams")
        assert dp1 is not None
        assert dp1.get("volume") == dp0.get("volume")
        assert dp1.get("pan") == dp0.get("pan")

    def test_warning_printed_for_defaulted_sound(
        self,
    ) -> None:
        """Should return a warning for each sound that gets default params."""
        kit = self._make_embedded_kit(
            num_sounds=3, sound_names=["Kick", "Snare", "HiHat"],
        )
        # Only provide noteRow for sound 0
        clip = self._make_kit_clip(
            noterows=[(0, {"volume": "0xAAAAAAAA"})],
        )
        _, warnings = extract_kit(kit, clip)
        warning_text = "\n".join(warnings)
        assert "Kit sound 'Snare' not used in this clip" in warning_text
        assert "Kit sound 'HiHat' not used in this clip" in warning_text
        # Sound 0 (Kick) should NOT have a warning
        assert "Kick" not in warning_text

    def test_no_sounds_have_noterows_uses_init_fallback(self) -> None:
        """When no sound has <defaultParams>, should fall back to init values."""
        kit = self._make_embedded_kit(num_sounds=2)
        # No noteRows at all
        clip = self._make_kit_clip(noterows=[])
        result, _ = extract_kit(kit, clip)
        sound_sources = result.find("soundSources")
        sounds = list(sound_sources)

        for sound in sounds:
            dp = sound.find("defaultParams")
            assert dp is not None
            # Should have init values from hardcoded fallback
            assert dp.get("volume") == "0x4CCCCCA8"
            assert dp.get("pan") == "0x00000000"
            # Should have child elements
            assert dp.find("envelope1") is not None
            assert dp.find("envelope2") is not None
            assert dp.find("patchCables") is not None
            assert dp.find("equalizer") is not None

    def test_noterow_without_soundparams_warns(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A noteRow with no <soundParams> should warn and the sound gets defaults."""
        kit = self._make_embedded_kit(num_sounds=1, sound_names=["Kick"])
        clip = etree.Element("instrumentClip", section="0")
        etree.SubElement(clip, "kitParams")
        note_rows_el = etree.SubElement(clip, "noteRows")
        # noteRow with drumIndex but no <soundParams> child
        etree.SubElement(note_rows_el, "noteRow", drumIndex="0")

        result, warnings = extract_kit(kit, clip)
        captured = capsys.readouterr()
        # Should warn about missing soundParams (printed to stdout)
        assert "no <soundParams>" in captured.out
        # Warning should also be propagated in the returned warnings list
        assert any("no <soundParams>" in w for w in warnings)
        # Sound should still get <defaultParams> from fallback
        sound_sources = result.find("soundSources")
        sounds = list(sound_sources)
        assert sounds[0].find("defaultParams") is not None

    def test_default_params_inserted_after_unison(self) -> None:
        """Defaulted <defaultParams> should be inserted after <unison>."""
        kit = self._make_embedded_kit(num_sounds=2)
        clip = self._make_kit_clip(noterows=[])
        result, _ = extract_kit(kit, clip)
        sound_sources = result.find("soundSources")
        for sound in sound_sources:
            tags = [child.tag for child in sound]
            dp_idx = tags.index("defaultParams")
            unison_idx = tags.index("unison")
            assert dp_idx == unison_idx + 1, (
                f"defaultParams should be right after unison, got order: {tags}"
            )


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
        """Default mode: <PresetName>-<SongName>.XML."""
        used: set[str] = set()
        result = generate_filename("Bloop", "133", "synth", 0, False, used)
        assert result == "133-Bloop.XML"
        assert "133-Bloop.XML" in used

    def test_extended_mode_format(self) -> None:
        """Extended mode: <PresetName>-<SongName>-<Abbr>.XML."""
        used: set[str] = set()
        result = generate_filename("Bloop", "133", "synth", 0, True, used)
        assert result == "133-Bloop-Lbl.XML"
        assert "133-Bloop-Lbl.XML" in used

    def test_colour_abbreviation_mapping(self) -> None:
        """Should use correct 3-letter abbreviation for each section ID."""
        from deluge_lib.extraction import SECTION_COLOURS

        for section_id, (_name, abbr) in SECTION_COLOURS.items():
            used: set[str] = set()
            result = generate_filename("Song", "Preset", "synth", section_id, True, used)
            assert result == f"Preset-Song-{abbr}.XML"

    def test_collision_appends_number(self) -> None:
        """Should append -2, -3 etc. on filename collision."""
        used: set[str] = {"133-Bloop.XML"}
        result = generate_filename("Bloop", "133", "synth", 0, False, used)
        assert result == "133-Bloop-2.XML"
        assert "133-Bloop-2.XML" in used

        # Third collision
        result2 = generate_filename("Bloop", "133", "synth", 0, False, used)
        assert result2 == "133-Bloop-3.XML"

    def test_preserves_spaces_and_hyphens(self) -> None:
        """Should keep spaces and hyphens in names."""
        used: set[str] = set()
        result = generate_filename("My Song", "Rich Saw-Bass", "synth", 0, False, used)
        assert result == "Rich Saw-Bass-My Song.XML"

    def test_preset_naming_default_mode(self) -> None:
        """Song naming: <SongName>-<PresetName>.XML."""
        used: set[str] = set()
        result = generate_filename("Bloop", "133", "synth", 0, False, used, naming="song")
        assert result == "Bloop-133.XML"
        assert "Bloop-133.XML" in used

    def test_preset_naming_extended_mode(self) -> None:
        """Song naming extended: <SongName>-<PresetName>-<Abbr>.XML."""
        used: set[str] = set()
        result = generate_filename("Bloop", "133", "synth", 0, True, used, naming="song")
        assert result == "Bloop-133-Lbl.XML"
        assert "Bloop-133-Lbl.XML" in used

    def test_preset_naming_collision(self) -> None:
        """Song naming collision should append -2."""
        used: set[str] = {"Bloop-133.XML"}
        result = generate_filename("Bloop", "133", "synth", 0, False, used, naming="song")
        assert result == "Bloop-133-2.XML"

    def test_preset_naming_is_default(self) -> None:
        """Preset naming should be the default (no naming arg)."""
        used: set[str] = set()
        result = generate_filename("Bloop", "133", "synth", 0, False, used)
        assert result == "133-Bloop.XML"


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
# Task 4.1 / 6.2: Comparison engine (compare_instruments)
# ---------------------------------------------------------------------------


def _make_synth_preset(**overrides: str | dict[str, str] | list[tuple[str, str, str]]) -> etree._Element:
    """Build a minimal standalone <sound> for comparison tests.

    Keyword overrides:
        osc1_type, osc2_type — oscillator types
        mode — synth mode attribute
        env1_attack, env1_decay, env1_sustain, env1_release — envelope1 attrs
        env2_attack, env2_decay, env2_sustain, env2_release — envelope2 attrs
        volume, pan, lpfFrequency, hpfFrequency — defaultParams attrs
        patchCables — list of (source, destination, amount) tuples
        Any other key is set on <defaultParams>.
    """
    sound = etree.Element(
        "sound",
        mode=overrides.pop("mode", "subtractive"),
        polyphonic="poly",
        modFXType="none",
        lpfMode="24dB",
        hpfMode="svf",
        filterRoute="H2L",
        firmwareVersion="c1.2.1",
        earliestCompatibleFirmware="4.1.0-alpha",
    )
    etree.SubElement(sound, "osc1", type=overrides.pop("osc1_type", "square"))
    etree.SubElement(sound, "osc2", type=overrides.pop("osc2_type", "square"))
    etree.SubElement(sound, "lfo1", type="sine")
    etree.SubElement(sound, "lfo2", type="sine")
    etree.SubElement(sound, "unison", num="4", detune="10")

    dp_attrs = {
        "volume": overrides.pop("volume", "0x4CCCCCA8"),
        "pan": overrides.pop("pan", "0x00000000"),
        "lpfFrequency": overrides.pop("lpfFrequency", "0x7FFFFFFF"),
        "hpfFrequency": overrides.pop("hpfFrequency", "0x00000000"),
    }
    # Allow arbitrary extra defaultParams attrs
    extra_dp = overrides.pop("extra_dp", {})
    dp_attrs.update(extra_dp)

    dp = etree.SubElement(sound, "defaultParams", **dp_attrs)

    env1_attrs = {
        "attack": overrides.pop("env1_attack", "0x00000000"),
        "decay": overrides.pop("env1_decay", "0x00000000"),
        "sustain": overrides.pop("env1_sustain", "0x7FFFFFFF"),
        "release": overrides.pop("env1_release", "0x00000000"),
    }
    etree.SubElement(dp, "envelope1", **env1_attrs)

    env2_attrs = {
        "attack": overrides.pop("env2_attack", "0x00000000"),
        "decay": overrides.pop("env2_decay", "0x00000000"),
        "sustain": overrides.pop("env2_sustain", "0x7FFFFFFF"),
        "release": overrides.pop("env2_release", "0x00000000"),
    }
    etree.SubElement(dp, "envelope2", **env2_attrs)

    cables = overrides.pop("patchCables", [("velocity", "volume", "0x3FFFFFE8")])
    pc_el = etree.SubElement(dp, "patchCables")
    for src, dst, amt in cables:
        etree.SubElement(pc_el, "patchCable", source=src, destination=dst, amount=amt)

    etree.SubElement(dp, "equalizer", bass="0x00000000", treble="0x00000000")

    etree.SubElement(sound, "arpeggiator", mode="off", noteMode="up", octaveMode="up")
    mk_el = etree.SubElement(sound, "modKnobs")
    mod_knobs = overrides.pop("modKnobs", None)
    if mod_knobs is not None:
        for knob_def in mod_knobs:
            attrs = {"controlsParam": knob_def["controlsParam"]}
            if "patchAmountFromSource" in knob_def:
                attrs["patchAmountFromSource"] = knob_def["patchAmountFromSource"]
            etree.SubElement(mk_el, "modKnob", **attrs)
    etree.SubElement(sound, "delay", pingPong="1", analog="0")
    etree.SubElement(sound, "sidechain", attack="0", release="0")
    etree.SubElement(sound, "audioCompressor", attack="0", release="0", thresh="0", ratio="0")
    return sound


def _make_kit_preset(
    num_sounds: int = 2,
    sound_overrides: dict[int, dict[str, str]] | None = None,
    sound_names: list[str] | None = None,
    kit_volume: str = "0x3504F334",
    kit_pan: str = "0x00000000",
) -> etree._Element:
    """Build a minimal standalone <kit> for comparison tests.

    sound_overrides: dict mapping sound index to overrides.  Keys include:
        osc1_type — osc1 type attribute
        volume, pan — defaultParams attrs on that sound
        patchCables — list of (source, destination, amount) tuples
    """
    kit = etree.Element(
        "kit",
        firmwareVersion="c1.2.1",
        earliestCompatibleFirmware="4.1.0-alpha",
    )
    etree.SubElement(kit, "defaultParams", volume=kit_volume, pan=kit_pan)
    etree.SubElement(kit, "delay", pingPong="1")
    etree.SubElement(kit, "sidechain")
    etree.SubElement(kit, "audioCompressor")

    names = sound_names or [f"Sound{i}" for i in range(num_sounds)]
    overrides = sound_overrides or {}
    ss = etree.SubElement(kit, "soundSources")
    for i in range(num_sounds):
        ov = overrides.get(i, {})
        sound = etree.SubElement(ss, "sound", name=names[i])
        etree.SubElement(sound, "osc1", type=ov.get("osc1_type", "sample"))
        etree.SubElement(sound, "osc2", type="square")
        etree.SubElement(sound, "lfo1", type="sine")
        etree.SubElement(sound, "lfo2", type="sine")
        etree.SubElement(sound, "unison", num="1", detune="0")
        s_dp = etree.SubElement(
            sound, "defaultParams",
            volume=ov.get("volume", "0x4CCCCCA8"),
            pan=ov.get("pan", "0x00000000"),
        )
        env1 = etree.SubElement(s_dp, "envelope1", attack="0x00000000", decay="0x00000000",
                                sustain="0x7FFFFFFF", release="0x00000000")
        env2 = etree.SubElement(s_dp, "envelope2", attack="0x00000000", decay="0x00000000",
                                sustain="0x7FFFFFFF", release="0x00000000")
        pc_el = etree.SubElement(s_dp, "patchCables")
        for src, dst, amt in ov.get("patchCables", [("velocity", "volume", "0x3FFFFFE8")]):
            etree.SubElement(pc_el, "patchCable", source=src, destination=dst, amount=amt)
        etree.SubElement(s_dp, "equalizer", bass="0x00000000", treble="0x00000000")
        etree.SubElement(sound, "arpeggiator", mode="off")
        mk_el = etree.SubElement(sound, "modKnobs")
        mod_knobs = ov.get("modKnobs")
        if mod_knobs is not None:
            for knob_def in mod_knobs:
                attrs = {"controlsParam": knob_def["controlsParam"]}
                if "patchAmountFromSource" in knob_def:
                    attrs["patchAmountFromSource"] = knob_def["patchAmountFromSource"]
                etree.SubElement(mk_el, "modKnob", **attrs)
        etree.SubElement(sound, "delay", pingPong="0")
        etree.SubElement(sound, "sidechain")
        etree.SubElement(sound, "audioCompressor")

    etree.SubElement(kit, "selectedDrumIndex", value="0")
    return kit


class TestCompareInstruments:
    """Tests for compare_instruments() — comparison engine."""

    CONFIG = ComparisonConfig.default()

    # --- Hard marker: osc type change ---

    def test_osc1_type_change_is_hard_distinct(self) -> None:
        """Different osc1 types should be detected as hard marker → distinct."""
        a = _make_synth_preset(osc1_type="square")
        b = _make_synth_preset(osc1_type="saw")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert len(result.hard_diffs) >= 1
        assert any("osc1.type" in d for d in result.hard_diffs)

    def test_osc2_type_change_is_hard_distinct(self) -> None:
        """Different osc2 types should be detected as hard marker → distinct."""
        a = _make_synth_preset(osc2_type="square")
        b = _make_synth_preset(osc2_type="analogSaw")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("osc2.type" in d for d in result.hard_diffs)

    # --- Hard marker: patchCable structure change ---

    def test_added_patchcable_is_hard_distinct(self) -> None:
        """Adding a patchCable routing should be a hard marker → distinct."""
        a = _make_synth_preset(patchCables=[("velocity", "volume", "0x3FFFFFE8")])
        b = _make_synth_preset(patchCables=[
            ("velocity", "volume", "0x3FFFFFE8"),
            ("lfo1", "pitch", "0x10000000"),
        ])
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("patchCables structure" in d for d in result.hard_diffs)

    def test_removed_patchcable_is_hard_distinct(self) -> None:
        """Removing a patchCable routing should be a hard marker → distinct."""
        a = _make_synth_preset(patchCables=[
            ("velocity", "volume", "0x3FFFFFE8"),
            ("lfo1", "pitch", "0x10000000"),
        ])
        b = _make_synth_preset(patchCables=[("velocity", "volume", "0x3FFFFFE8")])
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("patchCables structure" in d for d in result.hard_diffs)

    # --- Hard marker: synth mode change ---

    def test_synth_mode_change_is_hard_distinct(self) -> None:
        """Different synth modes should be a hard marker → distinct."""
        a = _make_synth_preset(mode="subtractive")
        b = _make_synth_preset(mode="fm")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("sound.mode" in d for d in result.hard_diffs)

    # --- Soft marker: threshold logic ---

    def test_soft_three_params_above_threshold_is_distinct(self) -> None:
        """3+ params changed by >10% → distinct (soft markers)."""
        a = _make_synth_preset(
            lpfFrequency="0x00000000",
            hpfFrequency="0x00000000",
            env1_attack="0x00000000",
        )
        # Each param shifted by a large amount (well over 10% of full range)
        b = _make_synth_preset(
            lpfFrequency="0x7FFFFFFF",
            hpfFrequency="0x7FFFFFFF",
            env1_attack="0x7FFFFFFF",
        )
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert result.hard_diffs == []
        assert result.soft_diff_count >= 3

    def test_soft_two_params_below_threshold_not_distinct(self) -> None:
        """Fewer than 3 params changed → not distinct."""
        a = _make_synth_preset(
            lpfFrequency="0x00000000",
            hpfFrequency="0x00000000",
        )
        b = _make_synth_preset(
            lpfFrequency="0x7FFFFFFF",
            hpfFrequency="0x7FFFFFFF",
        )
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is False
        assert result.hard_diffs == []
        assert result.soft_diff_count < 3

    def test_soft_small_change_not_counted(self) -> None:
        """Params that change by <8% of full range should not count as soft diffs."""
        # 8% of 0xFFFFFFFF ≈ 0x147AE147. Keep changes well under that.
        a = _make_synth_preset(lpfFrequency="0x40000000")
        b = _make_synth_preset(lpfFrequency="0x41000000")  # ~0.5% change
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is False
        assert result.soft_diff_count == 0

    # --- Ignored params: volume/pan ---

    def test_volume_change_does_not_affect_verdict(self) -> None:
        """Volume is in ignored_attrs — should not count as soft diff."""
        a = _make_synth_preset(volume="0x00000000")
        b = _make_synth_preset(volume="0x7FFFFFFF")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is False
        assert result.soft_diff_count == 0

    def test_pan_change_does_not_affect_verdict(self) -> None:
        """Pan is in ignored_attrs — should not count as soft diff."""
        a = _make_synth_preset(pan="0x80000000")
        b = _make_synth_preset(pan="0x7FFFFFFF")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is False
        assert result.soft_diff_count == 0

    def test_volume_and_pan_combined_with_soft_diffs(self) -> None:
        """Volume/pan changes should not push soft diff count over threshold."""
        a = _make_synth_preset(
            volume="0x00000000", pan="0x00000000",
            lpfFrequency="0x00000000", hpfFrequency="0x00000000",
        )
        # 2 real soft diffs + volume + pan change = still only 2 real soft diffs
        b = _make_synth_preset(
            volume="0x7FFFFFFF", pan="0x7FFFFFFF",
            lpfFrequency="0x7FFFFFFF", hpfFrequency="0x7FFFFFFF",
        )
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is False
        assert result.soft_diff_count == 2

    # --- Envelope attributes as soft markers ---

    def test_envelope_changes_are_soft_markers(self) -> None:
        """Envelope attribute changes should be counted as soft markers."""
        a = _make_synth_preset(
            env1_attack="0x00000000", env1_decay="0x00000000", env1_sustain="0x00000000",
        )
        b = _make_synth_preset(
            env1_attack="0x7FFFFFFF", env1_decay="0x7FFFFFFF", env1_sustain="0x7FFFFFFF",
        )
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert result.hard_diffs == []
        assert any("envelope1" in d for d in result.soft_diffs)

    def test_envelope2_changes_are_soft_markers(self) -> None:
        """Envelope2 attribute changes should also be counted."""
        a = _make_synth_preset(
            env2_attack="0x00000000", env2_decay="0x00000000", env2_sustain="0x00000000",
        )
        b = _make_synth_preset(
            env2_attack="0x7FFFFFFF", env2_decay="0x7FFFFFFF", env2_sustain="0x7FFFFFFF",
        )
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("envelope2" in d for d in result.soft_diffs)

    # --- PatchCable amount as soft marker ---

    def test_patchcable_amount_change_is_soft_marker(self) -> None:
        """Same patchCable structure but different amounts → soft marker."""
        a = _make_synth_preset(patchCables=[("velocity", "volume", "0x00000000")])
        b = _make_synth_preset(patchCables=[("velocity", "volume", "0x7FFFFFFF")])
        result = compare_instruments(a, b, "synth", self.CONFIG)
        # This is just 1 soft diff, so not distinct (threshold is 3)
        assert result.is_distinct is False
        assert any("patchCable" in d for d in result.soft_diffs)

    # --- Identical presets ---

    def test_identical_presets_not_distinct(self) -> None:
        """Two identical presets should not be distinct."""
        a = _make_synth_preset()
        b = _make_synth_preset()
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is False
        assert result.hard_diffs == []
        assert result.soft_diff_count == 0

    # --- ComparisonResult fields ---

    def test_result_fields_hard(self) -> None:
        """Hard marker result should have correct field values."""
        a = _make_synth_preset(osc1_type="square")
        b = _make_synth_preset(osc1_type="saw")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert isinstance(result, ComparisonResult)
        assert result.is_distinct is True
        assert len(result.hard_diffs) > 0
        assert result.soft_diff_count == 0
        assert result.soft_diffs == []
        assert "hard" in result.reason

    def test_result_fields_soft(self) -> None:
        """Soft marker result should have correct field values."""
        a = _make_synth_preset(
            lpfFrequency="0x00000000", hpfFrequency="0x00000000",
            env1_attack="0x00000000",
        )
        b = _make_synth_preset(
            lpfFrequency="0x7FFFFFFF", hpfFrequency="0x7FFFFFFF",
            env1_attack="0x7FFFFFFF",
        )
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert result.hard_diffs == []
        assert result.soft_diff_count >= 3
        assert len(result.soft_diffs) >= 3
        assert "soft" in result.reason

    def test_result_fields_similar(self) -> None:
        """Similar result should have correct field values."""
        a = _make_synth_preset()
        b = _make_synth_preset()
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is False
        assert result.hard_diffs == []
        assert "similar" in result.reason

    # --- Kit comparison: structural hard markers ---

    def test_kit_different_sound_count_is_hard_distinct(self) -> None:
        """Kits with different number of sounds → hard marker → distinct."""
        a = _make_kit_preset(num_sounds=2)
        b = _make_kit_preset(num_sounds=3)
        result = compare_instruments(a, b, "kit", self.CONFIG)
        assert result.is_distinct is True
        assert any("soundSources count" in d for d in result.hard_diffs)

    def test_kit_different_sound_names_is_hard_distinct(self) -> None:
        """Kits with different sound names → hard marker → distinct."""
        a = _make_kit_preset(sound_names=["Kick", "Snare"])
        b = _make_kit_preset(sound_names=["Kick", "HiHat"])
        result = compare_instruments(a, b, "kit", self.CONFIG)
        assert result.is_distinct is True
        assert any("soundSources names" in d for d in result.hard_diffs)

    def test_kit_per_sound_osc_type_change_is_hard(self) -> None:
        """Changing osc1 type on a kit sound → hard marker."""
        a = _make_kit_preset(sound_overrides={0: {"osc1_type": "sample"}})
        b = _make_kit_preset(sound_overrides={0: {"osc1_type": "analogSquare"}})
        result = compare_instruments(a, b, "kit", self.CONFIG)
        assert result.is_distinct is True
        assert any("osc1.type" in d for d in result.hard_diffs)

    # --- Kit comparison: per-sound soft markers ---

    def test_kit_one_tweaked_row_makes_kit_distinct(self) -> None:
        """One heavily tweaked row (3+ params) should make entire kit distinct."""
        # Row 0 has 3+ large param changes
        a = _make_kit_preset(num_sounds=2, sound_overrides={
            0: {"volume": "0x00000000", "pan": "0x00000000"},
        })
        b = _make_kit_preset(num_sounds=2, sound_overrides={
            0: {"volume": "0x00000000", "pan": "0x00000000"},
        })
        # Modify 3 params on sound 0 in preset b by large amounts
        ss_b = b.find("soundSources")
        sound0_b = list(ss_b)[0]
        dp_b = sound0_b.find("defaultParams")
        dp_b.find("envelope1").set("attack", "0x7FFFFFFF")
        dp_b.find("envelope1").set("decay", "0x7FFFFFFF")
        dp_b.find("envelope1").set("sustain", "0x00000000")
        result = compare_instruments(a, b, "kit", self.CONFIG)
        assert result.is_distinct is True
        assert result.hard_diffs == []
        assert result.soft_diff_count >= 3

    def test_kit_minor_tweak_not_distinct(self) -> None:
        """Minor tweaks to a kit row (fewer than threshold) → not distinct."""
        a = _make_kit_preset(num_sounds=2)
        b = _make_kit_preset(num_sounds=2)
        # Change 1 param on sound 0 by a large amount — still under threshold
        ss_b = b.find("soundSources")
        sound0_b = list(ss_b)[0]
        dp_b = sound0_b.find("defaultParams")
        dp_b.find("envelope1").set("attack", "0x7FFFFFFF")
        result = compare_instruments(a, b, "kit", self.CONFIG)
        assert result.is_distinct is False

    # --- Hard marker: modKnobs structure (synth) ---

    _BASELINE_MODKNOBS: list[dict[str, str]] = [
        {"controlsParam": "pan"},
        {"controlsParam": "volumePostFX"},
        {"controlsParam": "volumePostReverbSend", "patchAmountFromSource": "compressor"},
        {"controlsParam": "lpfFrequency"},
    ]

    def test_modknob_param_change_is_hard_distinct(self) -> None:
        """Different controlsParam in one modKnob slot → hard distinct."""
        knobs_b = [dict(k) for k in self._BASELINE_MODKNOBS]
        knobs_b[3] = {"controlsParam": "modulator1Volume"}
        a = _make_synth_preset(modKnobs=self._BASELINE_MODKNOBS)
        b = _make_synth_preset(modKnobs=knobs_b)
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("modKnobs[3].controlsParam" in d for d in result.hard_diffs)

    def test_modknob_patch_source_added_is_hard_distinct(self) -> None:
        """Adding patchAmountFromSource to a modKnob slot → hard distinct."""
        knobs_b = [dict(k) for k in self._BASELINE_MODKNOBS]
        knobs_b[0] = {"controlsParam": "pan", "patchAmountFromSource": "lfo1"}
        a = _make_synth_preset(modKnobs=self._BASELINE_MODKNOBS)
        b = _make_synth_preset(modKnobs=knobs_b)
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("modKnobs[0].patchAmountFromSource" in d and "added" in d for d in result.hard_diffs)

    def test_modknob_patch_source_removed_is_hard_distinct(self) -> None:
        """Removing patchAmountFromSource from a modKnob slot → hard distinct."""
        knobs_b = [dict(k) for k in self._BASELINE_MODKNOBS]
        knobs_b[2] = {"controlsParam": "volumePostReverbSend"}
        a = _make_synth_preset(modKnobs=self._BASELINE_MODKNOBS)
        b = _make_synth_preset(modKnobs=knobs_b)
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("modKnobs[2].patchAmountFromSource" in d and "removed" in d for d in result.hard_diffs)

    def test_modknob_patch_source_changed_is_hard_distinct(self) -> None:
        """Changed patchAmountFromSource on a modKnob slot → hard distinct."""
        knobs_b = [dict(k) for k in self._BASELINE_MODKNOBS]
        knobs_b[2] = {"controlsParam": "volumePostReverbSend", "patchAmountFromSource": "lfo2"}
        a = _make_synth_preset(modKnobs=self._BASELINE_MODKNOBS)
        b = _make_synth_preset(modKnobs=knobs_b)
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any(
            "modKnobs[2].patchAmountFromSource" in d and "'compressor'" in d and "'lfo2'" in d
            for d in result.hard_diffs
        )

    def test_identical_modknobs_not_distinct(self) -> None:
        """Identical modKnobs mappings → not distinct (from modKnobs perspective)."""
        a = _make_synth_preset(modKnobs=self._BASELINE_MODKNOBS)
        b = _make_synth_preset(modKnobs=self._BASELINE_MODKNOBS)
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert not any("modKnobs" in d for d in result.hard_diffs)

    def test_empty_modknobs_not_distinct(self) -> None:
        """Both presets with empty modKnobs → not distinct (backward compat)."""
        a = _make_synth_preset()
        b = _make_synth_preset()
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert not any("modKnobs" in d for d in result.hard_diffs)

    # --- Hard marker: modKnobs structure (kit per-sound) ---

    def test_kit_per_sound_modknob_change_is_hard_distinct(self) -> None:
        """Kit where one sound row has different modKnobs → hard distinct."""
        knobs_a = [{"controlsParam": "pan"}, {"controlsParam": "volumePostFX"}]
        knobs_b = [{"controlsParam": "pan"}, {"controlsParam": "lpfFrequency"}]
        a = _make_kit_preset(num_sounds=2, sound_overrides={0: {"modKnobs": knobs_a}})
        b = _make_kit_preset(num_sounds=2, sound_overrides={0: {"modKnobs": knobs_b}})
        result = compare_instruments(a, b, "kit", self.CONFIG)
        assert result.is_distinct is True
        assert any("sound[Sound0].modKnobs[1].controlsParam" in d for d in result.hard_diffs)


# ---------------------------------------------------------------------------
# Task 3.3: Comparison engine extension tests (depthControlledBy + synth osc markers)
# ---------------------------------------------------------------------------


def _add_depth_controlled_by(
    preset: etree._Element,
    cable_src: str,
    cable_dst: str,
    depth_source: str,
    depth_amount: str,
) -> None:
    """Add a <depthControlledBy> child to a matching patchCable in *preset*.

    Finds the patchCable with the given (source, destination) under
    <defaultParams><patchCables> and appends a nested depthControlledBy element.
    """
    dp = preset.find("defaultParams")
    for cable in dp.find("patchCables"):
        if cable.get("source") == cable_src and cable.get("destination") == cable_dst:
            dcb = etree.SubElement(cable, "depthControlledBy")
            etree.SubElement(dcb, "patchCable", source=depth_source, amount=depth_amount)
            return
    msg = f"No patchCable ({cable_src}->{cable_dst}) found"
    raise ValueError(msg)


class TestDepthControlledByComparison:
    """Tests for depthControlledBy nested patchCable comparison."""

    CONFIG = ComparisonConfig.default()

    def test_depth_present_one_side_only_is_hard(self) -> None:
        """depthControlledBy on one cable but not the other → hard distinct."""
        a = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        b = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        _add_depth_controlled_by(b, "lfo1", "oscAPitch", "lfo2", "0x3FFFFFE8")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("depthControlledBy" in d for d in result.hard_diffs)

    def test_depth_removed_is_hard(self) -> None:
        """depthControlledBy present on A but not B → hard distinct (removed)."""
        a = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        b = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        _add_depth_controlled_by(a, "lfo1", "oscAPitch", "lfo2", "0x3FFFFFE8")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("depthControlledBy: removed" in d for d in result.hard_diffs)

    def test_depth_different_source_is_hard(self) -> None:
        """Same depthControlledBy structure but different sub-source → hard distinct."""
        a = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        b = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        _add_depth_controlled_by(a, "lfo1", "oscAPitch", "lfo2", "0x3FFFFFE8")
        _add_depth_controlled_by(b, "lfo1", "oscAPitch", "velocity", "0x3FFFFFE8")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("depthControlledBy" in d and "source" in d for d in result.hard_diffs)

    def test_depth_same_structure_different_amount_is_soft(self) -> None:
        """Same depthControlledBy source but different amount → soft marker."""
        a = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        b = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        _add_depth_controlled_by(a, "lfo1", "oscAPitch", "lfo2", "0x00000000")
        _add_depth_controlled_by(b, "lfo1", "oscAPitch", "lfo2", "0x7FFFFFFF")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        # Hard diffs should be empty — this is a soft difference only
        assert result.hard_diffs == []
        assert any("depthControlledBy.amount" in d for d in result.soft_diffs)

    def test_depth_same_structure_same_amount_no_diff(self) -> None:
        """Identical depthControlledBy → no diffs at all."""
        a = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        b = _make_synth_preset(patchCables=[("lfo1", "oscAPitch", "0x051EB850")])
        _add_depth_controlled_by(a, "lfo1", "oscAPitch", "lfo2", "0x3FFFFFE8")
        _add_depth_controlled_by(b, "lfo1", "oscAPitch", "lfo2", "0x3FFFFFE8")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is False
        assert result.hard_diffs == []
        assert not any("depthControlledBy" in d for d in result.soft_diffs)

    def test_no_depth_controlled_by_unchanged_behaviour(self) -> None:
        """PatchCables without depthControlledBy → existing comparison unchanged."""
        a = _make_synth_preset(patchCables=[("velocity", "volume", "0x3FFFFFE8")])
        b = _make_synth_preset(patchCables=[("velocity", "volume", "0x3FFFFFE8")])
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is False
        assert result.hard_diffs == []
        assert result.soft_diffs == []


class TestSynthOscHardMarkers:
    """Tests for synth osc1/osc2 loopMode and reversed hard markers."""

    CONFIG = ComparisonConfig.default()

    def test_osc1_loopmode_difference_is_hard(self) -> None:
        """Different loopMode on osc1 → hard distinct."""
        a = _make_synth_preset()
        b = _make_synth_preset()
        a.find("osc1").set("loopMode", "0")
        b.find("osc1").set("loopMode", "1")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("osc1.loopMode" in d for d in result.hard_diffs)

    def test_osc1_reversed_difference_is_hard(self) -> None:
        """Different reversed on osc1 → hard distinct."""
        a = _make_synth_preset()
        b = _make_synth_preset()
        a.find("osc1").set("reversed", "0")
        b.find("osc1").set("reversed", "1")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("osc1.reversed" in d for d in result.hard_diffs)

    def test_osc2_loopmode_difference_is_hard(self) -> None:
        """Different loopMode on osc2 → hard distinct."""
        a = _make_synth_preset()
        b = _make_synth_preset()
        a.find("osc2").set("loopMode", "0")
        b.find("osc2").set("loopMode", "2")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("osc2.loopMode" in d for d in result.hard_diffs)

    def test_osc_same_loopmode_not_hard(self) -> None:
        """Same loopMode on both → no hard diff from loopMode."""
        a = _make_synth_preset()
        b = _make_synth_preset()
        a.find("osc1").set("loopMode", "1")
        b.find("osc1").set("loopMode", "1")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert not any("loopMode" in d for d in result.hard_diffs)

    def test_osc_absent_vs_present_loopmode_is_hard(self) -> None:
        """loopMode present on one side but absent on the other → hard distinct."""
        a = _make_synth_preset()
        b = _make_synth_preset()
        # Only set on b, not a — absent attr defaults to ""
        b.find("osc1").set("loopMode", "1")
        result = compare_instruments(a, b, "synth", self.CONFIG)
        assert result.is_distinct is True
        assert any("osc1.loopMode" in d for d in result.hard_diffs)


# ---------------------------------------------------------------------------
# Task 4.3 / 6.2: Extended mode multi-version selection
# ---------------------------------------------------------------------------


class TestSelectExtendedClips:
    """Tests for select_extended_clips() — extended mode clip selection."""

    CONFIG = ComparisonConfig.default()
    NORM_CONFIG = NormalisationConfig()

    @staticmethod
    def _make_synth_group(
        sections: dict[int, dict[str, str]],
    ) -> InstrumentClipGroup:
        """Build an InstrumentClipGroup with synth clips at the given sections.

        Each section value is a dict of soundParams overrides (e.g. lpfFrequency).
        The instrument element is a minimal embedded <sound> that will go through
        extract_synth() internally.
        """
        inst_el = etree.Element(
            "sound",
            presetName="TestSynth",
            presetFolder="SYNTHS",
            mode="subtractive",
            polyphonic="poly",
            modFXType="none",
            lpfMode="24dB",
            hpfMode="svf",
            filterRoute="H2L",
        )
        etree.SubElement(inst_el, "osc1", type="square")
        etree.SubElement(inst_el, "osc2", type="square")
        etree.SubElement(inst_el, "lfo1", type="sine")
        etree.SubElement(inst_el, "lfo2", type="sine")
        etree.SubElement(inst_el, "unison", num="4", detune="10")
        etree.SubElement(inst_el, "modKnobs")
        etree.SubElement(inst_el, "delay", pingPong="1")
        etree.SubElement(inst_el, "sidechain")
        etree.SubElement(inst_el, "audioCompressor")

        instrument = InstrumentInfo(
            element=inst_el,
            instrument_type="synth",
            preset_name="TestSynth",
            preset_folder="SYNTHS",
        )

        clips_by_section: dict[int, ClipInfo] = {}
        for sec, overrides in sections.items():
            clip_el = etree.Element("instrumentClip", section=str(sec))
            etree.SubElement(clip_el, "arpeggiator", mode="off")
            sp_attrs = {
                "volume": "0x4CCCCCA8",
                "pan": "0x00000000",
                "lpfFrequency": "0x7FFFFFFF",
                "hpfFrequency": "0x00000000",
            }
            sp_attrs.update(overrides)
            sp = etree.SubElement(clip_el, "soundParams", **sp_attrs)
            env1 = etree.SubElement(sp, "envelope1", attack="0x00000000",
                                    decay="0x00000000", sustain="0x7FFFFFFF",
                                    release="0x00000000")
            env2 = etree.SubElement(sp, "envelope2", attack="0x00000000",
                                    decay="0x00000000", sustain="0x7FFFFFFF",
                                    release="0x00000000")
            pc_el = etree.SubElement(sp, "patchCables")
            etree.SubElement(pc_el, "patchCable", source="velocity",
                             destination="volume", amount="0x3FFFFFE8")
            etree.SubElement(sp, "equalizer", bass="0x00000000", treble="0x00000000")
            clips_by_section[sec] = ClipInfo(
                element=clip_el,
                section=sec,
                preset_name="TestSynth",
                preset_folder="SYNTHS",
            )

        return InstrumentClipGroup(instrument=instrument, clips_by_section=clips_by_section)

    def test_baseline_always_included(self) -> None:
        """Lowest section ID clip is always in the result."""
        group = self._make_synth_group({
            0: {},
            3: {},
        })
        result = select_extended_clips(group, self.CONFIG, self.NORM_CONFIG)
        assert len(result) >= 1
        assert result[0][0].section == 0
        assert result[0][1] == []  # baseline has no comparisons

    def test_distinct_clip_accepted(self) -> None:
        """Clip that is distinct from baseline should be accepted."""
        group = self._make_synth_group({
            0: {"lpfFrequency": "0x00000000", "hpfFrequency": "0x00000000"},
            3: {"lpfFrequency": "0x7FFFFFFF", "hpfFrequency": "0x7FFFFFFF"},
        })
        # Override 3 envelope params on section 3 to ensure 3+ soft diffs
        clip3 = group.clips_by_section[3].element
        sp3 = clip3.find("soundParams")
        sp3.find("envelope1").set("attack", "0x7FFFFFFF")
        result = select_extended_clips(group, self.CONFIG, self.NORM_CONFIG)
        assert len(result) == 2
        sections = [clip.section for clip, _ in result]
        assert 0 in sections
        assert 3 in sections

    def test_similar_clip_rejected(self) -> None:
        """Clip that is similar to baseline should be rejected."""
        group = self._make_synth_group({
            0: {},
            3: {},  # identical params
        })
        result = select_extended_clips(group, self.CONFIG, self.NORM_CONFIG)
        assert len(result) == 1
        assert result[0][0].section == 0

    def test_compare_against_all_accepted(self) -> None:
        """Third clip should be compared against all accepted, not just baseline.

        Scenario: section 0 (baseline), section 3 (distinct from 0, accepted),
        section 6 (identical to section 3 but distinct from 0 → rejected
        because it's similar to accepted section 3).
        """
        group = self._make_synth_group({
            0: {"lpfFrequency": "0x00000000", "hpfFrequency": "0x00000000"},
            3: {"lpfFrequency": "0x7FFFFFFF", "hpfFrequency": "0x7FFFFFFF"},
            6: {"lpfFrequency": "0x7FFFFFFF", "hpfFrequency": "0x7FFFFFFF"},
        })
        # Make section 3 distinct from section 0 with 3+ diffs
        clip3 = group.clips_by_section[3].element
        sp3 = clip3.find("soundParams")
        sp3.find("envelope1").set("attack", "0x7FFFFFFF")
        # Section 6 is identical to section 3
        clip6 = group.clips_by_section[6].element
        sp6 = clip6.find("soundParams")
        sp6.set("lpfFrequency", "0x7FFFFFFF")
        sp6.set("hpfFrequency", "0x7FFFFFFF")
        sp6.find("envelope1").set("attack", "0x7FFFFFFF")

        result = select_extended_clips(group, self.CONFIG, self.NORM_CONFIG)
        sections = [clip.section for clip, _ in result]
        assert 0 in sections
        assert 3 in sections
        assert 6 not in sections  # rejected: similar to accepted section 3

    def test_empty_group_returns_empty(self) -> None:
        """Group with no clips should return empty list."""
        inst_el = etree.Element("sound", presetName="X", presetFolder="SYNTHS")
        instrument = InstrumentInfo(
            element=inst_el, instrument_type="synth",
            preset_name="X", preset_folder="SYNTHS",
        )
        group = InstrumentClipGroup(instrument=instrument, clips_by_section={})
        result = select_extended_clips(group, self.CONFIG, self.NORM_CONFIG)
        assert result == []


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


# ---------------------------------------------------------------------------
# Automation Stripping
# ---------------------------------------------------------------------------


class TestStripAutomation:
    def test_truncates_extended_hex_to_base_value(self) -> None:
        """Extended hex automation string should be truncated to first 8 hex chars."""
        el = etree.Element("defaultParams", lpfFrequency="0x7FFFFFFF7FFFFFFF000000607FFFFFFF00000120")
        warnings = _strip_automation(el)
        assert el.get("lpfFrequency") == "0x7FFFFFFF"
        assert len(warnings) == 1

    def test_normal_hex_unchanged(self) -> None:
        """Normal 8-char hex values should not be modified."""
        el = etree.Element("defaultParams", lpfFrequency="0x7FFFFFFF")
        warnings = _strip_automation(el)
        assert el.get("lpfFrequency") == "0x7FFFFFFF"
        assert warnings == []

    def test_non_hex_attributes_unchanged(self) -> None:
        """Non-hex attributes like text or numeric values should not be modified."""
        el = etree.Element("osc1", type="square")
        warnings = _strip_automation(el)
        assert el.get("type") == "square"
        assert warnings == []

    def test_recurses_into_children(self) -> None:
        """Should process attributes on descendant elements, not just the root."""
        root = etree.Element("sound")
        child = etree.SubElement(root, "defaultParams", volume="0x4CCCCCA8AABBCCDD11223344")
        grandchild = etree.SubElement(child, "envelope1", attack="0x00000000FFFFFFFF99887766")
        warnings = _strip_automation(root)
        assert child.get("volume") == "0x4CCCCCA8"
        assert grandchild.get("attack") == "0x00000000"
        assert len(warnings) == 2

    def test_returns_warning_strings(self) -> None:
        """Warning strings should identify the element tag and attribute name."""
        el = etree.Element("defaultParams", delayFeedback="0x7FFFFFFF7FFFFFFF000000607FFFFFFF")
        warnings = _strip_automation(el)
        assert warnings == ["Stripped automation from defaultParams.delayFeedback"]


# ---------------------------------------------------------------------------
# Task 5.1 / 6.2: Cross-song deduplication (deduplicate_results)
# ---------------------------------------------------------------------------


def _make_extraction_result(
    song_name: str,
    preset_name: str,
    instrument_type: str = "synth",
    element: etree._Element | None = None,
    section_id: int = 0,
) -> ExtractionResult:
    """Build a minimal ExtractionResult for dedup testing."""
    if element is None:
        element = _make_synth_preset()
    return ExtractionResult(
        song_name=song_name,
        preset_name=preset_name,
        instrument_type=instrument_type,
        section_id=section_id,
        colour_abbr="Lbl",
        element=element,
        output_filename=f"{song_name}-{preset_name}.XML",
        preset_folder=f"{'SYNTHS' if instrument_type == 'synth' else 'KITS'}",
        colour_name="LightBlue",
    )


class TestDeduplicateResults:
    """Tests for deduplicate_results() — cross-song deduplication."""

    CONFIG = ComparisonConfig.default()

    def test_empty_input_returns_empty(self) -> None:
        """Empty input should return empty accepted and rejected lists."""
        result = deduplicate_results([], self.CONFIG)
        assert isinstance(result, DedupResult)
        assert result.accepted == []
        assert result.rejected == []

    def test_single_result_passes_through(self) -> None:
        """A single result should pass through without comparison."""
        r = _make_extraction_result("Song1", "Bass")
        result = deduplicate_results([r], self.CONFIG)
        assert len(result.accepted) == 1
        assert result.accepted[0] is r
        assert result.rejected == []

    def test_single_result_group_passes_through(self) -> None:
        """Groups with one member pass through, even with multiple groups."""
        r1 = _make_extraction_result("Song1", "Bass", element=_make_synth_preset(osc1_type="saw"))
        r2 = _make_extraction_result("Song2", "Lead", element=_make_synth_preset(osc1_type="triangle"))
        result = deduplicate_results([r1, r2], self.CONFIG)
        assert len(result.accepted) == 2
        assert result.rejected == []

    def test_preset_name_grouping(self) -> None:
        """Results with different preset names are separate in the name pass.

        Note: with the global (cross-name) pass, structurally identical presets
        with different names *will* be caught. Use distinct elements to test
        name-pass independence.
        """
        r1 = _make_extraction_result("Song1", "Bass", element=_make_synth_preset(osc1_type="saw"))
        r2 = _make_extraction_result("Song2", "Lead", element=_make_synth_preset(osc1_type="triangle"))
        result = deduplicate_results([r1, r2], self.CONFIG)
        assert len(result.accepted) == 2
        assert result.rejected == []

    def test_cross_name_duplicates_caught_by_global_pass(self) -> None:
        """Structurally identical presets with different names → global pass rejects one."""
        r1 = _make_extraction_result("Song1", "Bass", element=_make_synth_preset())
        r2 = _make_extraction_result("Song2", "Lead", element=_make_synth_preset())
        result = deduplicate_results([r1, r2], self.CONFIG)
        assert len(result.accepted) == 1
        assert len(result.rejected) == 1
        assert result.name_pass_rejected == []
        assert len(result.global_pass_rejected) == 1

    def test_identical_presets_deduplicated(self) -> None:
        """Two identical presets with the same name → second rejected."""
        el_a = _make_synth_preset()
        el_b = _make_synth_preset()
        r1 = _make_extraction_result("Aaa", "Bass", element=el_a)
        r2 = _make_extraction_result("Bbb", "Bass", element=el_b)
        result = deduplicate_results([r1, r2], self.CONFIG)
        assert len(result.accepted) == 1
        assert len(result.rejected) == 1
        assert result.accepted[0].song_name == "Aaa"  # first alphabetically
        assert result.rejected[0].result.song_name == "Bbb"

    def test_distinct_presets_both_accepted(self) -> None:
        """Two distinct presets with the same name → both accepted."""
        el_a = _make_synth_preset(osc1_type="square")
        el_b = _make_synth_preset(osc1_type="saw")
        r1 = _make_extraction_result("Aaa", "Bass", element=el_a)
        r2 = _make_extraction_result("Bbb", "Bass", element=el_b)
        result = deduplicate_results([r1, r2], self.CONFIG)
        assert len(result.accepted) == 2
        assert result.rejected == []

    def test_deterministic_ordering_by_song_name(self) -> None:
        """Results should be sorted by song name within each group."""
        el = _make_synth_preset()
        r1 = _make_extraction_result("Zzz", "Bass", element=_make_synth_preset())
        r2 = _make_extraction_result("Aaa", "Bass", element=_make_synth_preset())
        r3 = _make_extraction_result("Mmm", "Bass", element=_make_synth_preset())
        result = deduplicate_results([r1, r2, r3], self.CONFIG)
        # All identical → only first alphabetically is accepted
        assert len(result.accepted) == 1
        assert result.accepted[0].song_name == "Aaa"
        assert len(result.rejected) == 2

    def test_compare_against_all_accepted(self) -> None:
        """Third result should be compared against all accepted, not just baseline.

        Scenario: A (baseline), B (distinct from A, accepted), C (identical to B → rejected).
        """
        el_a = _make_synth_preset(osc1_type="square")
        el_b = _make_synth_preset(osc1_type="saw")  # hard distinct from A
        el_c = _make_synth_preset(osc1_type="saw")  # identical to B
        r_a = _make_extraction_result("Aaa", "Bass", element=el_a)
        r_b = _make_extraction_result("Bbb", "Bass", element=el_b)
        r_c = _make_extraction_result("Ccc", "Bass", element=el_c)
        result = deduplicate_results([r_a, r_b, r_c], self.CONFIG)
        assert len(result.accepted) == 2
        assert len(result.rejected) == 1
        assert result.rejected[0].result.song_name == "Ccc"
        # The matched_result should be the one it was similar to (Bbb)
        assert result.rejected[0].matched_result.song_name == "Bbb"

    def test_instrument_type_grouping(self) -> None:
        """Same preset name but different instrument types → separate groups."""
        el_synth = _make_synth_preset()
        el_kit = _make_kit_preset()
        r1 = _make_extraction_result("Song1", "Init", instrument_type="synth", element=el_synth)
        r2 = _make_extraction_result("Song2", "Init", instrument_type="kit", element=el_kit)
        result = deduplicate_results([r1, r2], self.CONFIG)
        # Different instrument types → different groups → both accepted
        assert len(result.accepted) == 2
        assert result.rejected == []

    def test_rejected_result_has_comparison(self) -> None:
        """Rejected results should carry the ComparisonResult."""
        r1 = _make_extraction_result("Aaa", "Bass", element=_make_synth_preset())
        r2 = _make_extraction_result("Bbb", "Bass", element=_make_synth_preset())
        result = deduplicate_results([r1, r2], self.CONFIG)
        assert len(result.rejected) == 1
        rejected = result.rejected[0]
        assert isinstance(rejected, RejectedResult)
        assert isinstance(rejected.comparison, ComparisonResult)
        assert rejected.comparison.is_distinct is False
        assert rejected.matched_result is r1

    def test_multiple_groups_independent(self) -> None:
        """Dedup operates independently per group in the name pass."""
        # Group "Bass": 2 identical synths → 1 accepted, 1 rejected (name pass)
        r1 = _make_extraction_result("Song1", "Bass", element=_make_synth_preset(mode="fm"))
        r2 = _make_extraction_result("Song2", "Bass", element=_make_synth_preset(mode="fm"))
        # Group "Lead": 2 distinct synths → both accepted (name pass)
        # Use osc1_type="saw" and mode="ringmod" so all 3 surviving presets
        # are hard-distinct from each other (avoiding global-pass rejection).
        r3 = _make_extraction_result("Song1", "Lead", element=_make_synth_preset(osc1_type="saw"))
        r4 = _make_extraction_result("Song2", "Lead", element=_make_synth_preset(mode="ringmod"))
        result = deduplicate_results([r1, r2, r3, r4], self.CONFIG)
        assert len(result.accepted) == 3
        assert len(result.rejected) == 1
        assert len(result.name_pass_rejected) == 1
        assert result.global_pass_rejected == []


# ---------------------------------------------------------------------------
# Sidechain Kit Detection
# ---------------------------------------------------------------------------


class TestIsSidechainKit:
    """Tests for is_sidechain_kit() — sidechain-only kit detection."""

    @staticmethod
    def _make_kit_group(
        sounds: list[dict[str, str]],
        note_rows: list[dict[str, str | None]],
        kit_volume: str = "0x3504F334",
    ) -> InstrumentClipGroup:
        """Build a minimal InstrumentClipGroup for a kit.

        sounds: list of dicts with keys: name, sideChainSend (optional).
        note_rows: list of dicts with keys: drumIndex, noteDataWithLift (optional),
                   volume (optional, for soundParams).
        kit_volume: hex volume for the clip's <kitParams>.
        """
        # Build the instrument <kit> element with <soundSources>.
        kit_el = etree.Element("kit")
        ss = etree.SubElement(kit_el, "soundSources")
        for s in sounds:
            attrs = {"name": s["name"]}
            if "sideChainSend" in s:
                attrs["sideChainSend"] = s["sideChainSend"]
            etree.SubElement(ss, "sound", **attrs)

        # Build the clip element with <kitParams> and <noteRows>.
        clip_el = etree.Element("instrumentClip")
        etree.SubElement(clip_el, "kitParams", volume=kit_volume)
        nr_el = etree.SubElement(clip_el, "noteRows")
        for nr in note_rows:
            attrs: dict[str, str] = {}
            if nr.get("drumIndex") is not None:
                attrs["drumIndex"] = nr["drumIndex"]
            if nr.get("noteDataWithLift") is not None:
                attrs["noteDataWithLift"] = nr["noteDataWithLift"]
            row = etree.SubElement(nr_el, "noteRow", **attrs)
            if nr.get("volume") is not None:
                etree.SubElement(row, "soundParams", volume=nr["volume"])

        inst_info = InstrumentInfo(
            element=kit_el,
            instrument_type="kit",
            preset_name="TestKit",
            preset_folder="KITS",
        )
        clip_info = ClipInfo(
            element=clip_el,
            section=0,
            preset_name="TestKit",
            preset_folder="KITS",
        )
        return InstrumentClipGroup(
            instrument=inst_info,
            clips_by_section={0: clip_info},
        )

    def test_single_sound_max_sidechain_send(self) -> None:
        """Single-sound kit with max sideChainSend → detected (Path B)."""
        group = self._make_kit_group(
            sounds=[{"name": "KICK", "sideChainSend": str(SIDECHAIN_SEND_MAX)}],
            note_rows=[{"drumIndex": "0", "noteDataWithLift": "0x00000001"}],
        )
        is_sc, reason = is_sidechain_kit(group)
        assert is_sc is True
        assert "single sound" in reason

    def test_single_sound_max_sidechain_normal_volume(self) -> None:
        """Single-sound kit with max sideChainSend and normal volume → still detected (Path B)."""
        group = self._make_kit_group(
            sounds=[{"name": "KICK", "sideChainSend": str(SIDECHAIN_SEND_MAX)}],
            note_rows=[{"drumIndex": "0", "noteDataWithLift": "0x00000001"}],
            kit_volume="0x3504F334",
        )
        is_sc, reason = is_sidechain_kit(group)
        assert is_sc is True
        assert "single sound" in reason

    def test_multi_sound_one_sequenced_row_low_kit_volume(self) -> None:
        """Multi-sound kit, 1 sequenced row, max sideChainSend, low kit volume → detected (Path A)."""
        group = self._make_kit_group(
            sounds=[
                {"name": "KICK", "sideChainSend": str(SIDECHAIN_SEND_MAX)},
                {"name": "SNARE"},
            ],
            note_rows=[
                {"drumIndex": "0", "noteDataWithLift": "0x00000001"},
                {"drumIndex": "1"},
            ],
            kit_volume="0x80000000",  # silent
        )
        is_sc, reason = is_sidechain_kit(group)
        assert is_sc is True
        assert "low kit volume" in reason

    def test_multi_sound_one_sequenced_row_low_row_volume(self) -> None:
        """Multi-sound kit, 1 sequenced row, max sideChainSend, low row volume → detected (Path A)."""
        group = self._make_kit_group(
            sounds=[
                {"name": "KICK", "sideChainSend": str(SIDECHAIN_SEND_MAX)},
                {"name": "SNARE"},
            ],
            note_rows=[
                {"drumIndex": "0", "noteDataWithLift": "0x00000001", "volume": "0x80000000"},
                {"drumIndex": "1"},
            ],
            kit_volume="0x3504F334",  # normal kit volume
        )
        is_sc, reason = is_sidechain_kit(group)
        assert is_sc is True
        assert "low row volume" in reason

    def test_multi_sound_multiple_sequenced_rows(self) -> None:
        """Multi-sound kit with multiple sequenced rows → NOT detected (normal kit)."""
        group = self._make_kit_group(
            sounds=[
                {"name": "KICK", "sideChainSend": str(SIDECHAIN_SEND_MAX)},
                {"name": "SNARE"},
            ],
            note_rows=[
                {"drumIndex": "0", "noteDataWithLift": "0x00000001"},
                {"drumIndex": "1", "noteDataWithLift": "0x00000002"},
            ],
            kit_volume="0x80000000",
        )
        is_sc, reason = is_sidechain_kit(group)
        assert is_sc is False
        assert reason == ""

    def test_no_sidechain_send_attribute(self) -> None:
        """Kit with no sideChainSend attribute → NOT detected."""
        group = self._make_kit_group(
            sounds=[{"name": "KICK"}],
            note_rows=[{"drumIndex": "0", "noteDataWithLift": "0x00000001"}],
        )
        is_sc, reason = is_sidechain_kit(group)
        assert is_sc is False

    def test_sidechain_send_well_below_max(self) -> None:
        """Kit with sideChainSend well below max → NOT detected."""
        group = self._make_kit_group(
            sounds=[{"name": "KICK", "sideChainSend": "1000000"}],
            note_rows=[{"drumIndex": "0", "noteDataWithLift": "0x00000001"}],
            kit_volume="0x80000000",
        )
        is_sc, reason = is_sidechain_kit(group)
        assert is_sc is False

    def test_near_max_sidechain_send_within_threshold(self) -> None:
        """sideChainSend at 99% of max (just at threshold) → detected."""
        group = self._make_kit_group(
            sounds=[{"name": "KICK", "sideChainSend": str(SIDECHAIN_SEND_THRESHOLD)}],
            note_rows=[{"drumIndex": "0", "noteDataWithLift": "0x00000001"}],
        )
        is_sc, reason = is_sidechain_kit(group)
        assert is_sc is True

    def test_multi_sound_normal_volume_not_detected(self) -> None:
        """Multi-sound kit, 1 sequenced row, max sideChainSend but normal volume → NOT detected."""
        group = self._make_kit_group(
            sounds=[
                {"name": "KICK", "sideChainSend": str(SIDECHAIN_SEND_MAX)},
                {"name": "SNARE"},
            ],
            note_rows=[
                {"drumIndex": "0", "noteDataWithLift": "0x00000001"},
                {"drumIndex": "1"},
            ],
            kit_volume="0x3504F334",  # init kit volume (normal)
        )
        is_sc, reason = is_sidechain_kit(group)
        assert is_sc is False


# ---------------------------------------------------------------------------
# Phase 4: Test Song Filtering — directory exclusion
# ---------------------------------------------------------------------------


class TestDiscoverSongsExcludeDir:
    """Tests for the --exclude-dir directory exclusion in discover_songs()."""

    @staticmethod
    def _write_song(path: Path) -> None:
        """Write a minimal valid song XML at the given path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<song firmwareVersion="c1.2.1">\n'
            "  <instruments/>\n"
            "</song>\n"
        )

    def test_exclude_dirs_none_discovers_all(self, tmp_path: Path) -> None:
        """exclude_dirs=None discovers all songs (existing behaviour)."""
        songs_dir = tmp_path / "SONGS"
        self._write_song(songs_dir / "A.XML")
        self._write_song(songs_dir / "testing" / "B.XML")

        results = discover_songs(tmp_path, exclude_dirs=None)
        names = {p.name for p, _ in results}
        assert names == {"A.XML", "B.XML"}

    def test_exclude_single_dir(self, tmp_path: Path) -> None:
        """exclude_dirs=['testing'] excludes songs in testing/ subdirectory."""
        songs_dir = tmp_path / "SONGS"
        self._write_song(songs_dir / "A.XML")
        self._write_song(songs_dir / "testing" / "B.XML")
        self._write_song(songs_dir / "testing" / "C.XML")

        results = discover_songs(tmp_path, exclude_dirs=["testing"])
        names = {p.name for p, _ in results}
        assert names == {"A.XML"}

    def test_exclude_multiple_dirs(self, tmp_path: Path) -> None:
        """Multiple exclude_dirs values exclude multiple subdirectories."""
        songs_dir = tmp_path / "SONGS"
        self._write_song(songs_dir / "A.XML")
        self._write_song(songs_dir / "testing" / "B.XML")
        self._write_song(songs_dir / "drafts" / "C.XML")

        results = discover_songs(tmp_path, exclude_dirs=["testing", "drafts"])
        names = {p.name for p, _ in results}
        assert names == {"A.XML"}

    def test_top_level_songs_never_excluded(self, tmp_path: Path) -> None:
        """Songs at top level of SONGS/ are never excluded."""
        songs_dir = tmp_path / "SONGS"
        self._write_song(songs_dir / "A.XML")
        self._write_song(songs_dir / "B.XML")

        results = discover_songs(tmp_path, exclude_dirs=["testing"])
        names = {p.name for p, _ in results}
        assert names == {"A.XML", "B.XML"}

    def test_exclude_nested_subdir(self, tmp_path: Path) -> None:
        """Songs in nested subdirectories of an excluded dir are also excluded."""
        songs_dir = tmp_path / "SONGS"
        self._write_song(songs_dir / "A.XML")
        self._write_song(songs_dir / "testing" / "sub" / "B.XML")

        results = discover_songs(tmp_path, exclude_dirs=["testing"])
        names = {p.name for p, _ in results}
        assert names == {"A.XML"}

    def test_exclude_prints_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A message is printed when songs are excluded."""
        songs_dir = tmp_path / "SONGS"
        self._write_song(songs_dir / "A.XML")
        self._write_song(songs_dir / "testing" / "B.XML")
        self._write_song(songs_dir / "testing" / "C.XML")

        discover_songs(tmp_path, exclude_dirs=["testing"])
        captured = capsys.readouterr().out
        assert "Excluding 2 song(s) from testing/" in captured

    def test_exclude_is_case_insensitive(self, tmp_path: Path) -> None:
        """Exclusion matching is case-insensitive."""
        songs_dir = tmp_path / "SONGS"
        self._write_song(songs_dir / "A.XML")
        self._write_song(songs_dir / "Testing" / "B.XML")

        results = discover_songs(tmp_path, exclude_dirs=["testing"])
        names = {p.name for p, _ in results}
        assert names == {"A.XML"}
