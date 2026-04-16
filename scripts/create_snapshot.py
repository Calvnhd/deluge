"""Create a dated SHA-256 snapshot of all samples on the Deluge SD card."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path, PurePosixPath

from deluge_lib.cli_utils import get_deluge_root
from deluge_lib.deluge_sdk import (
    default_manifests_dir,
    find_all_wav_files,
    hash_file,
)


def snapshot(deluge_root: Path) -> Path:
    """Hash all samples and save a dated JSON snapshot.

    Args:
        deluge_root: Absolute path to the DELUGE directory.

    Returns:
        Path to the created snapshot file.
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
    if total:
        print()

    # Build snapshot data
    snapshot_date = date.today().isoformat()
    data = {
        "date": snapshot_date,
        "deluge_root": str(deluge_root),
        "hashes": dict(hashes),
    }

    # Ensure output directory exists
    manifests_dir = default_manifests_dir()
    manifests_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = manifests_dir / f"snapshot-{snapshot_date}.json"
    snapshot_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # Console output
    total = sum(len(paths) for paths in hashes.values())
    print(f"Hashed {total} files.")
    print(f"Snapshot saved to {snapshot_path}")

    # Warn about duplicate content
    for digest, paths in hashes.items():
        if len(paths) > 1:
            print(f"WARNING: duplicate content ({digest[:12]}…):")
            for p in paths:
                print(f"  {p}")

    return snapshot_path


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for creating sample snapshots."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Hash all samples and save a dated JSON snapshot.",
    )
    parser.parse_args(argv)

    deluge_root = get_deluge_root()
    snapshot(deluge_root)


if __name__ == "__main__":
    main()
