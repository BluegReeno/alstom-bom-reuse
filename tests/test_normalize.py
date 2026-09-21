"""Normalization: what the rules fold together, what they leave apart, and what they refuse to read.

These tests prove the code does what it says. Whether the folding is *good* — how many true
duplicates it finds, how many false merges it causes — is `evaluate`'s measurement (#5), and no
test here opens the ground truth.
"""

import inspect
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from bomreuse.ingest import read_raw
from bomreuse.model import NormalizationIssue, NormalizedDataset, Quantity, RawBomRow, RawDataset, RawNoteRow, RawVariantRow
from bomreuse.normalize import normalize, normalize_quantity, parse_date, parse_int, parse_number, parse_unit, reference_key, text_key
from bomreuse.spec import DatasetSpec, MustNotMergePair, load_spec

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
def test_the_must_not_merge_pairs_share_a_key_and_that_is_the_accepted_cost(pair: MustNotMergePair) -> None:
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


def test_composed_and_decomposed_accents_are_one_reference_and_the_accent_stays() -> None:
    """Without NFC the combining mark of a decomposed `é` is not alphanumeric and is dropped: `E`, against `É`."""
    composed, decomposed = unicodedata.normalize("NFC", "CÂBLE-12"), unicodedata.normalize("NFD", "CÂBLE-12")
    assert composed != decomposed
    assert reference_key(composed) == reference_key(decomposed) == "CÂB1E12"
    assert reference_key("CÂBLE-12") != reference_key("CABLE-12")


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
        # A float would hold these as `inf`, and `Infinity` is not JSON.
        pytest.param("9" * 400, "out of range", id="400 digits"),
        pytest.param("9" * 400 + ",5", "out of range", id="400 digits and a decimal"),
    ],
)
def test_what_is_not_plainly_a_number_is_not_read(raw: str, reason: str) -> None:
    assert parse_number(raw) == (None, reason)


@pytest.mark.parametrize("raw, expected", [("48", (48, None)), (" 0 ", (0, None)), ("048", (48, None)), ("", (None, "empty")), ("48.0", (None, "not an integer")), ("-1", (None, "not an integer")), ("many", (None, "not an integer"))])
def test_an_integer(raw: str, expected: tuple[int | None, str | None]) -> None:
    assert parse_int(raw) == expected


def test_an_integer_longer_than_python_converts_is_not_read() -> None:
    """`int()` refuses a digit string over 4300 characters with a `ValueError`: an issue, not a crash."""
    assert parse_int("9" * 5000) == (None, "out of range")


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


@pytest.mark.parametrize(
    "raw_value, raw_unit",
    [
        pytest.param("0," + "0" * 400 + "1", "pcs", id="smaller than any float"),
        pytest.param("0," + "0" * 322 + "1", "mm", id="a float until it is converted to metres"),
    ],
)
def test_a_quantity_too_small_for_a_float_is_counted_rather_than_read_as_zero(raw_value: str, raw_unit: str) -> None:
    """`not positive` is checked on the `Decimal`; the artifact holds the float, and `0.0` is not an amount."""
    quantity, issues = normalize_quantity(raw_value, raw_unit)
    assert quantity.value is None and quantity.unit is None
    assert issues == [("quantity", raw_value, "out of range")]


# --- rows into entities ------------------------------------------------------------------------

COMMITTED_RAW = ROOT / "data" / "raw"


@pytest.fixture(scope="module")
def raw() -> RawDataset:
    return read_raw(COMMITTED_RAW)


@pytest.fixture(scope="module")
def dataset(raw: RawDataset) -> NormalizedDataset:
    return normalize(raw)


def variant_row(variant_id: str = "A", **cells: str) -> RawVariantRow:
    defaults = {"name": "Standard car", "design_date": "2019-03-14", "region": "Hauts-de-France", "seats": "48", "bike_spaces": "0", "traction": "electric"}
    return RawVariantRow(row_number=1, variant_id=variant_id, **{**defaults, **cells})


def bom_row(row_number: int = 1, **cells: str) -> RawBomRow:
    defaults = {
        "line_id": f"L{row_number}",
        "variant_id": "A",
        "sub_assembly_ref": "SA-0101",
        "sub_assembly_designation": "Carbody shell",
        "component_ref": "BGI-2031",
        "designation": "Bolt set M8",
        "quantity": "4",
        "unit": "pcs",
        "supplier": "Artois Polymères",
        "unit_cost_eur": "12,50",
    }
    return RawBomRow(row_number=row_number, **{**defaults, **cells})


