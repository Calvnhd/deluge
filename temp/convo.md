New functions — Stubs with full signatures, type hints, and a step-by-step comment outline. Return NotImplementedError so they're obviously incomplete. This lets you validate the overall architecture and call graph before writing logic.

Dataclasses — Write them fully. They're just shape definitions — no reason to stub these.

Existing code changes — Inline comments work but are easy to lose track of. Tag them consistently, e.g. # EXTRACT-TODO: ..., so you can grep for them later and confirm none got left behind.

One addition to consider: Write the CLI entry point (extract_instruments.py) as a real skeleton that calls the stubbed functions in order. That way you can actually run the script early and watch it progress through the flow (hitting NotImplementedError at each unimplemented step). It's a useful sanity check for the overall pipeline structure.

---

Delegating to implementer...

Skill
Load your skill from agent-system/skills/feature-implementation/SKILL.md and follow its instructions.

Standards
Load and follow agent-system/standards/project.md for all project standards. Also load language standards from agent-system/standards/languages/ for Python.

Task
Scaffold the entire "Extract Instruments from Songs" feature as pseudocode stubs. This is NOT a full implementation — it's a structural skeleton covering the complete scope of the plan at docs/plans/extract-instruments-plan.md.

Read the plan thoroughly before starting. Also read:

docs/research/extract-instruments-research.md — for XML structure details and transformation recipes
temp/extraction-questions.md — for user decisions
scripts/deluge_lib/deluge_sdk.py — for existing patterns to follow
scripts/deluge_lib/cli_utils.py — for existing patterns
scripts/pyproject.toml — for existing entry points and config
scripts/extract_instruments.py — check if it exists already (it shouldn't)
What to produce
1. scripts/deluge_lib/extraction.py — Core logic module
Dataclasses: Write these FULLY (not stubs). They're just shape definitions. Include:

ExtractionResult — carries song name, preset name, instrument type (synth/kit), section ID, colour abbreviation, the assembled XML element, output filename, and metadata for the manifest
InstrumentInfo — carries the instrument element, its type, presetName, presetFolder
ClipInfo — carries the clip element, section ID, instrument reference
InstrumentClipGroup — groups an instrument with all its clips by section
VersionComparison — carries whether versions are distinct, which params differ
NormalisationConfig — which attributes to normalise and target values
Any other dataclasses the plan implies
Constants: Define these fully:

FIRMWARE_VERSION = "c1.2.1"
EARLIEST_COMPATIBLE = "4.1.0-alpha"
SYNTH_INIT_VOLUME = "0x4CCCCCA8"
KIT_INIT_VOLUME = "0x3504F334"
CENTRE_PAN = "0x00000000"
SONG_SPECIFIC_ATTRS — list of attributes to strip
ARPEGGIATOR_EXTRA_ATTRS — list of extra arp attrs to strip
SECTION_COLOURS — mapping of section ID to (colour name, 3-letter abbreviation)
DIFF_PARAM_COUNT_THRESHOLD = 3
DIFF_PARAM_PERCENT_THRESHOLD = 0.10
FAT32_UNSAFE_CHARS
Any other constants the plan implies
Functions: Write as stubs with:

Full signature (typed parameters, return type)
Docstring explaining purpose
Step-by-step comments outlining the algorithm (derived from the plan's acceptance criteria and the research transformation recipes)
raise NotImplementedError("Task X.Y: <description>") as the body
Functions needed (derived from plan tasks 1.2-4.2):

discover_songs(deluge_root: Path) -> list[tuple[Path, etree._Element]] (Task 1.2)
discover_instruments(song_tree: etree._Element) -> list[InstrumentInfo] (Task 1.3)
discover_clips(song_tree: etree._Element) -> list[ClipInfo] (Task 1.3)
match_instruments_to_clips(instruments: ..., clips: ...) -> list[InstrumentClipGroup] (Task 1.3)
select_default_clip(group: InstrumentClipGroup) -> ClipInfo (Task 1.4)
extract_synth(instrument: etree._Element, clip: etree._Element) -> etree._Element (Task 2.1 — include detailed step comments from research Section 13.5 transformation recipe)
extract_kit(instrument: etree._Element, clip: etree._Element) -> etree._Element (Task 2.2 — include detailed step comments from research Section 13.5 transformation recipe)
normalise_params(element: etree._Element, instrument_type: str, config: NormalisationConfig) -> None (Task 2.3)
generate_filename(song_name: str, preset_name: str, ...) -> str (Task 3.1)
serialise_xml(element: etree._Element, output_path: Path) -> None (Task 3.2)
compare_versions(clip_a: etree._Element, clip_b: etree._Element, instrument: etree._Element) -> VersionComparison (Task 4.1)
select_extended_clips(group: InstrumentClipGroup) -> list[ClipInfo] (Task 4.2)
Any helpers the plan implies (e.g. _strip_song_attrs, _reorder_synth_children, _reorder_kit_children, _extract_arpeggiator_from_clip, _merge_noterow_params)
2. scripts/extract_instruments.py — CLI entry point
Write this as a runnable skeleton that:

Parses args (--extended, --dry-run)
Loads DELUGE_ROOT via get_deluge_root()
Calls the stubbed functions in pipeline order
Has try/except around each phase so you can see where it fails
Includes the dry-run preview, confirmation prompt (using confirm_apply()), and trash mechanism flow
Includes the console output format from the plan
Includes manifest generation call
This should be real enough to run deluge-extract --dry-run and see it progress through the phases (hitting NotImplementedError at the first unimplemented function).

3. Existing file modifications
Add # EXTRACT-TODO: <description> comments in:

scripts/pyproject.toml — add the entry point for real (not just a comment — actually add it so the script is runnable)
scripts/deluge_lib/__init__.py — if it exists, add import for extraction module (or note that it's not needed)
Any other files that need modification per the plan
4. Test scaffolding
Create scripts/tests/test_extraction.py with:

Test function stubs (names and docstrings only, bodies as pass or pytest.skip("Not implemented"))
Covering all the test cases from Task 5.2
Guidelines
Follow existing code style from deluge_sdk.py and cli_utils.py (ruff-formatted, type-hinted, docstrings)
Use from __future__ import annotations for modern type syntax
The step comments inside function stubs should be detailed enough that someone could implement the function from the comments alone — reference specific XML element names, attribute names, and the transformation recipes
Do NOT add unnecessary abstractions — keep it simple and aligned with the plan
Do NOT modify any existing code (except pyproject.toml for the entry point)
Do NOT modify any files in DELUGE/