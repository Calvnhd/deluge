#!/usr/bin/env python3
"""
Generate manifests of Deluge SD card contents.

Creates 4 pairs of manifest files (markdown + CSV) in docs/:
  - manifest-kits: Kit names, samples used, firmware version
  - manifest-synths: Synth names, samples used (if any), firmware version
  - manifest-songs: Song names, instruments used, firmware version
  - manifest-samples: Used/unused samples, sizes, broken references

Usage: ./scripts/create-manifest.py

IMPORTANT: This script is READ-ONLY with respect to the DELUGE/ folder.
It MUST NEVER modify any .XML or .wav files. All output is written to docs/.
This is a hard requirement to protect the integrity of Deluge SD card data.
"""

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import NamedTuple


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class KitInfo:
    name: str
    path: str
    samples: list[str]
    modified: datetime
    firmware_version: str = ""


@dataclass
class SynthInfo:
    name: str
    path: str
    samples: list[str]
    modified: datetime
    firmware_version: str = ""


@dataclass
class SongInfo:
    name: str
    path: str
    kits: list[str]
    synths: list[str]
    audio_tracks: dict[str, str]  # track_name -> sample_path (or empty if no sample)
    midi_channels: list[int]
    has_arrangement: bool
    modified: datetime
    firmware_version: str = ""


@dataclass
class SampleInfo:
    path: str
    size_bytes: int
    modified: datetime
    used_by: list[str] = field(default_factory=list)


class ManifestData(NamedTuple):
    kits: list[KitInfo]
    synths: list[SynthInfo]
    songs: list[SongInfo]
    samples_used: list[SampleInfo]
    samples_unused: list[SampleInfo]
    broken_refs: dict[str, list[str]]  # xml_path -> list of missing sample paths
    firmware_versions: set[str]


# =============================================================================
# XML Parsing
# =============================================================================

