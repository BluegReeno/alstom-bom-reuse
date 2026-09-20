"""Normalization: what the rules fold together, what they leave apart, and what they refuse to read.

These tests prove the code does what it says. Whether the folding is *good* — how many true
duplicates it finds, how many false merges it causes — is `evaluate`'s measurement (#5), and no
test here opens the ground truth.
"""

import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from bomreuse.normalize import normalize_quantity, parse_date, parse_int, parse_number, parse_unit, reference_key, text_key
from bomreuse.spec import DatasetSpec, load_spec

SPEC: DatasetSpec = load_spec()
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "bomreuse"

WITHIN_REACH = [(family.canonical, spelling) for family in SPEC.typo_families if family.within_rules_reach for spelling in family.variants]
OUT_OF_REACH = [(family.canonical, spelling) for family in SPEC.typo_families if not family.within_rules_reach for spelling in family.variants]


# --- the reference key -------------------------------------------------------------------------


@pytest.mark.parametrize("spelling", ["BGI-2031", "BG1-2031", "bgi 2031 ", "BGI_2031", "BGI-2O3I", " Bgi-2031", "BGI2031", "b.g.i/2031", " BGI\t2031"])
def test_the_spellings_of_one_reference_share_one_key(spelling: str) -> None:
    assert reference_key(spelling) == reference_key("BGI-2031") == "BG12031"


@pytest.mark.parametrize("spelling", ["HVAC-GRILLE-l2", "HVAC-GRlLLE-12", "hvac-grille-12", "Hvac-Grille-I2"])
def test_a_lowercase_l_an_uppercase_i_and_a_one_are_one_character(spelling: str) -> None:
    assert reference_key(spelling) == reference_key("HVAC-GRILLE-12")


def test_the_key_is_case_insensitive_because_it_uppercases_before_it_folds() -> None:
    """DECISIONS.md 27: folding a lowercase `l` first would leave `brk-ctrl-valve` on a key of its own."""
    assert reference_key("brk-ctrl-valve") == reference_key("BRK-CTRL-VALVE") == "BRKCTR1VA1VE"


@pytest.mark.parametrize("canonical, spelling", WITHIN_REACH)
def test_every_typo_family_the_spec_declares_within_reach_collapses(canonical: str, spelling: str) -> None:
    assert reference_key(spelling) == reference_key(canonical)


@pytest.mark.parametrize("canonical, spelling", OUT_OF_REACH)
def test_every_typo_family_the_spec_declares_out_of_reach_stays_out_of_reach(canonical: str, spelling: str) -> None:
    """A transposition or a missing character is not undone: that would take a string distance (A2)."""
    assert reference_key(spelling) != reference_key(canonical)


def test_the_spec_plants_both_kinds_so_the_two_tests_above_are_not_vacuous() -> None:
    assert WITHIN_REACH and OUT_OF_REACH
    assert ("BGI-2031", "BGI-2013") in OUT_OF_REACH and ("SEAT-FIX-KIT-4471", "SEAT-FIX-KIT-447") in OUT_OF_REACH


@pytest.mark.parametrize("pair", SPEC.must_not_merge, ids=lambda pair: pair.id)
def test_the_must_not_merge_pairs_share_a_key_and_that_is_the_accepted_cost(pair) -> None:  # type: ignore[no-untyped-def]
    """Not a wish, a recorded trade-off (DECISIONS.md 27): the key cannot tell these products apart.

    Splitting them back is resolution's `reject` (#4), on their designations; whether it works is
    read in resolution precision (#5). If this test ever fails, the rule changed and the decision
    must be revisited — not the test.
    """
    assert pair.left_reference != pair.right_reference
    assert reference_key(pair.left_reference) == reference_key(pair.right_reference)


@pytest.mark.parametrize("left, right", [("SEAT-5", "SEAT-S"), ("BRK-8", "BRK-B"), ("Z-200", "2-200"), ("AB-12", "AB-21"), ("AB-12", "AB-120")])
def test_nothing_else_is_folded(left: str, right: str) -> None:
    assert reference_key(left) != reference_key(right)


@pytest.mark.parametrize("raw, key", [("0031", "0031"), ("00-31", "0031"), ("SA-0107", "SA0107"), ("SA-O107", "SA0107"), ("---", ""), ("", ""), ("   ", "")])
def test_a_leading_zero_stays_and_a_reference_of_separators_has_an_empty_key(raw: str, key: str) -> None:
    assert reference_key(raw) == key


def test_no_string_distance_anywhere_in_the_source() -> None:
    """docs/ARCHITECTURE.md A2, checked where it would be broken first."""
    for path in sorted(SRC.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("difflib", "rapidfuzz", "Levenshtein", "jellyfish", "SequenceMatcher"):
            assert f"import {forbidden}" not in source and f"from {forbidden}" not in source, f"{path.name} uses {forbidden}"


# --- text ------------------------------------------------------------------------------------


def test_a_name_typed_by_someone_else_is_the_same_name() -> None:
    assert text_key("Artois Polymères ") == text_key("ARTOIS  POLYMÈRES") == text_key("\tartois polymères") == "artois polymères"


def test_composed_and_decomposed_accents_are_one_name() -> None:
    composed, decomposed = unicodedata.normalize("NFC", "Polymères"), unicodedata.normalize("NFD", "Polymères")
    assert composed != decomposed
    assert text_key(composed) == text_key(decomposed)


def test_an_accent_is_part_of_the_name() -> None:
    assert text_key("Polymères") != text_key("Polymeres")


# --- numbers ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [("1,5", "1.5"), ("1.5", "1.5"), ("1.50", "1.5"), ("01,5", "1.5"), ("36", "36"), ("36,0", "36"), (" 12 ", "12"), ("48200,00", "48200"), ("17650.00", "17650"), ("0", "0"), ("0,001", "0.001")],
)
def test_a_number_is_read_with_a_comma_or_a_dot(raw: str, expected: str) -> None:
    assert parse_number(raw) == (Decimal(expected), None)


