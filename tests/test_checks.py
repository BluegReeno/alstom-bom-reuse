"""Inconsistency checks: a canonical component whose rows disagree on its unit, supplier or cost.

Every case goes through the real path — raw CSV cells, `normalize`, `resolve`, then `check` — so
the values compared are the ones `normalize` read, and the components the ones `resolve` made.
"""

from pathlib import Path

import pytest

from bomreuse.checks import CONFLICT_RULES, check, conflicts_by_component
from bomreuse.ingest import read_raw
from bomreuse.model import Attribute, Finding, GroupVerdict, NormalizedDataset, RawBomRow, RawDataset, RawVariantRow, Resolution
from bomreuse.normalize import normalize
from bomreuse.resolve import resolve
from bomreuse.rules import CATALOGUE
from bomreuse.signatures import build_signatures

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"

#: A BOM row as the file holds it: variant, reference, designation, quantity, unit, supplier, cost.
Row = tuple[str, str, str, str, str, str, str]

_VARIANTS = (
    RawVariantRow(1, "A", "Standard car", "2019-03-14", "Hauts-de-France", "48", "0", "electric"),
    RawVariantRow(2, "B", "Bike car", "2021-06-01", "Hauts-de-France", "40", "6", "electric"),
)


def dataset_of(*rows: Row) -> NormalizedDataset:
    """Two variants, one sub-assembly each, and the rows given — normalized as the CLI would."""
    return normalize(
        RawDataset(
            variants=_VARIANTS,
            bom=tuple(
                RawBomRow(
                    row_number=number,
                    line_id=f"L{number:05d}",
                    variant_id=variant,
                    sub_assembly_ref="SA-0101",
                    sub_assembly_designation="Carbody shell",
                    component_ref=reference,
                    designation=designation,
                    quantity=quantity,
                    unit=unit,
                    supplier=supplier,
                    unit_cost_eur=cost,
                )
                for number, (variant, reference, designation, quantity, unit, supplier, cost) in enumerate(rows, start=1)
            ),
            notes=(),
        )
    )


def checked(*rows: Row) -> tuple[Resolution, tuple[Finding, ...]]:
    dataset = dataset_of(*rows)
    resolution, _ = resolve(dataset)
    return resolution, check(dataset, resolution)


_ROOF: Row = ("A", "SHELL-ROOF", "Roof panel", "1", "pcs", "Atelier Lys Métal", "1200,00")


def _in_b(
    *,
    reference: str = "SHELL-ROOF",
    quantity: str = "1",
    unit: str = "pcs",
    supplier: str = "Atelier Lys Métal",
    cost: str = "1200,00",
) -> Row:
    """The roof panel's row as variant B holds it, with whatever the case changes."""
    return ("B", reference, "Roof panel", quantity, unit, supplier, cost)


# --- one finding per attribute the rows disagree on ---------------------------------------------


@pytest.mark.parametrize(
    ("second_row", "rule_id", "said"),
    [
        (_in_b(quantity="2", unit="m"), "checks.unit_conflict", "'pcs' in A; 'm' in B"),
        (_in_b(supplier="Sambre Freinage"), "checks.supplier_conflict", "'atelier lys métal' in A; 'sambre freinage' in B"),
        (_in_b(cost="1380.00"), "checks.cost_conflict", "1200.00 EUR in A; 1380.00 EUR in B"),
    ],
)
def test_a_value_that_moves_between_variants_is_one_finding_citing_one_row_per_value(second_row: Row, rule_id: str, said: str) -> None:
    _, findings = checked(_ROOF, second_row)
    assert [finding.rule_id for finding in findings] == [rule_id]
    finding = findings[0]
    assert finding.subject == "SHE11R00F"
    assert finding.confidence == CATALOGUE[rule_id].confidence
    assert said in finding.message
    assert [row.row_number for row in finding.source_rows] == [1, 2]
    assert {row.source_file for row in finding.source_rows} == {"bom.csv"}


def test_a_component_disagreeing_on_three_attributes_gets_three_findings_in_a_stable_order() -> None:
    _, findings = checked(_ROOF, _in_b(quantity="2", unit="kg", supplier="Sambre Freinage", cost="99"))
    assert [finding.rule_id for finding in findings] == ["checks.unit_conflict", "checks.supplier_conflict", "checks.cost_conflict"]


def test_the_message_names_the_reference_as_the_file_writes_it_not_the_folded_key() -> None:
    _, findings = checked(_ROOF, _ROOF, _in_b(reference="shell roof ", supplier="Sambre Freinage"))
    assert findings[0].message.startswith("'SHELL-ROOF' (component SHE11R00F)")