def parse_deluge_xml(xml_path: Path) -> ET.Element | None:
    """
    Parse a Deluge XML file, handling both old and new formats.
    
    Old format has multiple root elements (firmwareVersion, kit/sound/song).
    New format has a single root element with firmwareVersion as attribute.
    """
    try:
        # Try standard parsing first (new format)
        tree = ET.parse(xml_path)
        return tree.getroot()
    except ET.ParseError as e:
        if "junk after document element" in str(e):
            # Old format - wrap in synthetic root
            try:
                with open(xml_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Remove XML declaration if present and wrap
                if content.startswith('<?xml'):
                    content = content.split('?>', 1)[1]
                wrapped = f"<root>{content}</root>"
                return ET.fromstring(wrapped)
            except Exception:
                return None
        return None


def extract_firmware_version(root: ET.Element) -> str:
    """Extract firmware version from XML root element."""
    # Check if this is a wrapped root (old format)
    if root.tag == 'root':
        fw_elem = root.find('firmwareVersion')
        if fw_elem is not None and fw_elem.text:
            return fw_elem.text.strip()
    
    # Try attribute first (newer format)
    version = root.get('firmwareVersion', '')
    if version:
        return version
    
    # Try child element (older format)
    fw_elem = root.find('firmwareVersion')
    if fw_elem is not None and fw_elem.text:
        return fw_elem.text.strip()
    
    return ""


def get_actual_root(root: ET.Element, expected_tag: str) -> ET.Element | None:
    """Get the actual root element, handling wrapped old-format XMLs."""
    if root.tag == 'root':
        # Old format - find the actual element
        actual = root.find(expected_tag)
        return actual
    elif root.tag == expected_tag:
        return root
    return None


def extract_sample_paths(root: ET.Element) -> list[str]:
    """Extract all sample file paths from an XML element tree.
    
    Handles multiple formats:
    - Old format: <fileName>SAMPLES/path/file.wav</fileName>
    - New format: <osc1 fileName="SAMPLES/path/file.wav" ...>
    - Audio clips: <audioClip filePath="SAMPLES/path/file.wav" ...>
    """
    samples = []
    
    # Method 1: <fileName> child elements (old format)
    for filename_elem in root.iter('fileName'):
        if filename_elem.text and filename_elem.text.strip():
            path = filename_elem.text.strip()
            if path.upper().startswith('SAMPLES/'):
                samples.append(path)
    
    # Method 2: fileName attribute on osc1, osc2, and other elements (new format)
    for elem in root.iter():
        filename_attr = elem.get('fileName')
        if filename_attr and filename_attr.strip():
            path = filename_attr.strip()
            if path.upper().startswith('SAMPLES/'):
                samples.append(path)
    
    # Method 3: filePath attribute on audioClip elements
    for elem in root.iter('audioClip'):
        filepath_attr = elem.get('filePath')
        if filepath_attr and filepath_attr.strip():
            path = filepath_attr.strip()
            if path.upper().startswith('SAMPLES/'):
                samples.append(path)
    
    return list(set(samples))  # Deduplicate


def extract_instruments_from_song(root: ET.Element) -> tuple[list[str], list[str], dict[str, str], list[int], bool]:
    """Extract instrument information from a song XML.
    
    Returns:
        Tuple of (kits, synths, audio_tracks, midi_channels, has_arrangement)
        - audio_tracks is a dict mapping track name to sample file path
        
    Note: CV/gate outputs are intentionally not tracked. The project owner does not
    use CV and has chosen to exclude it from the manifest for simplicity.
    """
    kits = []
    synths = []
    audio_tracks: dict[str, str] = {}  # track_name -> sample_path
    midi_channels = []
    has_arrangement = False
    
    instruments = root.find('instruments')
    if instruments is None:
        return [], [], {}, [], False
    
    # Find all kit elements
    for kit in instruments.findall('kit'):
        name = kit.get('presetName', '')
        folder = kit.get('presetFolder', 'KITS')
        if name:
            full_path = f"{folder}/{name}" if folder else name
            kits.append(full_path)
        elif kit.get('presetSlot'):
            # Older format with slot number - use folder if available
            slot = kit.get('presetSlot', '')
            folder = kit.get('presetFolder', 'KITS')
            kits.append(f"{folder}/KIT{slot.zfill(3)}")
        # Check for arrangement data
        if kit.get('clipInstances'):
            has_arrangement = True
    
    # Find all sound elements that are synths (direct children of instruments)
    for sound in instruments.findall('sound'):
        name = sound.get('presetName', '')
        folder = sound.get('presetFolder', 'SYNTHS')
        if name:
            full_path = f"{folder}/{name}" if folder else name
            synths.append(full_path)
        elif sound.get('presetSlot'):
            # Older format with slot number - use folder if available
            slot = sound.get('presetSlot', '')
            folder = sound.get('presetFolder', 'SYNTHS')
            synths.append(f"{folder}/SYNT{slot.zfill(3)}")
        # Check for arrangement data
        if sound.get('clipInstances'):
            has_arrangement = True
    
    # Find all audio tracks - just get track names from instruments section
    # Sample paths come from audioClip elements
    for audio in instruments.findall('audioTrack'):
        name = audio.get('name', 'unnamed')
        audio_tracks[name] = ''  # Initialize with no sample, filled in from audioClips
        # Check for arrangement data
        if audio.get('clipInstances'):
            has_arrangement = True
    
    # Find all audioClip elements to get sample paths for each track
    # audioClip has trackName (matches audioTrack name) and filePath (the sample)
    for clip in root.iter('audioClip'):
        track_name = clip.get('trackName', '')
        file_path = clip.get('filePath', '')
        if track_name and file_path:
            # Store the sample path (may overwrite if multiple clips, but usually same track = same file)
            audio_tracks[track_name] = file_path
        elif track_name and track_name not in audio_tracks:
            # Track exists but has no sample loaded yet
            audio_tracks[track_name] = ''
    
    # Find all MIDI channels
    for midi in instruments.findall('midiChannel'):
        channel = midi.get('channel')
        if channel is not None:
            try:
                midi_channels.append(int(channel))
            except ValueError:
                pass
        # Check for arrangement data
        if midi.get('clipInstances'):
            has_arrangement = True
    
    return list(set(kits)), list(set(synths)), audio_tracks, sorted(set(midi_channels)), has_arrangement


def parse_kit(xml_path: Path) -> KitInfo | None:
    """Parse a kit XML file."""
    root = parse_deluge_xml(xml_path)
    if root is None:
        print(f"  ⚠ Failed to parse {xml_path.name}", file=sys.stderr)
        return None
    
    kit_root = get_actual_root(root, 'kit')
    if kit_root is None:
        return None
    
    samples = extract_sample_paths(kit_root)
    firmware = extract_firmware_version(root)
    modified = datetime.fromtimestamp(xml_path.stat().st_mtime)
    
    # Get relative path from KITS folder
    rel_path = str(xml_path.relative_to(xml_path.parent.parent))
    name = xml_path.stem
    
    return KitInfo(
        name=name,
        path=rel_path,
        samples=sorted(samples),
        modified=modified,
        firmware_version=firmware
    )


def parse_synth(xml_path: Path) -> SynthInfo | None:
    """Parse a synth XML file."""
    root = parse_deluge_xml(xml_path)
    if root is None:
        print(f"  ⚠ Failed to parse {xml_path.name}", file=sys.stderr)
        return None
    
    synth_root = get_actual_root(root, 'sound')
    if synth_root is None:
        return None
    
    samples = extract_sample_paths(synth_root)
    firmware = extract_firmware_version(root)
    modified = datetime.fromtimestamp(xml_path.stat().st_mtime)
    
    rel_path = str(xml_path.relative_to(xml_path.parent.parent))
    name = xml_path.stem
    
    return SynthInfo(
        name=name,
        path=rel_path,
        samples=sorted(samples),
        modified=modified,
        firmware_version=firmware
    )


def parse_song(xml_path: Path) -> SongInfo | None:
    """Parse a song XML file."""
    root = parse_deluge_xml(xml_path)
    if root is None:
        print(f"  ⚠ Failed to parse {xml_path.name}", file=sys.stderr)
        return None
    
    song_root = get_actual_root(root, 'song')
    if song_root is None:
        return None
    
    kits, synths, audio_tracks, midi_channels, has_arrangement = extract_instruments_from_song(song_root)
    firmware = extract_firmware_version(root)
    modified = datetime.fromtimestamp(xml_path.stat().st_mtime)
    
    rel_path = str(xml_path.relative_to(xml_path.parent.parent))
    name = xml_path.stem
    
    return SongInfo(
        name=name,
        path=rel_path,
        kits=sorted(kits),
        synths=sorted(synths),
        audio_tracks=audio_tracks,
        midi_channels=midi_channels,
        has_arrangement=has_arrangement,
        modified=modified,
        firmware_version=firmware
    )


# =============================================================================
# Data Collection
# =============================================================================

def extract_audio_clip_samples(root: ET.Element) -> dict[str, str]:
    """Extract mapping of sample paths to audio track names from song XML.
    
    Returns:
        Dict mapping sample_path -> track_name for all audioClip elements
    """
    result = {}
    for clip in root.iter('audioClip'):
        track_name = clip.get('trackName', '')
        file_path = clip.get('filePath', '')
        if track_name and file_path and file_path.upper().startswith('SAMPLES/'):
            result[file_path] = track_name
    return result


def extract_embedded_instrument_samples(root: ET.Element, song_name: str) -> dict[str, str]:
    """Extract sample paths from embedded instruments in a song, with usage descriptions.
    
    Songs contain embedded copies of kit/synth configurations in <instruments>.
    This function extracts samples from those embedded instruments.
    
    Returns:
        Dict mapping sample_path -> usage_description
    """
    result = {}
    instruments = root.find('instruments')
    if instruments is None:
        return result
    
    # Extract samples from embedded kits
    for kit in instruments.findall('kit'):
        kit_name = kit.get('presetName', '')
        if not kit_name and kit.get('presetSlot'):
            # Older format with slot number
            slot = kit.get('presetSlot', '')
            kit_name = f"KIT{slot.zfill(3)}"
        kit_name = kit_name or 'unnamed kit'
        samples = extract_sample_paths(kit)
        for sample in samples:
            result[sample] = f"Kit: {kit_name} (in {song_name})"
    
    # Extract samples from embedded synths (sound elements)
    for sound in instruments.findall('sound'):
        synth_name = sound.get('presetName', '')
        if not synth_name and sound.get('presetSlot'):
            # Older format with slot number
            slot = sound.get('presetSlot', '')
            synth_name = f"SYNT{slot.zfill(3)}"
        synth_name = synth_name or 'unnamed synth'
        samples = extract_sample_paths(sound)
        for sample in samples:
            result[sample] = f"Synth: {synth_name} (in {song_name})"
    
    return result


def collect_manifest_data(deluge_path: Path) -> ManifestData:
    """Scan DELUGE folder and collect all manifest data."""
    kits: list[KitInfo] = []
    synths: list[SynthInfo] = []
    songs: list[SongInfo] = []
    all_sample_refs: dict[str, list[str]] = {}  # sample_path -> list of usage descriptions
    broken_refs: dict[str, list[str]] = {}  # xml_path -> list of missing samples
    firmware_versions: set[str] = set()
    
    kits_path = deluge_path / 'KITS'
    synths_path = deluge_path / 'SYNTHS'
    songs_path = deluge_path / 'SONGS'
    samples_path = deluge_path / 'SAMPLES'
    
    # Parse kits
    print("Scanning kits...")
    if kits_path.exists():
        for xml_file in sorted(kits_path.rglob('*.XML')):
            kit = parse_kit(xml_file)
            if kit:
                kits.append(kit)
                if kit.firmware_version:
                    firmware_versions.add(kit.firmware_version)
                
                # Track kit sample references with descriptive name
                usage_desc = f"Kit: {kit.name}"
                for sample in kit.samples:
                    all_sample_refs.setdefault(sample, []).append(usage_desc)
    
    # Parse synths
    print("Scanning synths...")
    if synths_path.exists():
        for xml_file in sorted(synths_path.rglob('*.XML')):
            synth = parse_synth(xml_file)
            if synth:
                synths.append(synth)
                if synth.firmware_version:
                    firmware_versions.add(synth.firmware_version)
                
                # Track synth sample references with descriptive name
                usage_desc = f"Synth: {synth.name}"
                for sample in synth.samples:
                    all_sample_refs.setdefault(sample, []).append(usage_desc)
    
    # Parse songs
    print("Scanning songs...")
    if songs_path.exists():
        for xml_file in sorted(songs_path.rglob('*.XML')):
            song = parse_song(xml_file)
            if song:
                songs.append(song)
                if song.firmware_version:
                    firmware_versions.add(song.firmware_version)
                
                # Songs reference samples in multiple ways
                root = parse_deluge_xml(xml_file)
                if root is not None:
                    song_root = get_actual_root(root, 'song')
                    if song_root is not None:
                        # 1. Audio clip samples - track with audio track name and song
                        audio_clip_samples = extract_audio_clip_samples(song_root)
                        for sample_path, track_name in audio_clip_samples.items():
                            usage_desc = f"Audio: {track_name} (in {song.name})"
                            all_sample_refs.setdefault(sample_path, []).append(usage_desc)
                        
                        # 2. Embedded instrument samples (kits/synths within the song)
                        embedded_samples = extract_embedded_instrument_samples(song_root, song.name)
                        for sample_path, usage_desc in embedded_samples.items():
                            all_sample_refs.setdefault(sample_path, []).append(usage_desc)
    
    # Collect all actual sample files
    print("Scanning samples...")
    actual_samples: dict[str, SampleInfo] = {}
    if samples_path.exists():
        for wav_file in sorted(samples_path.rglob('*.wav'), key=lambda p: str(p).lower()):
            rel_path = f"SAMPLES/{wav_file.relative_to(samples_path)}"
            stat = wav_file.stat()
            actual_samples[rel_path] = SampleInfo(
                path=rel_path,
                size_bytes=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime)
            )
        # Also check for .WAV extension
        for wav_file in sorted(samples_path.rglob('*.WAV'), key=lambda p: str(p).lower()):
            rel_path = f"SAMPLES/{wav_file.relative_to(samples_path)}"
            if rel_path not in actual_samples:
                stat = wav_file.stat()
                actual_samples[rel_path] = SampleInfo(
                    path=rel_path,
                    size_bytes=stat.st_size,
                    modified=datetime.fromtimestamp(stat.st_mtime)
                )
    
    # Categorize samples as used/unused and find broken refs
    samples_used: list[SampleInfo] = []
    samples_unused: list[SampleInfo] = []
    
    # Normalize paths for case-insensitive comparison
    actual_samples_lower = {k.lower(): k for k in actual_samples.keys()}
    
    for ref_path, xml_files in all_sample_refs.items():
        ref_lower = ref_path.lower()
        if ref_lower in actual_samples_lower:
            actual_path = actual_samples_lower[ref_lower]
            sample = actual_samples[actual_path]
            sample.used_by.extend(xml_files)
        else:
            # Broken reference
            for xml_file in xml_files:
                broken_refs.setdefault(xml_file, []).append(ref_path)
    
    # Split into used and unused
    for sample in actual_samples.values():
        if sample.used_by:
            samples_used.append(sample)
        else:
            samples_unused.append(sample)
    
    # Sort by path
    samples_used.sort(key=lambda s: s.path.lower())
    samples_unused.sort(key=lambda s: s.path.lower())
    kits.sort(key=lambda k: k.name.lower())
    synths.sort(key=lambda s: s.name.lower())
    songs.sort(key=lambda s: s.name.lower())
    
    return ManifestData(
        kits=kits,
        synths=synths,
        songs=songs,
        samples_used=samples_used,
        samples_unused=samples_unused,
        broken_refs=broken_refs,
        firmware_versions=firmware_versions
    )


