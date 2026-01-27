"""
Deluge SDK - Library for parsing and working with Deluge SD card contents.

This module provides data structures and parsing functions for reading
Deluge XML files (kits, synths, songs) and tracking sample usage.

IMPORTANT: This library is READ-ONLY. It must NEVER modify any .XML or .wav files.
All functions only read data from the filesystem.

Usage:
    from deluge_sdk import parse_kit, parse_synth, parse_song, KitInfo, SynthInfo, SongInfo
    
    kit = parse_kit(Path("DELUGE/KITS/KIT000.XML"))
    if kit:
        print(f"Kit {kit.name} uses {len(kit.samples)} samples")
"""

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
    """Information about a Deluge kit preset."""
    name: str
    path: str
    samples: list[str]
    modified: datetime
    firmware_version: str = ""


@dataclass
class SynthInfo:
    """Information about a Deluge synth preset."""
    name: str
    path: str
    samples: list[str]
    modified: datetime
    firmware_version: str = ""


@dataclass
class SongInfo:
    """Information about a Deluge song."""
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
    """Information about a sample file."""
    path: str
    size_bytes: int
    modified: datetime
    used_by: list[str] = field(default_factory=list)


class ManifestData(NamedTuple):
    """Complete manifest data for a Deluge SD card."""
    kits: list[KitInfo]
    synths: list[SynthInfo]
    songs: list[SongInfo]
    samples_used: list[SampleInfo]
    samples_unused: list[SampleInfo]
    broken_refs: dict[str, list[str]]  # xml_path -> list of missing sample paths
    firmware_versions: set[str]


# =============================================================================
# XML Parsing - Low Level
# =============================================================================

def parse_deluge_xml(xml_path: Path) -> ET.Element | None:
    """
    Parse a Deluge XML file, handling both old and new formats.
    
    Old format has multiple root elements (firmwareVersion, kit/sound/song).
    New format has a single root element with firmwareVersion as attribute.
    
    Args:
        xml_path: Path to the XML file
        
    Returns:
        Root element of the parsed XML, or None if parsing failed
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
    """
    Extract firmware version from XML root element.
    
    Handles multiple formats:
    - Wrapped root with <firmwareVersion> child element (very old format)
    - firmwareVersion attribute on root element (v4.x format)
    - <firmwareVersion> child element (v2.x format)
    
    Args:
        root: Root element of parsed XML
        
    Returns:
        Firmware version string, or empty string if not found
    """
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
    """
    Get the actual root element, handling wrapped old-format XMLs.
    
    Args:
        root: Root element (may be synthetic wrapper)
        expected_tag: The tag name we're looking for (e.g., 'kit', 'sound', 'song')
        
    Returns:
        The actual root element, or None if not found
    """
    if root.tag == 'root':
        # Old format - find the actual element
        actual = root.find(expected_tag)
        return actual
    elif root.tag == expected_tag:
        return root
    return None


# =============================================================================
# XML Parsing - Sample Extraction
# =============================================================================

def extract_sample_paths(root: ET.Element) -> list[str]:
    """
    Extract all sample file paths from an XML element tree.
    
    Handles multiple formats:
    - Old format: <fileName>SAMPLES/path/file.wav</fileName>
    - New format: <osc1 fileName="SAMPLES/path/file.wav" ...>
    - Audio clips: <audioClip filePath="SAMPLES/path/file.wav" ...>
    
    Args:
        root: XML element to search within
        
    Returns:
        List of unique sample paths found
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


def extract_audio_clip_samples(root: ET.Element) -> dict[str, str]:
    """
    Extract mapping of sample paths to audio track names from song XML.
    
    Args:
        root: Song XML root element
        
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
    """
    Extract sample paths from embedded instruments in a song, with usage descriptions.
    
    Songs contain embedded copies of kit/synth configurations in <instruments>.
    This function extracts samples from those embedded instruments.
    
    Args:
        root: Song XML root element
        song_name: Name of the song (for usage descriptions)
        
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