def a_raw_dataset(*bom: RawBomRow, variants: tuple[RawVariantRow, ...] | None = None, notes: tuple[RawNoteRow, ...] = ()) -> RawDataset:
    return RawDataset(variants=variants if variants is not None else (variant_row("A"), variant_row("B", design_date="2021-06-02")), bom=bom, notes=notes)


def test_every_row_of_the_committed_dataset_becomes_an_entity(dataset: NormalizedDataset) -> None:
    assert (len(dataset.lines), len(dataset.notes), len(dataset.variants)) == (696, 40, 5)
    assert len(dataset.sub_assemblies) == 72


def test_the_committed_dataset_has_nothing_unreadable(dataset: NormalizedDataset) -> None:
    """Its dirt is all of the kinds this module reads. An issue here means the generator and the reader drifted apart."""
    assert dataset.issues == ()
    assert all(line.quantity.value is not None and line.unit_cost.normalized is not None for line in dataset.lines)


def test_variants_come_in_design_order_so_the_newest_is_last(dataset: NormalizedDataset) -> None:
    dates = [variant.design_date.normalized for variant in dataset.variants if variant.design_date.normalized is not None]
    assert len(dates) == len(dataset.variants), "every committed variant has a readable date"
    assert dates == sorted(dates)
    assert dataset.variants[-1].id == "C", "the file lists C last too, but the order must come from the dates"
    assert [variant.seats.normalized for variant in dataset.variants] == [48, 36, 48, 44, 32]


def test_the_variant_order_does_not_come_from_the_file_order() -> None:
    newest_first = (variant_row("C", design_date="2025-02-17"), variant_row("A", design_date="2019-03-14"), variant_row("Z", design_date="someday"))
    assert [variant.id for variant in normalize(a_raw_dataset(variants=newest_first)).variants] == ["A", "C", "Z"]


def test_every_line_points_at_a_component_and_a_sub_assembly_that_exist(dataset: NormalizedDataset) -> None:
    components = {component.id for component in dataset.components}
    sub_assemblies = {sub_assembly.id for sub_assembly in dataset.sub_assemblies}
    variants = {variant.id for variant in dataset.variants}
    for line in dataset.lines:
        assert line.child_id in components and line.parent_id in sub_assemblies and line.variant_id in variants
        assert line.component_ref.normalized == line.child_id
        assert line.parent_id == f"{line.variant_id}:{line.sub_assembly_ref.normalized}"


def test_duplicate_spellings_fold_into_fewer_components_with_distinct_ids(dataset: NormalizedDataset, raw: RawDataset) -> None:
    ids = [component.id for component in dataset.components]
    assert len(ids) == len(set(ids)) and ids == sorted(ids)
    assert len(ids) < len({row.component_ref for row in raw.bom})
    assert {reference for component in dataset.components for reference in component.raw_references} == {row.component_ref for row in raw.bom}


def test_a_component_used_by_five_variants_is_one_entity_not_five(dataset: NormalizedDataset) -> None:
    key = reference_key("BGI-2031")
    [component] = [component for component in dataset.components if component.id == key]
    assert len(component.raw_references) >= 4 and "BGI-2031" in component.raw_references
    assert {line.variant_id for line in dataset.lines if line.child_id == key} == {"A", "B", "C", "D", "E"}


def test_a_sub_assembly_is_one_per_variant_even_when_the_reference_is_shared(dataset: NormalizedDataset) -> None:
    """C spells it `SA-O107`, A `SA-0107`: one reference key, two sub-assemblies — their contents are what #4 compares."""
    by_id = {sub_assembly.id: sub_assembly for sub_assembly in dataset.sub_assemblies}
    a, c = by_id[f"A:{reference_key('SA-0107')}"], by_id[f"C:{reference_key('SA-0107')}"]
    assert a.reference_key == c.reference_key and a.id != c.id
    assert a.raw_references == ("SA-0107",) and c.raw_references == ("SA-O107",)
    assert (a.variant_id, c.variant_id) == ("A", "C")


def test_the_spellings_of_a_supplier_fold_into_one(dataset: NormalizedDataset) -> None:
    [supplier] = [supplier for supplier in dataset.suppliers if supplier.id == text_key("Artois Polymères")]
    assert {"Artois Polymères", "Artois Polymères "} <= set(supplier.raw_names)
    assert len(dataset.suppliers) < len({line.supplier.raw for line in dataset.lines})
    assert all(line.supplier.normalized in {supplier.id for supplier in dataset.suppliers} for line in dataset.lines)


