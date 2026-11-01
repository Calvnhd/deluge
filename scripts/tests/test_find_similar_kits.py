"""Regression tests for the read-only kit similarity scanner."""

from __future__ import annotations

from pathlib import Path

import pytest
from find_similar_kits import find_matches, load_kit, main


def write_kit(
    path: Path,
    *,
    name: str = "1",
    selected: int = 0,
    sample: str = "SAMPLES/Kick.WAV",
    volume: str = "0x40000000",
    pan: str = "0x00000000",
    pitch: str = "0",
    extra: str = "",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<kit firmwareVersion="c1.2.1">
  <soundSources>
    <sound name="{name}" mode="subtractive">
      <osc1 type="sample" fileName="{sample}"><zone startSamplePos="0" /></osc1>
      <defaultParams volume="{volume}" pan="{pan}" pitch="{pitch}" />
      {extra}
    </sound>
  </soundSources>
  <selectedDrumIndex>{selected}</selectedDrumIndex>
</kit>""",
        encoding="utf-8",
    )
    return path


def test_original_label_and_selection_difference_is_equivalent(tmp_path: Path) -> None:
    left = load_kit(write_kit(tmp_path / "Chopped-Lead.XML", name="4"))
    right = load_kit(write_kit(tmp_path / "Eeeahh.XML", name="Eeeaaahh", selected=3))
    matches = find_matches([left, right], max_differences=0)
    assert len(matches) == 1
    assert matches[0].differences == ()


def test_formatting_attribute_order_and_comments_are_ignored(tmp_path: Path) -> None:
    left_path = write_kit(tmp_path / "a.XML")
    right_path = tmp_path / "b.XML"
    right_path.write_text(
        left_path.read_text(encoding="utf-8")
        .replace('name="1" mode="subtractive"', 'mode="subtractive" name="renamed"')
        .replace("\n", "")
        .replace("<soundSources>", "<soundSources><!-- UI note -->"),
        encoding="utf-8",
    )
    assert find_matches([load_kit(left_path), load_kit(right_path)])[0].differences == ()


@pytest.mark.parametrize("threshold,expected", [(0, 0), (2, 0), (3, 1), (4, 1)])
def test_threshold_counts_all_changes_including_volume_pan_and_small_changes(
    tmp_path: Path, threshold: int, expected: int
) -> None:
    left = load_kit(write_kit(tmp_path / "a.XML"))
    right = load_kit(
        write_kit(tmp_path / "b.XML", volume="0x40000001", pan="0x00000001", pitch="1")
    )
    matches = find_matches([left, right], max_differences=threshold)
    assert len(matches) == expected
    if matches:
        assert len(matches[0].differences) == 3
        assert {diff.field.rsplit("/", 1)[-1] for diff in matches[0].differences} == {
            "@volume",
            "@pan",
            "@pitch",
        }


@pytest.mark.parametrize("sample", ["SAMPLES/Snare.WAV", "SAMPLES/kick.WAV"])
def test_different_sample_paths_are_not_near_duplicates(tmp_path: Path, sample: str) -> None:
    left = load_kit(write_kit(tmp_path / "a.XML"))
    right = load_kit(write_kit(tmp_path / "b.XML", sample=sample))
    assert find_matches([left, right], max_differences=100) == []


def test_element_style_sample_paths_are_preserved_even_when_numeric(tmp_path: Path) -> None:
    left_path = write_kit(tmp_path / "a.XML")
    right_path = write_kit(tmp_path / "b.XML")
    for path, sample in [(left_path, "123"), (right_path, "456")]:
        path.write_text(
            path.read_text(encoding="utf-8")
            .replace('fileName="SAMPLES/Kick.WAV"', "")
            .replace("<zone", f"<fileName>{sample}</fileName><zone"),
            encoding="utf-8",
        )
    assert find_matches([load_kit(left_path), load_kit(right_path)], max_differences=100) == []


@pytest.mark.parametrize(
    "extra",
    [
        '<osc2 type="sample" fileName="SAMPLES/Kick.WAV" />',
        "<unknownSetting />",
        '<defaultParams anotherParam="0" />',
    ],
)
def test_structure_and_missing_fields_are_not_guessed(tmp_path: Path, extra: str) -> None:
    left = load_kit(write_kit(tmp_path / "a.XML"))
    right = load_kit(write_kit(tmp_path / "b.XML", extra=extra))
    assert find_matches([left, right], max_differences=100) == []


def test_sound_order_is_preserved(tmp_path: Path) -> None:
    sources = [
        '<sound name="kick"><osc1 fileName="SAMPLES/Kick.WAV" /></sound>',
        '<sound name="snare"><osc1 fileName="SAMPLES/Snare.WAV" /></sound>',
    ]
    profiles = []
    for filename, sounds in [("a.XML", sources), ("b.XML", list(reversed(sources)))]:
        path = tmp_path / filename
        path.write_text(f"<kit><soundSources>{''.join(sounds)}</soundSources></kit>")
        profiles.append(load_kit(path))
    assert find_matches(profiles, max_differences=100) == []


def test_non_numerical_settings_are_not_ignored(tmp_path: Path) -> None:
    left_path = write_kit(tmp_path / "a.XML")
    right_path = write_kit(tmp_path / "b.XML")
    right_path.write_text(
        right_path.read_text(encoding="utf-8").replace('mode="subtractive"', 'mode="fm"')
    )
    assert find_matches([load_kit(left_path), load_kit(right_path)]) == []


def test_unknown_numerical_settings_are_reported(tmp_path: Path) -> None:
    left = load_kit(write_kit(tmp_path / "a.XML", extra='<newSetting amount="0" />'))
    right = load_kit(write_kit(tmp_path / "b.XML", extra='<newSetting amount="1" />'))
    matches = find_matches([left, right])
    assert len(matches) == 1
    assert matches[0].differences[0].field.endswith("newSetting[3]/@amount")


def test_reference_filter_and_deterministic_order(tmp_path: Path) -> None:
    profiles = [load_kit(write_kit(tmp_path / f"{name}.XML")) for name in ["c", "b", "a"]]
    reference = tmp_path / "b.XML"
    matches = find_matches(profiles, reference=reference)
    assert [(match.left.name, match.right.name) for match in matches] == [
        ("a.XML", "b.XML"),
        ("b.XML", "c.XML"),
    ]


def test_cli_recurses_skips_trash_and_leaves_files_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_kit(tmp_path / "a.XML")
    write_kit(tmp_path / "nested" / "b.xml", volume="0x40000001")
    write_kit(tmp_path / ".trash" / "c.XML")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    main(["--kits-dir", str(tmp_path)])
    output = capsys.readouterr().out
    assert "Scanned 2 kits: 0 equivalent pairs, 1 near-duplicate pairs" in output
    assert "0x40000000 -> 0x40000001" in output
    assert "not a guarantee of similar audio" in output
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_cli_supports_external_reference_kit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = tmp_path / "library"
    write_kit(library / "a.XML")
    reference = write_kit(tmp_path / "reference.XML")
    main([str(reference), "--kits-dir", str(library)])
    assert "Scanned 1 kits: 1 equivalent pairs" in capsys.readouterr().out


@pytest.mark.parametrize("xml", ["<kit>", "<sound />", "<!DOCTYPE kit><kit />"])
def test_invalid_or_unsupported_xml_fails_explicitly(tmp_path: Path, xml: str) -> None:
    path = tmp_path / "bad.XML"
    path.write_text(xml)
    with pytest.raises(SystemExit, match="Kit comparison failed:"):
        main(["--kits-dir", str(tmp_path)])


def test_missing_directory_fails(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="Kit comparison failed:"):
        main(["--kits-dir", str(tmp_path / "missing")])


def test_negative_threshold_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="zero or greater"):
        find_matches([], max_differences=-1)
    with pytest.raises(SystemExit) as error:
        main(["--kits-dir", str(tmp_path), "--max-differences", "-1"])
    assert error.value.code == 2


def test_no_matches_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_kit(tmp_path / "a.XML")
    main(["--kits-dir", str(tmp_path)])
    output = capsys.readouterr().out
    assert output.startswith("WORK IN PROGRESS: review comparison results before acting on them.\n")
    assert "No matches within the selected threshold" in output
