"""The contract parses, and it says what the architecture requires it to say."""

from pathlib import Path

import pytest

from bomreuse.spec import DEFAULT_SPEC_PATH, VERDICTS, SpecError, load_spec

MINIMAL_SPEC = """
version = "1"

[thresholds]
max_abs_diff = 3
diff_ratio = 0.25

[dataset]
min_subassembly_size = 4
default_unit = "pcs"

[[story_cases]]
id = "c1"
sub_assembly = "S"
left_variant = "A"
right_variant = "B"
expected_verdict = "identical"
source = "test"
[story_cases.left]
"P1" = 1
"P2" = 1
"P3" = 1
"P4" = 1
[story_cases.right]
"P1" = 1
"P2" = 1
"P3" = 1
"P4" = 1

[[typo_families]]
id = "t1"
kind = "transposition"
canonical = "X-1234"
variants = ["X-1243"]
within_rules_reach = false
note = "n"

[[must_not_merge]]
id = "m1"
left_reference = "X-I"
right_reference = "X-1"
left_true_component = "TRUE-1"
right_true_component = "TRUE-2"
collapsing_rule = "homoglyph_i_one"
reason = "r"

[[must_not_merge]]
id = "m2"
left_reference = "Y-O"
right_reference = "Y-0"
left_true_component = "TRUE-3"
right_true_component = "TRUE-4"
collapsing_rule = "homoglyph_o_zero"
reason = "r"
"""


def write_spec(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "spec.toml"
    path.write_text(body, encoding="utf-8")
    return path


# --- the committed contract ----------------------------------------------------------------


def test_the_committed_spec_loads() -> None:
    spec = load_spec()
    assert spec.version == "1"


def test_thresholds_are_the_two_declared_numbers() -> None:
    thresholds = load_spec().thresholds
    assert thresholds.max_abs_diff == 3
    assert thresholds.diff_ratio == 0.25


def test_minimum_subassembly_size_is_declared_and_readable() -> None:
    """The degenerate-budget fix belongs to the data; #2's generator honours this number."""
    assert load_spec().dataset.min_subassembly_size == 4


def test_story_cases_cover_the_three_verdicts() -> None:
    expected = {case.expected_verdict for case in load_spec().story_cases}
    assert expected == VERDICTS


def test_story_case_count_is_within_the_issue_range() -> None:
    assert 5 <= len(load_spec().story_cases) <= 10


def test_every_story_case_honours_the_minimum_size() -> None:
    spec = load_spec()
    minimum = spec.dataset.min_subassembly_size
    for case in spec.story_cases:
        assert len(case.left) >= minimum, case.id
        assert len(case.right) >= minimum, case.id


def test_some_typo_families_are_out_of_the_rules_reach() -> None:
    """Without them, resolution recall is 1 by construction and measures nothing."""
    out_of_reach = [f for f in load_spec().typo_families if not f.within_rules_reach]
    assert {f.kind for f in out_of_reach} >= {"transposition", "missing_character"}


def test_must_not_merge_pairs_are_declared() -> None:
    """Without them, resolution precision is 1 by construction and measures nothing."""
    pairs = load_spec().must_not_merge
    assert len(pairs) >= 2
    for pair in pairs:
        assert pair.left_true_component != pair.right_true_component


def test_story_case_lookup_by_id() -> None:
    spec = load_spec()
    assert spec.story_case("bike_module_two_fewer_hooks").sub_assembly == "Bike module"
    with pytest.raises(SpecError, match="no story case"):
        spec.story_case("no_such_case")


def test_default_spec_path_points_at_the_committed_file() -> None:
    assert DEFAULT_SPEC_PATH.name == "dataset_spec.toml"
    assert DEFAULT_SPEC_PATH.is_file()


# --- strictness ----------------------------------------------------------------------------


def test_minimal_spec_is_accepted(tmp_path: Path) -> None:
    spec = load_spec(write_spec(tmp_path, MINIMAL_SPEC))
    assert len(spec.story_cases) == 1


def test_a_missing_file_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="not found"):
        load_spec(tmp_path / "absent.toml")


def test_a_missing_key_fails_loudly(tmp_path: Path) -> None:
    body = MINIMAL_SPEC.replace("max_abs_diff = 3\n", "")
    with pytest.raises(SpecError, match=r"\[thresholds\] is missing \['max_abs_diff'\]"):
        load_spec(write_spec(tmp_path, body))


def test_an_unknown_key_fails_loudly(tmp_path: Path) -> None:
    body = MINIMAL_SPEC.replace("diff_ratio = 0.25\n", "diff_ratio = 0.25\ndiff_ration = 0.30\n")
    with pytest.raises(SpecError, match="unknown keys"):
        load_spec(write_spec(tmp_path, body))


def test_an_unknown_verdict_fails_loudly(tmp_path: Path) -> None:
    body = MINIMAL_SPEC.replace('expected_verdict = "identical"', 'expected_verdict = "reused"')
    with pytest.raises(SpecError, match="is not one of"):
        load_spec(write_spec(tmp_path, body))


def test_a_story_case_below_the_minimum_size_fails_loudly(tmp_path: Path) -> None:
    body = MINIMAL_SPEC.replace('"P4" = 1\n[story_cases.right]', "[story_cases.right]")
    with pytest.raises(SpecError, match="below dataset.min_subassembly_size"):
        load_spec(write_spec(tmp_path, body))


def test_a_spec_with_only_catchable_typos_fails_loudly(tmp_path: Path) -> None:
    body = MINIMAL_SPEC.replace("within_rules_reach = false", "within_rules_reach = true")
    with pytest.raises(SpecError, match="out of reach of the folding rules"):
        load_spec(write_spec(tmp_path, body))


def test_a_spec_with_a_single_must_not_merge_pair_fails_loudly(tmp_path: Path) -> None:
    body = MINIMAL_SPEC[: MINIMAL_SPEC.index('[[must_not_merge]]\nid = "m2"')]
    with pytest.raises(SpecError, match="fewer than two must-not-merge pairs"):
        load_spec(write_spec(tmp_path, body))


def test_a_duplicate_story_case_id_fails_loudly(tmp_path: Path) -> None:
    body = MINIMAL_SPEC + MINIMAL_SPEC[MINIMAL_SPEC.index("[[story_cases]]") : MINIMAL_SPEC.index("[[typo_families]]")]
    with pytest.raises(SpecError, match="duplicate story case id"):
        load_spec(write_spec(tmp_path, body))


def test_a_negative_quantity_fails_loudly(tmp_path: Path) -> None:
    body = MINIMAL_SPEC.replace('"P1" = 1\n"P2" = 1\n"P3" = 1\n"P4" = 1\n[story_cases.right]', '"P1" = -1\n"P2" = 1\n"P3" = 1\n"P4" = 1\n[story_cases.right]')
    with pytest.raises(SpecError, match="must be positive"):
        load_spec(write_spec(tmp_path, body))


def test_a_unit_for_an_absent_component_fails_loudly(tmp_path: Path) -> None:
    body = MINIMAL_SPEC.replace(
        "[[typo_families]]",
        '[story_cases.units]\n"P9" = "m"\n\n[[typo_families]]',
        1,
    )
    with pytest.raises(SpecError, match="units for components it does not contain"):
        load_spec(write_spec(tmp_path, body))


def test_invalid_toml_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="not valid TOML"):
        load_spec(write_spec(tmp_path, "version = "))
