"""Phase 1: Generate a JSON inventory of all WAV files with SHA256 hashes."""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_inventory(root):
    entries = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if not fn.lower().endswith(".wav"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            entries.append({
                "relative_path": rel.replace("\\", "/"),
                "sha256": sha256_file(full),
            })
    entries.sort(key=lambda e: e["relative_path"])
    return entries


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "inventory_before.json"
    out_path = os.path.join(ROOT, out)
    inv = build_inventory(ROOT)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(inv, f, indent=2)
    print(f"Wrote {len(inv)} entries to {out}")


if __name__ == "__main__":
    main()
