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

import sys
from pathlib import Path
from datetime import datetime

# Import shared library
from deluge_sdk import (
    # Data structures
    KitInfo, SynthInfo, SongInfo, SampleInfo, ManifestData,
    # Parsing functions
    parse_deluge_xml, get_actual_root,
    parse_kit, parse_synth, parse_song,
    extract_audio_clip_samples, extract_embedded_instrument_samples,
    # Utilities
    format_size, format_date,
)


# =============================================================================
# Data Collection
# =============================================================================

def collect_manifest_data(deluge_path: Path) -> ManifestData:
    """
    Scan DELUGE folder and collect all manifest data.
    
    This function walks through the DELUGE folder structure, parsing all
    XML files and collecting sample references. It tracks:
    - All kits, synths, and songs
    - Sample usage (which instruments use which samples)
    - Broken references (samples that don't exist)
    - Firmware versions across all files
    
    Args:
        deluge_path: Path to the DELUGE folder
        
    Returns:
        ManifestData containing all collected information
    """
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
            else:
                print(f"  ⚠ Failed to parse {xml_file.name}", file=sys.stderr)
    
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
            else:
                print(f"  ⚠ Failed to parse {xml_file.name}", file=sys.stderr)
    
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
            else:
                print(f"  ⚠ Failed to parse {xml_file.name}", file=sys.stderr)
    
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