def test_two_rows_of_one_variant_disagreeing_are_reported_too() -> None:
    """The ground truth records a variant disagreeing with itself: the check reads rows, not pairs."""
    _, findings = checked(_ROOF, ("A", "SHELL-ROOF", "Roof panel", "1", "pcs", "Atelier Lys Métal", "1500,00"))
    assert [finding.rule_id for finding in findings] == ["checks.cost_conflict"]
    assert "in A;" in findings[0].message and "in A." in findings[0].message


# --- what is not a conflict -----------------------------------------------------------------------


def test_values_normalization_made_equal_are_agreement() -> None:
    """`1000 mm` and `1 m`, `12,50` and `12.50`, a supplier's case and trailing space."""
    first = ("A", "SHELL-ROOF", "Roof panel", "1000", "mm", "Atelier Lys Métal", "12,50")
    second = ("B", "SHELL-ROOF", "Roof panel", "1", "m", "ATELIER LYS MÉTAL ", "12.50")
    assert checked(first, second)[1] == ()


def test_an_unreadable_value_is_not_a_second_value() -> None:
    _, findings = checked(_ROOF, _in_b(quantity="two", supplier="", cost="n/a"))
    assert findings == ()


def test_rows_that_agree_on_everything_give_nothing() -> None:
    assert checked(_ROOF, _in_b())[1] == ()


# --- the split parts of a rejected group ----------------------------------------------------------


def test_a_split_part_is_checked_like_any_other_component() -> None:
    """The gap PR #19 found: `resolve` reports no conflict inside the parts of a `reject` group.

    Two rows are the same stainless floor rail from two suppliers at two costs, the third is
    another product sharing the key. The check runs on the parts, so the rail's disagreement is
    reported against `SEATRA111#1`, and the mounting rail is left alone.
    """
    resolution, findings = checked(
        ("A", "SEAT-RAIL-I", "Floor rail, stainless steel", "6", "pcs", "Atelier Lys Métal", "312.00"),
        ("B", "SEAT-RAIL-I", "Floor rail, stainless steel", "6", "pcs", "Sambre Freinage", "340.00"),
        ("A", "SEAT-RAIL-1", "Mounting rail, aluminium, mark 1", "2", "pcs", "Atelier Lys Métal", "121,00"),
    )
    assert resolution.groups[0].verdict is GroupVerdict.REJECT
    assert [(finding.subject, finding.rule_id) for finding in findings] == [
        ("SEATRA111#1", "checks.supplier_conflict"),
        ("SEATRA111#1", "checks.cost_conflict"),
    ]


# --- reading the findings back ------------------------------------------------------------------


def test_conflicts_by_component_reads_only_the_checks_own_findings() -> None:
    dataset = dataset_of(_ROOF, _in_b(reference="SHELL ROOF", supplier="Sambre Freinage", cost="99"))
    resolution, resolution_findings = resolve(dataset)
    findings = resolution_findings + check(dataset, resolution)
    assert {finding.rule_id for finding in resolution_findings}, "the case must carry resolution findings to ignore"
    assert conflicts_by_component(findings) == {"SHE11R00F": (Attribute.SUPPLIER, Attribute.COST)}


def test_every_conflict_rule_is_in_the_catalogue() -> None:
    assert set(CONFLICT_RULES) <= set(CATALOGUE)
    assert set(CONFLICT_RULES.values()) == {Attribute.UNIT, Attribute.SUPPLIER, Attribute.COST}


# --- on the committed dataset: a conflict is a finding, not a doubt about the part ----------------


def test_a_component_carrying_a_planted_conflict_stays_merged_and_in_its_signatures() -> None:
    """Decision 26: the part whose supplier, cost or unit moves is still that part."""
    dataset = normalize(read_raw(COMMITTED_RAW))
    resolution, _ = resolve(dataset)
    findings = check(dataset, resolution)
    assert findings

    group_of = {component.id: group for group in resolution.groups for component in group.components}
    component_of = {component.id: component for component in resolution.components}
    signatures = {signature.sub_assembly_id: signature for signature in build_signatures(dataset, resolution)}
    parent_of_row = {line.row_number: line.parent_id for line in dataset.lines}

    for finding in findings:
        group = group_of[finding.subject]
        assert group.verdict is GroupVerdict.REVIEW and len(group.components) == 1, finding.subject
        holders = {parent_of_row[row] for row in component_of[finding.subject].rows}
        assert len({line.variant_id for line in dataset.lines if line.parent_id in holders}) > 1
        for holder in holders:
            assert finding.subject in {item.component for item in signatures[holder].signature.items}, (finding.subject, holder)
