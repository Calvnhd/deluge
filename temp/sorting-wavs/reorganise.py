"""Phase 2: Reorganise WAV files into instrument category folders.

Categories:
  BASS      - Bass guitar, synth bass, 808, sub bass
  FX        - Sound effects, environmental, non-musical
  KEYS      - Keyboard, piano, organ, rhodes, kalimba, clavinet
  MULTI     - Multiple instruments, no single dominant
  PERC      - Drums, drumkit parts, cymbals, percussion
  STRINGED  - Guitar, violin, viola, cello, harp, orchestral strings
  SYNTH     - Synth leads, pads, arps, plucks
  VOCAL     - Any voice
  WIND      - Sax, trumpet, brass, flute, reed, accordion
"""

import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

CATEGORIES = ["BASS", "FX", "KEYS", "MULTI", "PERC", "STRINGED", "SYNTH", "VOCAL", "WIND"]

# ---- keyword rules --------------------------------------------------------
# Each rule is (category, compiled_regex).  Evaluated top-to-bottom; first
# match wins.  We match against the *filename only* (not the directory).

_RULES_SRC = [
    # ── compound / specific terms first ────────────────────────────────
    # Vocal keywords (high priority – a "vocal loop" is vocals even if other
    # words like "drum" also appear in the path)
    ("VOCAL",    r"\bvocal\w*\b|\bvox\b|\bvoice\b|\bchoir\b|\bchant\w*\b|\bsing\w*\b|\brap\b|\bbgv\w*\b|\bopera\b|\bscream\b"),

    # Percussion – must come before BASS so "808 Sub & Snare" → PERC when it
    # contains both percussion *and* bass keywords.
    # But "808" alone without percussion words → BASS (handled later).
    ("PERC",     r"\bdrum\b|\bdrums\b|\bkick\b|\bsnare\b|\bhi[\s_-]?hat\b|\bhihat\b|\bhh\b"
                 r"|\bclap\b|\bcymbals?\b|\bcrash\b|\bride\b|\btoms?\b"
                 r"|\btambourine\b|\bshaker\b|\brim\b|\bbongo\b|\bconga\b|\bdjembe\b"
                 r"|\bperc\b|\bpercussion\b|\bbeat\b|\bbreak\b|\btop\s*loop\b"
                 r"|\bfill\b|\bgroove\b|\bopen\s*hh\b|\bclosed\s*hh\b|\bbodhram\b"
                 r"|\bdrum\s*loop\b|\btoploop\b|\bdrumloop\b|\bdrum_loop\b|\bdrumkit\b"
                 r"|\bhats\b|\bhat\b|\b909\b|\bbrush\b|\b808s?\b"),

    # Bass – "bass guitar", "synth bass", "electric bass", plain "bass", sub
    ("BASS",     r"\bbass\b|\bsub\b|\bbassline\b"),

    # Keys
    ("KEYS",     r"\bpiano\b|\bkeys\b|\borgan\b|\brhodes\b|\bclavinet\b"
                 r"|\belectric\s*piano\b|\be[\s_-]?piano\b|\bepiano\b|\bharpsichord\b"
                 r"|\bkalimba\b|\bmarimba\b|\bvibraphone\b|\bxylophone\b|\bmallets\b"
                 r"|\bkey\s*chord\b"),

    # Wind
    ("WIND",     r"\bflute\b|\bsax\b|\bsaxophone\b|\btrumpet\b|\bbrass\b"
                 r"|\breed\b|\bhorn\b|\baccordion\b|\bclarinet\b|\boboe\b"
                 r"|\btrombone\b|\btuba\b"),

    # Stringed – guitars, orchestral strings by name
    ("STRINGED", r"\bguitar\b|\bgtr\b|\bviolin\b|\bviola\b|\bcello\b"
                 r"|\bharp\b|\bquartet\b|\bpizzicato\b|\bpizz\b"
                 r"|\bstring\b|\bstrings\b|\bstring_ensemble\b|\bstringed\b|\bukulele\b|\bbanjo\b"
                 r"|\bacoustic\b"),

    # FX
    ("FX",       r"\bfx\b|\bsfx\b|\briser\b|\bsweep\b|\bimpact\b|\btransition\b"
                 r"|\bnoise\b|\bfoley\b|\bambien\w*\b|\bsiren\b|\bglitch\b"
                 r"|\brain\b|\btraffic\b|\bexplosion\b|\btexture\b|\bvinyl\b"
                 r"|\bcrackle\b|\bdownlifter\b|\buplifter\b|\batmos\b"
                 r"|\bsound[\s_]?effect\b|\benvironment\b|\bbuzz\b"
                 r"|\bbell\b|\bchurchbell\b|\bthunder\b|\bstatic\b|\bbat\b"
                 r"|\bcomputer\b|\bsci[\s_-]?fi\b|\bdroid\b|\bmachine\b"
                 r"|\bchrome\s*hit\b"),

    # Synth – pads, leads, arps, plucks, generic synth
    ("SYNTH",    r"\bsynth\w*\b|\bpad\b|\blead\b|\barp\b|\bpluck\w*\b"
                 r"|\bdrone\b|\bmodular\b|\banalog\b|\bchords?\b"
                 r"|\bmelod\w+\b|\bswell\b"),
]

