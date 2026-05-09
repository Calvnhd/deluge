# Deluge CLI v0.1
"""Deluge SDK — Deluge filesystem discovery, reference extraction, and in-place updating."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from lxml import etree

from deluge_lib.scanning import normalise_key, scan_tree

# 64 KiB read chunks for hashing large WAV files
_HASH_CHUNK_SIZE = 1024 * 64

# The three standard Deluge SD card subdirectories containing XML presets.
_DELUGE_SUBDIRS = ("KITS", "SYNTHS", "SONGS")

# Tag-to-type mapping for path-based XML type detection.
_PATH_TYPE_MAP = {"KITS": "kit", "SYNTHS": "synth", "SONGS": "song"}

# Tags that carry element-style or attribute-style fileName references.
_OSC_AND_RANGE_TAGS = ("osc1", "osc2", "sampleRange")


@dataclass
class SampleRef:
    # TODO-v0.1-REVIEW
    """A single sample reference found in a Deluge XML file."""

    # Sample path as written in the XML, relative to DELUGE/ (e.g. "SAMPLES/DRUMS/Kick/808 Kick.wav")
    path: str
    # Path to the XML file containing this reference, relative to DELUGE_ROOT (e.g. "KITS/KIT001.XML")
    xml_file: Path
    # Type of the XML file: "kit", "synth", or "song"
    xml_type: str
    # Name of the preset/track containing this reference:
    #   Standalone kit/synth: XML filename without extension (e.g. "KIT001")
    #   Song-embedded kit/synth: presetName attribute (e.g. "K01Perc2")
    #   Song audioClip: trackName attribute (e.g. "AUDIO2")
    preset_name: str
    # XML format of the reference: "fileName-element", "fileName-attribute", or "filePath-attribute"
    ref_type: str
    # XML element holding the reference: "osc1", "osc2", "sampleRange", or "audioClip"
    element_tag: str


def hash_file(path: Path) -> str:
    """Compute a SHA256 hex digest for a file, reading in chunks.

    Args:
        path: Path to the file to hash.

    Returns:
        Lowercase hex digest string.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def find_all_wav_files(samples_dir: Path) -> list[Path]:
    """Recursively find all .wav/.WAV files under a directory.

    Returns sorted absolute paths
    """
    if not samples_dir.is_dir():
        print(f"WARNING: samples directory does not exist: {samples_dir}")
        return []
    scan = scan_tree(samples_dir, label="samples", file_filter="wav")
    return sorted(samples_dir / entry.rel_path for entry in scan.files.values())


def get_existing_samples(deluge_root: Path) -> set[str]:
    # TODO-v0.1-REVIEW
    """Build a normalised set of all WAV sample paths under DELUGE/SAMPLES/.

    Returns a set of lowercase, forward-slash paths relative to *deluge_root*,
    suitable for case-insensitive existence checks via ``normalise_key()``.
    """
    samples_dir = deluge_root / "SAMPLES"
    if not samples_dir.is_dir():
        return set()
    scan = scan_tree(samples_dir, label="SAMPLES", file_filter="wav")
    return {normalise_key(Path("SAMPLES") / e.rel_path) for e in scan.files.values()}


def hash_all_samples(deluge_root: Path) -> dict[str, list[str]]:
    """Hash all WAV files under ``deluge_root / "SAMPLES"`` and group by digest.

    Args:
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        Mapping of SHA-256 hex digests to lists of relative paths
    """
    samples_dir = deluge_root / "SAMPLES"
    wav_files = find_all_wav_files(samples_dir)

    hashes: dict[str, list[str]] = defaultdict(list)
    total = len(wav_files)
    for i, wav_path in enumerate(wav_files, 1):
        print(f"\rHashing {i}/{total}...", end="", flush=True)
        digest = hash_file(wav_path)
        rel_path = str(PurePosixPath(wav_path.relative_to(deluge_root)))
        hashes[digest].append(rel_path)
    if total > 0:
        print()

    return dict(hashes)