@pytest.mark.parametrize(
    "raw, reason",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("1.234,56", "ambiguous separators"),
        ("1,234.56", "ambiguous separators"),
        ("abc", "not a number"),
        ("-3", "not a number"),
        ("+3", "not a number"),
        ("1e3", "not a number"),
        ("1 234", "not a number"),
        ("1,2,3", "not a number"),
        ("1.", "not a number"),
        (",5", "not a number"),
        ("12 m", "not a number"),
        ("１２", "not a number"),  # full-width digits
        ("NaN", "not a number"),
        ("inf", "not a number"),
    ],
)
def test_what_is_not_plainly_a_number_is_not_read(raw: str, reason: str) -> None:
    assert parse_number(raw) == (None, reason)


@pytest.mark.parametrize("raw, expected", [("48", (48, None)), (" 0 ", (0, None)), ("048", (48, None)), ("", (None, "empty")), ("48.0", (None, "not an integer")), ("-1", (None, "not an integer")), ("many", (None, "not an integer"))])
def test_an_integer(raw: str, expected: tuple[int | None, str | None]) -> None:
    assert parse_int(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2019-03-14", (date(2019, 3, 14), None)),
        (" 2019-03-14 ", (date(2019, 3, 14), None)),
        ("", (None, "empty")),
        ("14/03/2019", (None, "not an ISO date")),
        ("20190314", (None, "not an ISO date")),
        ("2019-02-30", (None, "not an ISO date")),
        ("2019-03-14T10:00", (None, "not an ISO date")),
    ],
)
def test_a_date(raw: str, expected: tuple[date | None, str | None]) -> None:
    assert parse_date(raw) == expected


# --- units and quantities ----------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["pcs", "units", "unit", "u", " U ", "PCS", "Units"])
def test_every_spelling_of_a_count_is_pcs(raw: str) -> None:
    assert parse_unit(raw) == (("pcs", Decimal(1)), None)


@pytest.mark.parametrize("raw, reason", [("", "empty"), (" ", "empty"), ("cm", "unknown unit"), ("km", "unknown unit"), ("m2", "unknown unit"), ("kgs", "unknown unit"), ("each", "unknown unit")])
def test_an_unknown_unit_is_not_guessed(raw: str, reason: str) -> None:
    assert parse_unit(raw) == (None, reason)


@pytest.mark.parametrize(
    "raw_value, raw_unit, value, unit",
    [("1,5", "m", 1.5, "m"), ("1500", "mm", 1.5, "m"), ("1500", "g", 1.5, "kg"), ("2,75", "kg", 2.75, "kg"), ("4", "units", 4.0, "pcs"), ("2", " U ", 2.0, "pcs"), ("9600", "MM", 9.6, "m"), ("1", "mm", 0.001, "m")],
)
def test_an_amount_is_brought_to_its_si_unit_and_keeps_its_raw_spelling(raw_value: str, raw_unit: str, value: float, unit: str) -> None:
    quantity, issues = normalize_quantity(raw_value, raw_unit)
    assert (quantity.value, quantity.unit) == (value, unit)
    assert isinstance(quantity.value, float)
    assert (quantity.raw_value, quantity.raw_unit) == (raw_value, raw_unit)
    assert issues == []


def test_three_spellings_of_one_length_are_the_same_float_exactly() -> None:
    """`==`, not `isclose`: the arithmetic is done in Decimal so that the artifact is stable."""
    values = {normalize_quantity(*spelling)[0].value for spelling in [("36000", "mm"), ("36", "m"), ("36,0", "m"), ("36.0", "m")]}
    assert values == {36.0}
    assert normalize_quantity("9600", "mm")[0].value == normalize_quantity("9,6", "m")[0].value
    assert normalize_quantity("100", "g")[0].value == normalize_quantity("0,1", "kg")[0].value == 0.1


@pytest.mark.parametrize(
    "raw_value, raw_unit, expected_issues",
    [
        ("abc", "pcs", [("quantity", "abc", "not a number")]),
        ("", "pcs", [("quantity", "", "empty")]),
        ("1.234,56", "m", [("quantity", "1.234,56", "ambiguous separators")]),
        ("-3", "pcs", [("quantity", "-3", "not a number")]),
        ("0", "pcs", [("quantity", "0", "not positive")]),
        ("0,0", "m", [("quantity", "0,0", "not positive")]),
        ("1e3", "pcs", [("quantity", "1e3", "not a number")]),
        ("12", "cm", [("unit", "cm", "unknown unit")]),
        ("12", "", [("unit", "", "empty")]),
        ("abc", "cm", [("quantity", "abc", "not a number"), ("unit", "cm", "unknown unit")]),
    ],
)
def test_an_unreadable_half_makes_the_whole_amount_unreadable(raw_value: str, raw_unit: str, expected_issues: list[tuple[str, str, str]]) -> None:
    quantity, issues = normalize_quantity(raw_value, raw_unit)
    assert quantity.value is None and quantity.unit is None, "a number without its unit is not an amount"
    assert (quantity.raw_value, quantity.raw_unit) == (raw_value, raw_unit)
    assert issues == expected_issues