# =============================================================================
# XML Parsing - Instrument Extraction
# =============================================================================

def extract_instruments_from_song(root: ET.Element) -> tuple[list[str], list[str], dict[str, str], list[int], bool]:
    """
    Extract instrument information from a song XML.
    
    Args:
        root: Song XML root element
        
    Returns:
        Tuple of (kits, synths, audio_tracks, midi_channels, has_arrangement)
        - kits: List of kit preset paths
        - synths: List of synth preset paths
        - audio_tracks: Dict mapping track name to sample file path
        - midi_channels: List of MIDI channel numbers
        - has_arrangement: True if song has arrangement data
        
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


# =============================================================================
# High-Level Parsing Functions
# =============================================================================

def parse_kit(xml_path: Path) -> KitInfo | None:
    """
    Parse a kit XML file.
    
    Args:
        xml_path: Path to the kit XML file
        
    Returns:
        KitInfo object, or None if parsing failed
    """
    root = parse_deluge_xml(xml_path)
    if root is None:
        return None
    
    kit_root = get_actual_root(root, 'kit')
    if kit_root is None:
        return None
    
    samples = extract_sample_paths(kit_root)
    firmware = extract_firmware_version(root)
    modified = datetime.fromtimestamp(xml_path.stat().st_mtime)
    
    # Get relative path from parent's parent (assumes DELUGE/KITS/file.XML structure)
    try:
        rel_path = str(xml_path.relative_to(xml_path.parent.parent))
    except ValueError:
        rel_path = xml_path.name
    name = xml_path.stem
    
    return KitInfo(
        name=name,
        path=rel_path,
        samples=sorted(samples),
        modified=modified,
        firmware_version=firmware
    )


def parse_synth(xml_path: Path) -> SynthInfo | None:
    """
    Parse a synth XML file.
    
    Args:
        xml_path: Path to the synth XML file
        
    Returns:
        SynthInfo object, or None if parsing failed
    """
    root = parse_deluge_xml(xml_path)
    if root is None:
        return None
    
    synth_root = get_actual_root(root, 'sound')
    if synth_root is None:
        return None
    
    samples = extract_sample_paths(synth_root)
    firmware = extract_firmware_version(root)
    modified = datetime.fromtimestamp(xml_path.stat().st_mtime)
    
    try:
        rel_path = str(xml_path.relative_to(xml_path.parent.parent))
    except ValueError:
        rel_path = xml_path.name
    name = xml_path.stem
    
    return SynthInfo(
        name=name,
        path=rel_path,
        samples=sorted(samples),
        modified=modified,
        firmware_version=firmware
    )


def parse_song(xml_path: Path) -> SongInfo | None:
    """
    Parse a song XML file.
    
    Args:
        xml_path: Path to the song XML file
        
    Returns:
        SongInfo object, or None if parsing failed
    """
    root = parse_deluge_xml(xml_path)
    if root is None:
        return None
    
    song_root = get_actual_root(root, 'song')
    if song_root is None:
        return None
    
    kits, synths, audio_tracks, midi_channels, has_arrangement = extract_instruments_from_song(song_root)
    firmware = extract_firmware_version(root)
    modified = datetime.fromtimestamp(xml_path.stat().st_mtime)
    
    try:
        rel_path = str(xml_path.relative_to(xml_path.parent.parent))
    except ValueError:
        rel_path = xml_path.name
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
# Utility Functions
# =============================================================================

def format_size(size_bytes: int) -> str:
    """
    Format byte size as human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human-readable size string (e.g., "1.5 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_date(dt: datetime) -> str:
    """
    Format datetime as YYYY-MM-DD.
    
    Args:
        dt: Datetime object
        
    Returns:
        Date string in YYYY-MM-DD format
    """
    return dt.strftime('%Y-%m-%d')