def find_all_xml_files(deluge_root: Path) -> list[Path]:
    # TODO-v0.1-REVIEW
    """Recursively find all XML files in KITS/, SYNTHS/, SONGS/ under *deluge_root*.

    Returns a sorted list of absolute paths.  Missing subdirectories are skipped.
    """
    results: list[Path] = []
    for subdir in _DELUGE_SUBDIRS:
        d = deluge_root / subdir
        if not d.is_dir():
            continue
        # Not optimal to use scan_tree because we throw away so much of the result
        # Consider writing something bespoke
        scan = scan_tree(d, label=subdir, file_filter="xml")
        for entry in scan.files.values():
            results.append(d / entry.rel_path)
    return sorted(results)


def detect_xml_type(xml_path: Path) -> str:
    # TODO-v0.1-REVIEW
    """Determine the Deluge XML type from the file's path.

    Returns ``"kit"``, ``"synth"``, or ``"song"``.
    Raises :class:`ValueError` if the path does not contain a recognised directory.
    """
    parts = xml_path.parts
    for part in parts:
        if part in _PATH_TYPE_MAP:
            return _PATH_TYPE_MAP[part]
    msg = f"{xml_path} does not contain KITS, SYNTHS, or SONGS in its path"
    raise ValueError(msg)


def _get_preset_name(
    element: etree._Element,
    xml_type: str,
    xml_path: Path,
) -> str:
    # TODO-v0.1-REVIEW
    """Walk up the element tree to determine the preset/instrument name.

    - **Standalone presets** (kit/synth outside a song): use ``xml_path.stem``.
    - **Song-embedded instruments**: walk up until we find the element whose
      parent is ``<instruments>``, then read its ``presetName`` attribute.
    - **audioClip**: use the ``trackName`` attribute on the element itself.
    """
    if element.tag == "audioClip":
        return element.get("trackName", "unknown")

    if xml_type != "song":
        return xml_path.stem

    # Song-embedded instrument: walk up to find the instrument element
    # (direct child of <instruments>).
    current: etree._Element | None = element
    while current is not None:
        parent = current.getparent()
        if parent is not None and parent.tag == "instruments":
            name = current.get("presetName")
            return name if name else "unknown"
        current = parent

    return "unknown"


def parse_deluge_xml(
    xml_path: Path,
) -> tuple[etree._ElementTree | None, etree._Element, bool]:
    # TODO-v0.1-REVIEW
    """Parse a Deluge XML file with a three-stage fallback strategy.

    1. **Strict parse** via ``etree.parse()``.
    2. **Synthetic root wrapper** — wraps raw content in ``<root>...</root>``
       to handle old firmware (2.0.0–2.1.0) files with multiple root elements.
    3. **Recovering parser** — uses ``etree.XMLParser(recover=True)`` to
       handle files with duplicate attributes, unclosed tags, etc.  These
       files are readable by the Deluge hardware but not by a strict XML
       parser.  Recovered trees may have silently dropped data and MUST NOT
       be written back to disk.

    Returns ``(tree, root, recovered)`` where *tree* is ``None`` when a
    wrapper fallback was used, and *recovered* is ``True`` when the lenient
    parser was needed.
    """
    # Known firmware bug: audioClip elements have duplicate attributes
    # (isPlaying, isSoloing, etc.) — harmless, suppress the warning.
    _KNOWN_DUPE_ATTR_RE = re.compile(r"Attribute \w+ redefined")

    try:
        tree = etree.parse(xml_path)  # noqa: S320
        return tree, tree.getroot(), False
    except etree.XMLSyntaxError:
        raw = xml_path.read_bytes()
        # remove xml declaration
        raw = raw.replace(b'<?xml version="1.0" encoding="UTF-8"?>', b"", 1) 
        try:
            # wrap entire xml in new root element
            root = etree.fromstring(b"<root>" + raw + b"</root>")  # noqa: S320
            print(f"\nWarning: {xml_path} has multiple root elements")
            return None, root, False
        except etree.XMLSyntaxError as exc:
            # Lenient parse for files with duplicate attributes, unclosed tags, etc.
            parser = etree.XMLParser(recover=True)
            root = etree.fromstring(b"<root>" + raw + b"</root>", parser=parser)  # noqa: S320
            if not _KNOWN_DUPE_ATTR_RE.search(str(exc)):
                print(f"\nWarning: {xml_path} has malformed XML and was parsed with recover=true. {exc}")
            return None, root, True


