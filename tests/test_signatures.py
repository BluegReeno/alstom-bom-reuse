"""The A1 rule itself: signature, distance, budget, verdict.

The story cases live in `test_verdict_story_cases.py`; what is tested here is the mechanism
they are run through.
"""

import pytest

from bomreuse.signatures import (
    Signature,
    SignatureItem,
    Verdict,
    budget,
    compare,
    distance,
    verdict,
)
from bomreuse.spec import Thresholds

THRESHOLDS = Thresholds(max_abs_diff=3, diff_ratio=0.25)


def sig(counts: dict[str, float], units: dict[str, str] | None = None) -> Signature:
    return Signature.from_counts(counts, units)


FOUR = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


# --- the signature type ---------------------------------------------------------------------


def test_items_are_sorted_so_two_equal_signatures_compare_equal() -> None:
    assert sig({"B": 1, "A": 2}) == sig({"A": 2, "B": 1})


def test_a_component_twice_in_one_signature_is_refused() -> None:
    item = SignatureItem(component="P1", quantity=1.0, unit="pcs")
    with pytest.raises(ValueError, match="appears twice"):
        Signature(items=(item, item))


def test_from_counts_applies_the_default_unit_and_the_overrides() -> None:
    signature = sig({"CABLE": 36.0, "PLUG": 2}, {"CABLE": "m"})
    assert signature.by_component["CABLE"].unit == "m"
    assert signature.by_component["PLUG"].unit == "pcs"


# --- distance -------------------------------------------------------------------------------


def test_identical_signatures_have_an_empty_diff() -> None:
    assert distance(sig(FOUR), sig(FOUR)).is_empty()


def test_added_and_removed_are_read_left_to_right() -> None:
    diff = distance(sig({"A": 1, "B": 1, "C": 1, "D": 1}), sig({"A": 1, "B": 1, "C": 1, "E": 1}))
    assert [item.component for item in diff.added] == ["E"]
    assert [item.component for item in diff.removed] == ["D"]
    assert diff.n_parts_diff == 2
    assert diff.n_qty_diff == 0


def test_a_different_quantity_is_a_quantity_difference_not_a_part_difference() -> None:
    diff = distance(sig(FOUR), sig({**FOUR, "P2": 5}))
    assert diff.n_parts_diff == 0
    assert [change.component for change in diff.quantity_changed] == ["P2"]
    assert (diff.quantity_changed[0].left.quantity, diff.quantity_changed[0].right.quantity) == (2.0, 5.0)


def test_a_residual_unit_difference_counts_as_a_quantity_difference() -> None:
    """After normalization units are SI, so a difference left means a different amount."""
    diff = distance(sig({**FOUR, "CABLE": 1.5}, {"CABLE": "m"}), sig({**FOUR, "CABLE": 1.5}, {"CABLE": "kg"}))
    assert diff.n_qty_diff == 1
    assert diff.n_parts_diff == 0


def test_quantities_are_compared_with_a_tolerance() -> None:
    """Normalized quantities are floats; an exact == would depend on the arithmetic order."""
    assert distance(sig({**FOUR, "CABLE": 0.1 + 0.2}), sig({**FOUR, "CABLE": 0.3})).is_empty()


def test_the_diff_is_mirrored_when_the_sides_are_swapped() -> None:
    left, right = sig({"A": 1, "B": 1, "C": 1, "D": 1}), sig({"A": 1, "B": 1, "C": 1, "E": 1})
    assert distance(left, right).added == distance(right, left).removed


# --- budget ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("size", "expected"),
    [(4, 1), (7, 2), (8, 2), (9, 3), (12, 3), (40, 3)],
)
def test_budget_is_the_ratio_until_the_absolute_clamp_bites(size: int, expected: int) -> None:
    signature = sig({f"P{i}": 1 for i in range(size)})
    assert budget(signature, signature, THRESHOLDS) == expected


def test_budget_follows_the_smaller_side() -> None:
    small, large = sig({f"P{i}": 1 for i in range(4)}), sig({f"P{i}": 1 for i in range(40)})
    assert budget(small, large, THRESHOLDS) == 1


def test_the_minimum_subassembly_size_keeps_the_budget_out_of_its_degenerate_range() -> None:
    """At the declared minimum of 4 the budget is 1, not "anything goes"."""
    four, five = sig(FOUR), sig({**FOUR, "P5": 1})
    assert budget(four, five, THRESHOLDS) == 1
    assert verdict(four, sig({**FOUR, "P5": 1, "P6": 1}), THRESHOLDS) is Verdict.SPECIFIC


# --- verdict ---------------------------------------------------------------------------------


def test_identical_requires_both_counters_at_zero() -> None:
    assert verdict(sig(FOUR), sig(FOUR), THRESHOLDS) is Verdict.IDENTICAL
    assert verdict(sig(FOUR), sig({**FOUR, "P2": 5}), THRESHOLDS) is Verdict.REUSABLE


def test_both_counters_are_judged_against_the_same_budget() -> None:
    """Three quantity differences are no more acceptable than three missing parts."""
    twelve = {f"P{i}": 1 for i in range(12)}
    three_qty = {**twelve, "P0": 9, "P1": 9, "P2": 9}
    four_qty = {**three_qty, "P3": 9}
    assert verdict(sig(twelve), sig(three_qty), THRESHOLDS) is Verdict.REUSABLE
    assert verdict(sig(twelve), sig(four_qty), THRESHOLDS) is Verdict.SPECIFIC

    three_parts = {f"P{i}": 1 for i in range(12) if i > 2}
    four_parts = {f"P{i}": 1 for i in range(12) if i > 3}
    assert verdict(sig(twelve), sig(three_parts), THRESHOLDS) is Verdict.REUSABLE
    assert verdict(sig(twelve), sig(four_parts), THRESHOLDS) is Verdict.SPECIFIC


def test_the_absolute_clamp_is_a_real_ceiling_on_a_large_subassembly() -> None:
    """Without max_abs_diff a 40-component sub-assembly would tolerate 10 differences."""
    forty = {f"P{i}": 1 for i in range(40)}
    assert budget(sig(forty), sig(forty), THRESHOLDS) == 3
    assert verdict(sig(forty), sig({f"P{i}": 1 for i in range(40) if i > 3}), THRESHOLDS) is Verdict.SPECIFIC


@pytest.mark.parametrize(
    "right",
    [FOUR, {**FOUR, "P5": 1}, {**FOUR, "P2": 9}, {"P1": 1, "P2": 2, "P9": 3, "P8": 4}],
)
def test_the_verdict_does_not_depend_on_which_side_is_given_first(right: dict[str, float]) -> None:
    assert verdict(sig(FOUR), sig(right), THRESHOLDS) is verdict(sig(right), sig(FOUR), THRESHOLDS)


def test_compare_hands_back_the_budget_that_decided_it() -> None:
    result = compare(sig(FOUR), sig({**FOUR, "P5": 1}), THRESHOLDS)
    assert (result.verdict, result.budget) == (Verdict.REUSABLE, 1)
    assert [item.component for item in result.diff.added] == ["P5"]