def test_every_raw_cell_of_every_row_is_carried_on_its_line_untouched(dataset: NormalizedDataset, raw: RawDataset) -> None:
    assert len(dataset.lines) == len(raw.bom)
    for line, row in zip(dataset.lines, raw.bom, strict=True):
        carried = (
            line.row_number,
            line.line_id,
            line.sub_assembly_ref.raw,
            line.sub_assembly_designation.raw,
            line.component_ref.raw,
            line.designation.raw,
            line.quantity.raw_value,
            line.quantity.raw_unit,
            line.supplier.raw,
            line.unit_cost.raw,
        )
        assert carried == (
            row.row_number,
            row.line_id,
            row.sub_assembly_ref,
            row.sub_assembly_designation,
            row.component_ref,
            row.designation,
            row.quantity,
            row.unit,
            row.supplier,
            row.unit_cost_eur,
        )


def test_notes_are_carried_through_untouched_with_their_date_read(dataset: NormalizedDataset, raw: RawDataset) -> None:
    assert [(note.note_id, note.text, note.date.raw) for note in dataset.notes] == [(row.note_id, row.text, row.date) for row in raw.notes]
    assert all(isinstance(note.date.normalized, date) for note in dataset.notes)


@pytest.mark.parametrize("reference", ["0031", " Bgi-2031", "BGI-2031 ", "bgi 2031"])
def test_a_reference_survives_normalization_byte_for_byte_in_its_raw_field(reference: str) -> None:
    result = normalize(a_raw_dataset(bom_row(component_ref=reference, sub_assembly_ref=f" {reference}")))
    assert result.lines[0].component_ref.raw == reference
    assert result.lines[0].sub_assembly_ref.raw == f" {reference}"
    assert reference in result.components[0].raw_references
    assert result.issues == ()


# --- unreadable values: kept, and counted ------------------------------------------------------


def test_an_unreadable_quantity_keeps_its_row_and_yields_exactly_one_issue() -> None:
    result = normalize(a_raw_dataset(bom_row(1), bom_row(2, line_id="L00002", quantity="abc")))
    assert len(result.lines) == 2
    line = result.lines[1]
    assert line.quantity == Quantity(raw_value="abc", raw_unit="pcs", value=None, unit=None)
    assert line.child_id == reference_key("BGI-2031"), "the rest of the row is still read"
    assert result.issues == (NormalizationIssue(source_file="bom.csv", row_number=2, row_id="L00002", field="quantity", raw="abc", reason="not a number"),)


@pytest.mark.parametrize(
    "cells, field, reason",
    [
        ({"quantity": "0"}, "quantity", "not positive"),
        ({"quantity": "1.234,56"}, "quantity", "ambiguous separators"),
        ({"unit": "cm"}, "unit", "unknown unit"),
        ({"unit_cost_eur": ""}, "unit_cost_eur", "empty"),
        ({"unit_cost_eur": "12 EUR"}, "unit_cost_eur", "not a number"),
        ({"supplier": "  "}, "supplier", "empty"),
        ({"designation": ""}, "designation", "empty"),
        ({"sub_assembly_designation": ""}, "sub_assembly_designation", "empty"),
        ({"variant_id": "Q"}, "variant_id", "unknown variant"),
        ({"variant_id": ""}, "variant_id", "empty"),
        ({"component_ref": "---"}, "component_ref", "empty reference"),
        ({"sub_assembly_ref": ""}, "sub_assembly_ref", "empty reference"),
        ({"line_id": " "}, "line_id", "empty"),
    ],
)
def test_each_unreadable_cell_is_one_issue_naming_its_field_and_its_raw_value(cells: dict[str, str], field: str, reason: str) -> None:
    result = normalize(a_raw_dataset(bom_row(7, **cells)))
    assert len(result.lines) == 1, "the row is kept"
    [issue] = result.issues
    assert (issue.source_file, issue.row_number, issue.field, issue.reason) == ("bom.csv", 7, field, reason)
    assert issue.raw == cells[field]
    assert issue.row_id == cells.get("line_id", "L7")


def test_an_absurdly_long_number_is_counted_like_any_other_unreadable_value() -> None:
    """Past Python's int-conversion limit and past the largest float: an issue each, no exception, no `Infinity`."""
    variants = (variant_row("A", seats="9" * 5000),)
    result = normalize(a_raw_dataset(bom_row(3, quantity="9" * 400, unit_cost_eur="9" * 400), variants=variants))
    assert result.variants[0].seats.normalized is None
    assert result.lines[0].quantity.value is None and result.lines[0].unit_cost.normalized is None
    assert [(issue.source_file, issue.field, issue.reason) for issue in result.issues] == [
        ("bom.csv", "quantity", "out of range"),
        ("bom.csv", "unit_cost_eur", "out of range"),
        ("variants.csv", "seats", "out of range"),
    ]


