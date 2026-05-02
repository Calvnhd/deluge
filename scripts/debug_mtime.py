"""Print mtime for every file in a folder."""
import os
from pathlib import Path

#FOLDER = Path(r"G:\SYNTHS\FACTORY")
FOLDER = Path(r"C:\source\deluge\DELUGE\SYNTHS\FACTORY")

for root, _dirs, files in os.walk(FOLDER):
    for name in sorted(files):
        p = Path(root) / name
        rel = p.relative_to(FOLDER)
        print(f"{str(rel):<70} {p.stat().st_mtime}")
