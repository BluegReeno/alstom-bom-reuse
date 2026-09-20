"""Spike S1: the verdict rule against the hand-written cases of CONTEXT.md's worked example.

The rule is run against the story, not the other way round. When the two disagreed, the part
counts in `data/dataset_spec.toml` changed — never the thresholds (DECISIONS.md 17). Two cases
forced a change and carry the reason as a comment in the spec: the seating module, whose
armrests and cushions belong to the seat reference rather than to the module, and the bike
module, whose fixing kit follows the rail rather than the hook.
"""

import pytest

from bomreuse.signatures import Signature, Verdict, compare
from bomreuse.spec import DatasetSpec, StoryCase, load_spec

SPEC: DatasetSpec = load_spec()
CASES: tuple[StoryCase, ...] = SPEC.story_cases


def signatures(case: StoryCase) -> tuple[Signature, Signature]:
    default_unit = SPEC.dataset.default_unit
    return (
        Signature.from_counts(case.left, case.units, default_unit),
        Signature.from_counts(case.right, case.units, default_unit),
    )


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_the_rule_agrees_with_the_story(case: StoryCase) -> None:
    left, right = signatures(case)
    result = compare(left, right, SPEC.thresholds)
    assert result.verdict == case.expected_verdict, (
        f"{case.id} ({case.sub_assembly}, {case.left_variant} vs {case.right_variant}): "
        f"the story says {case.expected_verdict}, the rule says {result.verdict} "
        f"(n_parts_diff={result.diff.n_parts_diff}, n_qty_diff={result.diff.n_qty_diff}, "
        f"budget={result.budget}). Per DECISIONS.md 17, the fix is the part counts in "
        f"data/dataset_spec.toml, never the thresholds."
    )


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_the_story_reads_the_same_from_either_side(case: StoryCase) -> None:
    left, right = signatures(case)
    assert compare(left, right, SPEC.thresholds).verdict == compare(right, left, SPEC.thresholds).verdict


# --- the diff carried as evidence, case by case ----------------------------------------------


def test_the_seating_module_diff_names_the_tip_up_seat_and_the_seat_count() -> None:
    """CONTEXT.md: "same seat, different count" — the evidence must say exactly that."""
    left, right = signatures(SPEC.story_case("seating_module_tipup"))
    diff = compare(left, right, SPEC.thresholds).diff
    assert [item.component for item in diff.added] == ["SEAT-TIPUP"]
    assert diff.removed == ()
    assert {change.component for change in diff.quantity_changed} == {"SEAT-FIX-DBL", "SEAT-FIX-KIT"}
    seats = next(change for change in diff.quantity_changed if change.component == "SEAT-FIX-DBL")
    assert (seats.left.quantity, seats.right.quantity) == (24.0, 18.0)


def test_the_bike_module_diff_is_two_fewer_hooks_and_nothing_else() -> None:
    left, right = signatures(SPEC.story_case("bike_module_two_fewer_hooks"))
    diff = compare(left, right, SPEC.thresholds).diff
    assert diff.n_parts_diff == 0
    hooks = next(change for change in diff.quantity_changed if change.component == "BIKE-HOOK")
    assert (hooks.left.quantity, hooks.right.quantity) == (8.0, 6.0)


def test_the_new_anchorage_is_specific_because_of_the_parts_not_the_quantities() -> None:
    """The anchorage is the one sub-assembly the story calls new; it must fail on parts."""
    left, right = signatures(SPEC.story_case("floor_wall_anchorage_new"))
    result = compare(left, right, SPEC.thresholds)
    assert result.verdict is Verdict.SPECIFIC
    assert result.diff.n_parts_diff > result.budget
    assert {item.component for item in result.diff.added} >= {"ANCH-BIKE-PLATE", "ANCH-WALL-BRACKET"}


def test_an_identical_case_carries_no_diff_at_all() -> None:
    left, right = signatures(SPEC.story_case("carbody_shell_identical"))
    assert compare(left, right, SPEC.thresholds).diff.is_empty()


def test_the_door_set_is_reusable_only_because_of_the_absolute_clamp() -> None:
    """16 components would allow 4 differences on the ratio alone; max_abs_diff caps it at 3."""
    left, right = signatures(SPEC.story_case("passenger_door_set_reusable"))
    result = compare(left, right, SPEC.thresholds)
    assert result.budget == SPEC.thresholds.max_abs_diff
    assert result.diff.n_parts_diff == 3