def test_a_zero_cost_is_a_cost() -> None:
    result = normalize(a_raw_dataset(bom_row(unit_cost_eur="0,00")))
    assert result.lines[0].unit_cost.normalized == 0.0 and result.issues == ()


def test_an_empty_reference_creates_no_component_and_no_sub_assembly() -> None:
    result = normalize(a_raw_dataset(bom_row(1, component_ref="---"), bom_row(2, sub_assembly_ref=" ", supplier="")))
    assert [line.child_id for line in result.lines] == ["", reference_key("BGI-2031")]
    assert [line.parent_id for line in result.lines] == [f"A:{reference_key('SA-0101')}", ""]
    assert [component.id for component in result.components] == [reference_key("BGI-2031")]
    assert [sub_assembly.id for sub_assembly in result.sub_assemblies] == [f"A:{reference_key('SA-0101')}"]
    assert [supplier.id for supplier in result.suppliers] == [text_key("Artois Polymères")]


@pytest.mark.parametrize("variants, variant_id", [(None, ""), (None, "Q"), ((variant_row("A"), variant_row(" ")), "")], ids=["empty", "unknown", "empty, and variants.csv has an empty id too"])
def test_a_line_of_an_empty_or_unknown_variant_creates_no_sub_assembly(variants: tuple[RawVariantRow, ...] | None, variant_id: str) -> None:
    """The variant is half of the sub-assembly's key: `:SA0101` or `Q:SA0101` would be a ghost for #4 to compare."""
    result = normalize(a_raw_dataset(bom_row(1), bom_row(2, variant_id=variant_id), variants=variants))
    assert [line.parent_id for line in result.lines] == [f"A:{reference_key('SA-0101')}", ""]
    assert [sub_assembly.id for sub_assembly in result.sub_assemblies] == [f"A:{reference_key('SA-0101')}"]
    kept = result.lines[1]
    assert kept.variant_id == variant_id and kept.sub_assembly_ref.normalized == reference_key("SA-0101"), "the line keeps what it said"
    assert kept.child_id == reference_key("BGI-2031"), "a component never names a variant: it is still one"
    assert ("bom.csv", 2, "variant_id") in {(issue.source_file, issue.row_number, issue.field) for issue in result.issues}


def test_a_variant_id_is_read_whatever_its_case_and_spacing() -> None:
    result = normalize(a_raw_dataset(bom_row(variant_id=" a ")))
    assert result.lines[0].variant_id == "A" and result.issues == ()


def test_unreadable_variant_and_note_cells_are_issues_too() -> None:
    variants = (variant_row("A", seats="forty-eight", design_date="14/03/2019"), variant_row("a "))
    notes = (RawNoteRow(row_number=1, note_id="N1", variant_id="B", date="yesterday", text="Ne pas monter."),)
    result = normalize(a_raw_dataset(variants=variants, notes=notes))
    assert len(result.variants) == 2 and len(result.notes) == 1
    assert result.notes[0].text == "Ne pas monter." and result.notes[0].date.normalized is None
    assert [(issue.source_file, issue.field, issue.reason) for issue in result.issues] == [
        ("notes.csv", "date", "not an ISO date"),
        ("notes.csv", "variant_id", "unknown variant"),
        ("variants.csv", "design_date", "not an ISO date"),
        ("variants.csv", "seats", "not an integer"),
        ("variants.csv", "variant_id", "duplicate variant"),
    ]


def test_issues_come_in_file_row_and_field_order() -> None:
    result = normalize(a_raw_dataset(bom_row(2, unit="cm", quantity="x"), bom_row(1, quantity="x")))
    assert [(issue.row_number, issue.field) for issue in result.issues] == [(1, "quantity"), (2, "quantity"), (2, "unit")]


def test_two_designations_under_one_key_are_both_kept_for_resolution(dataset: NormalizedDataset) -> None:
    """The three must-not-merge pairs share a key; their two product names are what #4's `reject` will read."""
    by_id = {component.id: component for component in dataset.components}
    for pair in SPEC.must_not_merge:
        component = by_id[reference_key(pair.left_reference)]
        assert {pair.left_reference, pair.right_reference} <= set(component.raw_references)
        assert len(component.designations) >= 2


def test_normalize_takes_the_raw_rows_and_nothing_else() -> None:
    """docs/ARCHITECTURE.md A5: no path, no spec — the signature has no room for anything but `ingest`'s rows."""
    assert list(inspect.signature(normalize).parameters) == ["raw"]
