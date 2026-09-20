"""The dirt operators change how a value is spelled, never the value."""

import random
from decimal import Decimal

import pytest

from bomreuse.dirt import GENERATED_KINDS, can_apply, render_cost, render_quantity, spelling_noise, typo

SEEDS = range(200)

#: How many sub-units make a base unit, restated here on purpose: the test must not borrow
#: the conversion table of the module it checks.
TO_BASE = {"pcs": Decimal(1), "units": Decimal(1), "u": Decimal(1), "m": Decimal(1), "mm": Decimal("0.001"), "kg": Decimal(1), "g": Decimal("0.001")}


def back_to_base(quantity: str, unit: str) -> Decimal:
    return Decimal(quantity.replace(",", ".")) * TO_BASE[unit]


# --- typos ---------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", GENERATED_KINDS)
def test_a_typo_never_returns_its_input(kind: str) -> None:
    """A no-op typo would silently un-plant a defect."""
    for seed in SEEDS:
        assert typo("BGI-2031", kind, random.Random(seed)) != "BGI-2031"


def test_a_case_and_whitespace_typo_keeps_every_character_but_case_and_spaces() -> None:
    for seed in SEEDS:
        result = typo("BGI-2031", "case_and_whitespace", random.Random(seed))
        assert result.strip().upper() == "BGI-2031"


def test_a_separator_typo_only_touches_separators() -> None:
    seen = {typo("HVAC-GRILLE-12", "separator", random.Random(seed)) for seed in SEEDS}
    assert seen == {"HVACGRILLE12", "HVAC GRILLE 12", "HVAC_GRILLE_12", "HVAC-GRILLE12"}


def test_a_homoglyph_typo_swaps_lookalikes_and_keeps_the_length() -> None:
    seen = {typo("BGI-2031", "homoglyph", random.Random(seed)) for seed in SEEDS}
    assert {"BG1-2031", "BGI-2O31"} <= seen
    assert all(len(result) == len("BGI-2031") for result in seen)


def test_a_homoglyph_typo_is_refused_where_nothing_can_be_mistaken() -> None:
    assert not can_apply("SEAT-RAX", "homoglyph")
    with pytest.raises(ValueError, match="cannot change"):
        typo("SEAT-RAX", "homoglyph", random.Random(1))


def test_a_separator_typo_is_refused_without_a_separator() -> None:
    assert not can_apply("BGX2", "separator")
    with pytest.raises(ValueError, match="cannot change"):
        typo("BGX2", "separator", random.Random(1))


@pytest.mark.parametrize("kind", ["transposition", "missing_character", "anything"])
def test_out_of_reach_kinds_are_never_generated(kind: str) -> None:
    """They are literals of the spec, placed by hand (docs/ARCHITECTURE.md A2)."""
    assert not can_apply("BGI-2031", kind)
    with pytest.raises(ValueError, match="not generated"):
        typo("BGI-2031", kind, random.Random(1))


def test_the_same_seed_gives_the_same_typo() -> None:
    assert typo("BGI-2031", "homoglyph", random.Random(5)) == typo("BGI-2031", "homoglyph", random.Random(5))


# --- quantities and costs --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "base_unit"),
    [(36.0, "m"), (1.5, "m"), (0.25, "m"), (42.0, "m"), (2.5, "kg"), (0.4, "kg"), (12.0, "kg"), (24.0, "pcs"), (1.0, "pcs")],
)
def test_a_rendered_quantity_converts_back_to_exactly_the_true_value(value: float, base_unit: str) -> None:
    for seed in SEEDS:
        quantity, unit = render_quantity(value, base_unit, random.Random(seed))
        assert back_to_base(quantity, unit) == Decimal(str(value)), (quantity, unit)


def test_lengths_show_up_in_both_units_and_with_a_decimal_comma() -> None:
    rendered = {render_quantity(1.5, "m", random.Random(seed)) for seed in SEEDS}
    assert {("1,5", "m"), ("1.5", "m"), ("1500", "mm")} <= rendered


def test_a_whole_length_is_never_written_as_a_float_repr() -> None:
    rendered = {render_quantity(36.0, "m", random.Random(seed)) for seed in SEEDS}
    assert rendered <= {("36", "m"), ("36,0", "m"), ("36.0", "m"), ("36000", "mm")}
    assert ("36000", "mm") in rendered


def test_counts_use_the_three_spellings_and_stay_whole() -> None:
    rendered = {render_quantity(24.0, "pcs", random.Random(seed)) for seed in SEEDS}
    assert rendered == {("24", "pcs"), ("24", "units"), ("24", "u")}


def test_an_unknown_base_unit_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown base unit"):
        render_quantity(1.0, "litre", random.Random(1))


def test_a_cost_has_two_decimals_and_sometimes_a_comma() -> None:
    rendered = {render_cost(12.5, random.Random(seed)) for seed in SEEDS}
    assert rendered == {"12.50", "12,50"}


# --- text ----------------------------------------------------------------------------------


def test_spelling_noise_is_case_and_trailing_space_only() -> None:
    for seed in SEEDS:
        noisy = spelling_noise("Ferroval Systèmes", random.Random(seed))
        assert noisy.strip().casefold() == "ferroval systèmes".casefold()
    assert len({spelling_noise("Ferroval Systèmes", random.Random(seed)) for seed in SEEDS}) == 4