# =============================================================================
# Output Formatting
# =============================================================================

def format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_date(dt: datetime) -> str:
    """Format datetime as YYYY-MM-DD."""
    return dt.strftime('%Y-%m-%d')


def generate_kits_md(data: ManifestData, timestamp: datetime) -> str:
    """Generate markdown manifest for kits."""
    lines = []
    
    lines.append("# Kits Manifest")
    lines.append("")
    lines.append(f"Generated: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"**Total: {len(data.kits)} kits**")
    lines.append("")
    
    # Firmware versions in kits
    kit_firmwares = set(k.firmware_version for k in data.kits if k.firmware_version)
    if kit_firmwares:
        lines.append(f"Firmware versions: {', '.join(sorted(kit_firmwares))}")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    for kit in data.kits:
        lines.append(f"## {kit.name}")
        lines.append("")
        lines.append(f"- **Path:** `{kit.path}`")
        lines.append(f"- **Modified:** {format_date(kit.modified)}")
        if kit.firmware_version:
            lines.append(f"- **Firmware:** {kit.firmware_version}")
        lines.append(f"- **Samples ({len(kit.samples)}):**")
        if kit.samples:
            for sample in kit.samples:
                lines.append(f"  - `{sample}`")
        else:
            lines.append("  - *(none)*")
        lines.append("")
    
    return "\n".join(lines)


def generate_kits_csv(data: ManifestData, timestamp: datetime) -> str:
    """Generate CSV manifest for kits."""
    lines = []
    lines.append(f"# Kits Manifest - Generated {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("Name,Path,Modified,Firmware,Sample Count,Samples")
    for kit in data.kits:
        samples_str = "; ".join(kit.samples) if kit.samples else ""
        samples_str = samples_str.replace('"', '""')
        lines.append(f'"{kit.name}","{kit.path}",{format_date(kit.modified)},{kit.firmware_version or ""},{len(kit.samples)},"{samples_str}"')
    return "\n".join(lines)


def generate_synths_md(data: ManifestData, timestamp: datetime) -> str:
    """Generate markdown manifest for synths."""
    lines = []
    
    lines.append("# Synths Manifest")
    lines.append("")
    lines.append(f"Generated: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"**Total: {len(data.synths)} synths**")
    lines.append("")
    
    # Firmware versions in synths
    synth_firmwares = set(s.firmware_version for s in data.synths if s.firmware_version)
    if synth_firmwares:
        lines.append(f"Firmware versions: {', '.join(sorted(synth_firmwares))}")
        lines.append("")
    
    # Count synths with samples
    synths_with_samples = [s for s in data.synths if s.samples]
    if synths_with_samples:
        lines.append(f"Synths using samples: {len(synths_with_samples)}")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    for synth in data.synths:
        lines.append(f"## {synth.name}")
        lines.append("")
        lines.append(f"- **Path:** `{synth.path}`")
        lines.append(f"- **Modified:** {format_date(synth.modified)}")
        if synth.firmware_version:
            lines.append(f"- **Firmware:** {synth.firmware_version}")
        if synth.samples:
            lines.append(f"- **Samples ({len(synth.samples)}):**")
            for sample in synth.samples:
                lines.append(f"  - `{sample}`")
        lines.append("")
    
    return "\n".join(lines)


def generate_synths_csv(data: ManifestData, timestamp: datetime) -> str:
    """Generate CSV manifest for synths."""
    lines = []
    lines.append(f"# Synths Manifest - Generated {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("Name,Path,Modified,Firmware,Sample Count,Samples")
    for synth in data.synths:
        samples_str = "; ".join(synth.samples) if synth.samples else ""
        samples_str = samples_str.replace('"', '""')
        lines.append(f'"{synth.name}","{synth.path}",{format_date(synth.modified)},{synth.firmware_version or ""},{len(synth.samples)},"{samples_str}"')
    return "\n".join(lines)


def generate_songs_md(data: ManifestData, timestamp: datetime) -> str:
    """Generate markdown manifest for songs."""
    lines = []
    
    lines.append("# Songs Manifest")
    lines.append("")
    lines.append(f"Generated: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"**Total: {len(data.songs)} songs**")
    lines.append("")
    
    # Summary stats
    arranged_count = sum(1 for s in data.songs if s.has_arrangement)
    lines.append(f"**With arrangements:** {arranged_count} | **Without:** {len(data.songs) - arranged_count}")
    lines.append("")
    
    # Firmware versions in songs
    song_firmwares = set(s.firmware_version for s in data.songs if s.firmware_version)
    if song_firmwares:
        lines.append(f"Firmware versions: {', '.join(sorted(song_firmwares))}")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    for song in data.songs:
        arrangement_badge = "🎼 " if song.has_arrangement else ""
        lines.append(f"## {arrangement_badge}{song.name}")
        lines.append("")
        lines.append(f"- **Path:** `{song.path}`")
        lines.append(f"- **Modified:** {format_date(song.modified)}")
        lines.append(f"- **Arrangement:** {'Yes' if song.has_arrangement else 'No'}")
        if song.firmware_version:
            lines.append(f"- **Firmware:** {song.firmware_version}")
        
        # Clip types
        if song.kits:
            lines.append(f"- **Kits ({len(song.kits)}):** {', '.join(song.kits)}")
        if song.synths:
            lines.append(f"- **Synths ({len(song.synths)}):** {', '.join(song.synths)}")
        if song.audio_tracks:
            lines.append(f"- **Audio Tracks ({len(song.audio_tracks)}):**")
            for track_name, sample_path in sorted(song.audio_tracks.items()):
                if sample_path:
                    lines.append(f"  - {track_name}: `{sample_path}`")
                else:
                    lines.append(f"  - {track_name}: *(no sample loaded)*")
        if song.midi_channels:
            channels = [str(ch) for ch in song.midi_channels]
            lines.append(f"- **MIDI Channels ({len(song.midi_channels)}):** {', '.join(channels)}")
        lines.append("")
    
    return "\n".join(lines)


def generate_songs_csv(data: ManifestData, timestamp: datetime) -> str:
    """Generate CSV manifest for songs."""
    lines = []
    lines.append(f"# Songs Manifest - Generated {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("Name,Path,Modified,Firmware,Has Arrangement,Kit Count,Synth Count,Audio Track Count,MIDI Channel Count,Kits,Synths,Audio Tracks,MIDI Channels")
    for song in data.songs:
        kits_str = "; ".join(song.kits) if song.kits else ""
        synths_str = "; ".join(song.synths) if song.synths else ""
        # Format audio tracks as "name=path; name2=path2"
        audio_parts = [f"{name}={path}" if path else f"{name}=(none)" for name, path in sorted(song.audio_tracks.items())]
        audio_str = "; ".join(audio_parts) if audio_parts else ""
        midi_str = "; ".join(str(ch) for ch in song.midi_channels) if song.midi_channels else ""
        has_arr = "Yes" if song.has_arrangement else "No"
        lines.append(f'"{song.name}","{song.path}",{format_date(song.modified)},{song.firmware_version or ""},{has_arr},{len(song.kits)},{len(song.synths)},{len(song.audio_tracks)},{len(song.midi_channels)},"{kits_str}","{synths_str}","{audio_str}","{midi_str}"')
    return "\n".join(lines)


def generate_samples_md(data: ManifestData, timestamp: datetime) -> str:
    """Generate markdown manifest for samples."""
    lines = []
    
    total_used_size = sum(s.size_bytes for s in data.samples_used)
    total_unused_size = sum(s.size_bytes for s in data.samples_unused)
    total_size = total_used_size + total_unused_size
    
    lines.append("# Samples Manifest")
    lines.append("")
    lines.append(f"Generated: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Count | Size |")
    lines.append("|----------|-------|------|")
    lines.append(f"| Used | {len(data.samples_used)} | {format_size(total_used_size)} |")
    lines.append(f"| Unused | {len(data.samples_unused)} | {format_size(total_unused_size)} |")
    lines.append(f"| **Total** | **{len(data.samples_used) + len(data.samples_unused)}** | **{format_size(total_size)}** |")
    lines.append("")
    
    # Broken references warning
    if data.broken_refs:
        lines.append("## ⚠️ Broken Sample References")
        lines.append("")
        lines.append("The following XML files reference samples that don't exist:")
        lines.append("")
        for xml_file, missing in sorted(data.broken_refs.items()):
            lines.append(f"**{xml_file}**:")
            for sample in missing:
                lines.append(f"- `{sample}`")
            lines.append("")
    
    # Used samples
    lines.append("---")
    lines.append("")
    lines.append("## Used Samples")
    lines.append("")
    lines.append(f"Total: {len(data.samples_used)} ({format_size(total_used_size)})")
    lines.append("")
    lines.append("| Path | Size | Modified | Used By |")
    lines.append("|------|------|----------|---------|")
    for sample in data.samples_used:
        used_by_str = ", ".join(sample.used_by[:3])
        if len(sample.used_by) > 3:
            used_by_str += f" (+{len(sample.used_by) - 3} more)"
        lines.append(f"| `{sample.path}` | {format_size(sample.size_bytes)} | {format_date(sample.modified)} | {used_by_str} |")
    lines.append("")
    
    # Unused samples
    lines.append("---")
    lines.append("")
    lines.append("## Unused Samples")
    lines.append("")
    lines.append(f"Total: {len(data.samples_unused)} ({format_size(total_unused_size)})")
    lines.append("")
    if data.samples_unused:
        lines.append("| Path | Size | Modified |")
        lines.append("|------|------|----------|")
        for sample in data.samples_unused:
            lines.append(f"| `{sample.path}` | {format_size(sample.size_bytes)} | {format_date(sample.modified)} |")
    else:
        lines.append("*No unused samples found.*")
    lines.append("")
    
    return "\n".join(lines)


def generate_samples_csv(data: ManifestData, timestamp: datetime) -> str:
    """Generate CSV manifest for samples."""
    lines = []
    lines.append(f"# Samples Manifest - Generated {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("Status,Path,Size (bytes),Size (human),Modified,Used By")
    
    for sample in data.samples_used:
        used_by_str = "; ".join(sample.used_by)
        used_by_str = used_by_str.replace('"', '""')
        lines.append(f'USED,"{sample.path}",{sample.size_bytes},{format_size(sample.size_bytes)},{format_date(sample.modified)},"{used_by_str}"')
    
    for sample in data.samples_unused:
        lines.append(f'UNUSED,"{sample.path}",{sample.size_bytes},{format_size(sample.size_bytes)},{format_date(sample.modified)},""')
    
    # Broken references
    if data.broken_refs:
        lines.append("")
        lines.append("# BROKEN REFERENCES")
        lines.append("XML File,Missing Sample")
        for xml_file, missing in sorted(data.broken_refs.items()):
            for sample in missing:
                lines.append(f'"{xml_file}","{sample}"')
    
    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    # Paths
    script_dir = Path(__file__).parent.resolve()
    repo_dir = script_dir.parent
    deluge_path = repo_dir / 'DELUGE'
    docs_path = repo_dir / 'docs'
    
    # Output files - MUST be outside DELUGE folder
    output_files = {
        'kits': (docs_path / 'manifest-kits.md', docs_path / 'manifest-kits.csv'),
        'synths': (docs_path / 'manifest-synths.md', docs_path / 'manifest-synths.csv'),
        'songs': (docs_path / 'manifest-songs.md', docs_path / 'manifest-songs.csv'),
        'samples': (docs_path / 'manifest-samples.md', docs_path / 'manifest-samples.csv'),
    }
    
    # SAFETY CHECK: Ensure no output files are inside DELUGE folder
    # This script must NEVER modify any files in DELUGE/
    for category, (md_file, csv_file) in output_files.items():
        for output_path in [md_file, csv_file]:
            try:
                output_path.resolve().relative_to(deluge_path.resolve())
                print(f"FATAL ERROR: Output file {output_path} is inside DELUGE folder!")
                print("This script must NEVER write to DELUGE/. Aborting.")
                return 1
            except ValueError:
                pass  # Good - output is not inside DELUGE
    
    # Validate DELUGE folder exists
    if not deluge_path.exists():
        print(f"Error: DELUGE folder not found at {deluge_path}")
        return 1
    
    # Ensure docs folder exists
    docs_path.mkdir(parents=True, exist_ok=True)
    
    print("=" * 50)
    print("Deluge Manifest Generator")
    print("=" * 50)
    print(f"Source: {deluge_path}")
    print(f"Output: {docs_path}/manifest-*.md")
    print(f"        {docs_path}/manifest-*.csv")
    print()
    
    # Collect data
    data = collect_manifest_data(deluge_path)
    timestamp = datetime.now()
    
    # Generate and write outputs
    print("\nGenerating manifests...")
    
    # Kits
    with open(output_files['kits'][0], 'w', encoding='utf-8') as f:
        f.write(generate_kits_md(data, timestamp))
    with open(output_files['kits'][1], 'w', encoding='utf-8') as f:
        f.write(generate_kits_csv(data, timestamp))
    
    # Synths
    with open(output_files['synths'][0], 'w', encoding='utf-8') as f:
        f.write(generate_synths_md(data, timestamp))
    with open(output_files['synths'][1], 'w', encoding='utf-8') as f:
        f.write(generate_synths_csv(data, timestamp))
    
    # Songs
    with open(output_files['songs'][0], 'w', encoding='utf-8') as f:
        f.write(generate_songs_md(data, timestamp))
    with open(output_files['songs'][1], 'w', encoding='utf-8') as f:
        f.write(generate_songs_csv(data, timestamp))
    
    # Samples
    with open(output_files['samples'][0], 'w', encoding='utf-8') as f:
        f.write(generate_samples_md(data, timestamp))
    with open(output_files['samples'][1], 'w', encoding='utf-8') as f:
        f.write(generate_samples_csv(data, timestamp))
    
    # Remove old combined manifest files if they exist
    old_files = [docs_path / 'manifest.md', docs_path / 'manifest.csv']
    for old_file in old_files:
        if old_file.exists():
            old_file.unlink()
            print(f"  Removed old file: {old_file.name}")
    
    # Print summary
    total_used_size = sum(s.size_bytes for s in data.samples_used)
    total_unused_size = sum(s.size_bytes for s in data.samples_unused)
    
    print()
    print("=" * 50)
    print("Manifests generated!")
    print("=" * 50)
    print(f"Kits:            {len(data.kits)}")
    print(f"Synths:          {len(data.synths)}")
    print(f"Songs:           {len(data.songs)}")
    print(f"Samples (used):  {len(data.samples_used)} ({format_size(total_used_size)})")
    print(f"Samples (unused):{len(data.samples_unused)} ({format_size(total_unused_size)})")
    
    if data.broken_refs:
        broken_count = sum(len(v) for v in data.broken_refs.values())
        print()
        print(f"⚠️  WARNING: {broken_count} broken sample reference(s) found!")
        print("   See manifest-samples.md for details.")
    
    if data.firmware_versions:
        print()
        print(f"Firmware versions: {', '.join(sorted(data.firmware_versions))}")
    
    print()
    print("Output files:")
    for category, (md_file, csv_file) in output_files.items():
        print(f"  {md_file.name}, {csv_file.name}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