# Compile all patterns (case-insensitive)
RULES = [(cat, re.compile(pat, re.IGNORECASE)) for cat, pat in _RULES_SRC]


def classify(filename):
    """Return the best-guess category for a filename."""
    name = os.path.splitext(filename)[0]          # drop .wav
    # Normalise separators so \b works: replace _ and - with spaces
    name = re.sub(r"[_\-]", " ", name)
    # Split camelCase / PascalCase compounds (e.g. "DrumLoop" → "Drum Loop")
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    # Split uppercase runs before lowercase (e.g. "EGuitar" → "E Guitar",
    # "HHDrums" → "HH Drums")
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    # Split digit-letter boundaries (e.g. "Guitar3" → "Guitar 3")
    name = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", name)
    name = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", name)
    for cat, pat in RULES:
        if pat.search(name):
            return cat
    return "MULTI"   # fallback – unknown ⇒ MULTI


def main():
    dry_run = "--dry-run" in sys.argv

    # Load pre-move inventory so we know every file
    inv_path = os.path.join(ROOT, "inventory_before.json")
    with open(inv_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    moves = []        # list of (src_rel, dst_rel, category)
    skipped = []      # files that would collide

    for entry in inventory:
        rel = entry["relative_path"]
        src = os.path.join(ROOT, rel.replace("/", os.sep))
        filename = os.path.basename(rel)

        cat = classify(filename)

        dst_rel = f"{cat}/{filename}"
        dst = os.path.join(ROOT, cat, filename)

        # Handle name collisions: append a counter
        if os.path.exists(dst) or any(m[1] == dst_rel for m in moves):
            base, ext = os.path.splitext(filename)
            counter = 2
            while True:
                new_name = f"{base}_{counter}{ext}"
                dst_rel = f"{cat}/{new_name}"
                dst = os.path.join(ROOT, cat, new_name)
                if not os.path.exists(dst) and not any(m[1] == dst_rel for m in moves):
                    break
                counter += 1

        moves.append((rel, dst_rel, cat))

    # Print summary
    from collections import Counter
    counts = Counter(cat for _, _, cat in moves)
    print("Category distribution:")
    for cat in CATEGORIES:
        print(f"  {cat:10s}: {counts.get(cat, 0):4d}")
    print(f"  {'TOTAL':10s}: {len(moves):4d}")
    print()

    if dry_run:
        # Write plan to JSON for review
        plan_path = os.path.join(ROOT, "move_plan.json")
        plan = [{"src": s, "dst": d, "category": c} for s, d, c in moves]
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
        print(f"Dry run – wrote plan to {plan_path}")
        return

    # Execute moves
    for src_rel, dst_rel, cat in moves:
        src = os.path.join(ROOT, src_rel.replace("/", os.sep))
        dst = os.path.join(ROOT, dst_rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)

    print(f"Moved {len(moves)} files.")

    # Clean up empty source directories
    for dirpath, dirnames, filenames in os.walk(ROOT, topdown=False):
        # Skip the new category dirs and root
        rel_dir = os.path.relpath(dirpath, ROOT)
        if rel_dir == "." or rel_dir.split(os.sep)[0] in CATEGORIES:
            continue
        # Remove directory if empty (no files, no subdirs)
        if not filenames and not dirnames:
            try:
                os.rmdir(dirpath)
                print(f"  Removed empty dir: {rel_dir}")
            except OSError:
                pass


if __name__ == "__main__":
    main()