def extract_sample_refs(xml_path: Path, deluge_root: Path) -> list[SampleRef]:
    # TODO-v0.1-REVIEW
    """Extract all sample references from a single Deluge XML file.

    Handles all 5 reference patterns:

    1. ``<fileName>text</fileName>`` element on ``<osc1>``/``<osc2>`` (element-style)
    2. ``<fileName>text</fileName>`` element within ``<sampleRange>`` (element-style)
    3. ``fileName="..."`` attribute on ``<osc1>``/``<osc2>`` (attribute-style)
    4. ``fileName="..."`` attribute on ``<sampleRange>`` (attribute-style)
    5. ``filePath="..."`` attribute on ``<audioClip>`` (songs only)

    The ``xml_file`` field on each :class:`SampleRef` is stored as a path
    relative to *deluge_root*.  Empty references are skipped.
    """
    _tree, root, _recovered = parse_deluge_xml(xml_path)
    xml_type = detect_xml_type(xml_path)
    xml_rel = xml_path.relative_to(deluge_root)
    refs: list[SampleRef] = []

    # Phase 1: element-style <fileName>text</fileName>
    for fn_el in root.iter("fileName"):
        text = fn_el.text
        if not text:
            continue
        parent = fn_el.getparent()
        if parent is None:
            continue
        tag = parent.tag
        if tag not in _OSC_AND_RANGE_TAGS:
            continue
        preset_name = _get_preset_name(fn_el, xml_type, xml_path)
        refs.append(
            SampleRef(
                path=text,
                xml_file=xml_rel,
                xml_type=xml_type,
                preset_name=preset_name,
                ref_type="fileName-element",
                element_tag=tag,
            )
        )

    # Phase 2: attribute-style fileName="..." on osc1/osc2/sampleRange
    for tag in _OSC_AND_RANGE_TAGS:
        for el in root.iter(tag):
            value = el.get("fileName")
            if not value:
                continue
            preset_name = _get_preset_name(el, xml_type, xml_path)
            refs.append(
                SampleRef(
                    path=value,
                    xml_file=xml_rel,
                    xml_type=xml_type,
                    preset_name=preset_name,
                    ref_type="fileName-attribute",
                    element_tag=tag,
                )
            )

    # Phase 3: attribute-style filePath="..." on audioClip
    for clip_el in root.iter("audioClip"):
        value = clip_el.get("filePath")
        if not value:
            continue
        preset_name = _get_preset_name(clip_el, xml_type, xml_path)
        refs.append(
            SampleRef(
                path=value,
                xml_file=xml_rel,
                xml_type=xml_type,
                preset_name=preset_name,
                ref_type="filePath-attribute",
                element_tag="audioClip",
            )
        )

    return refs


# ---------------------------------------------------------------------------
# Regex fallback for unextracted sample paths
# ---------------------------------------------------------------------------

_SAMPLE_PATH_RE = re.compile(r"SAMPLES/[^\"'<>\t\n\r]+\.wav", re.IGNORECASE)


def find_unextracted_refs(xml_file: Path, extracted: list[SampleRef]) -> list[str]:
    # TODO-v0.1-REVIEW
    """Find sample paths in raw XML text not captured by the structured extractor.

    Reads the raw XML and finds all SAMPLES/...wav paths via regex, then
    returns any paths not present in the *extracted* set.
    """
    raw_text = xml_file.read_text(encoding="utf-8")
    raw_paths = set(_SAMPLE_PATH_RE.findall(raw_text))
    extracted_paths = {ref.path for ref in extracted}
    return sorted(raw_paths - extracted_paths)
