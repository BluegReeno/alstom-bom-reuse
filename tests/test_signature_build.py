"""Signatures read off the resolved BOM: on the committed dataset, and on rows written by hand.

Every hand-written case goes through the real path — raw CSV cells, `normalize`, `resolve`, then
`build_signatures` — like `test_resolve.py`, so that no test invents a reference key or a
canonical component id of its own.

What the committed dataset is used for is the part no small fixture can show: Decision 26, that a
group under `review` for a planted supplier, cost or unit conflict still feeds the signatures,
and that a `reject` splits one before they are built.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from bomreuse.ingest import read_raw
from bomreuse.model import Attribute, GroupVerdict, NormalizedDataset, RawBomRow, RawDataset, RawVariantRow, Resolution, Signature, SubAssemblySignature
from bomreuse.normalize import normalize, reference_key
from bomreuse.resolve import resolve
from bomreuse.signatures import build_signatures

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"

#: The design dates the hand-written rows borrow, so a variant letter is enough to place a row.
DESIGN_DATES: Mapping[str, str] = {"A": "2019-03-14", "B": "2021-06-02", "C": "2025-02-17"}


@dataclass(frozen=True, slots=True)
class Row:
    """One row of `bom.csv`, with the columns a signature does not read left at a default."""

    variant: str
    sub_assembly: str
    reference: str
    designation: str
    quantity: str = "1"
    unit: str = "pcs"
    supplier: str = "Atelier Lys Métal"
    cost: str = "10,00"


def dataset_of(rows: Sequence[Row], dates: Mapping[str, str] = DESIGN_DATES) -> NormalizedDataset:
    return normalize(
        RawDataset(
            variants=tuple(
                RawVariantRow(number, variant, f"Variant {variant}", dates[variant], "Hauts-de-France", "48", "0", "electric")
                for number, variant in enumerate(sorted({row.variant for row in rows}), start=1)
            ),
            bom=tuple(
                RawBomRow(
                    row_number=number,
                    line_id=f"L{number:05d}",
                    variant_id=row.variant,
                    sub_assembly_ref=row.sub_assembly,
                    sub_assembly_designation=f"sub-assembly {row.sub_assembly}",
                    component_ref=row.reference,
                    designation=row.designation,
                    quantity=row.quantity,
                    unit=row.unit,
                    supplier=row.supplier,
                    unit_cost_eur=row.cost,
                )
                for number, row in enumerate(rows, start=1)
            ),
            notes=(),
        )
    )


def signatures_of(rows: Sequence[Row]) -> dict[str, Signature]:
    dataset = dataset_of(rows)
    resolution, _ = resolve(dataset)
    return {built.sub_assembly_id: built.signature for built in build_signatures(dataset, resolution)}


def built_of(rows: Sequence[Row]) -> dict[str, SubAssemblySignature]:
    dataset = dataset_of(rows)
    resolution, _ = resolve(dataset)
    return {built.sub_assembly_id: built for built in build_signatures(dataset, resolution)}


def expected(counts: Mapping[str, float], units: Mapping[str, str] | None = None) -> Signature:
    """The signature the raw references given should produce, keyed the way `normalize` keys them.

    Going through `reference_key` rather than spelling `SHE11R00F` by hand keeps the expectation
    a statement about the signature, not a second copy of the folding rules (DECISIONS.md 27).
    """
    fold = {reference: reference_key(reference) for reference in counts}
    return Signature.from_counts(
        {fold[reference]: quantity for reference, quantity in counts.items()},
        {fold[reference]: unit for reference, unit in (units or {}).items()},
    )


def components_of(signature: Signature) -> list[str]:
    return [item.component for item in signature.items]


@pytest.fixture(scope="module")
def committed() -> tuple[NormalizedDataset, Resolution, tuple[SubAssemblySignature, ...]]:
    dataset = normalize(read_raw(COMMITTED_RAW))
    resolution, _ = resolve(dataset)
    return dataset, resolution, build_signatures(dataset, resolution)


# --- what a signature is -----------------------------------------------------------------------


def test_a_signature_is_the_components_a_sub_assembly_contains_with_si_quantities() -> None:
    signatures = signatures_of(
        [
            Row("A", "SA-0101", "SHELL-ROOF", "Roof assembly", "1", "units"),
            Row("A", "SA-0101", "SHELL-SEAL", "Door seal", "1,5", "m"),
            Row("A", "SA-0101", "SHELL-GLUE", "Structural glue", "800", "g"),
        ]
    )
    assert signatures["A:SA0101"] == expected(
        {"SHELL-ROOF": 1.0, "SHELL-SEAL": 1.5, "SHELL-GLUE": 0.8},
        {"SHELL-SEAL": "m", "SHELL-GLUE": "kg"},
    )


def test_every_sub_assembly_of_every_variant_gets_one_signature(committed: tuple[NormalizedDataset, Resolution, tuple[SubAssemblySignature, ...]]) -> None:
    dataset, _, signatures = committed
    assert [built.sub_assembly_id for built in signatures] == [sub_assembly.id for sub_assembly in dataset.sub_assemblies]
    assert all(len(built.signature) > 0 for built in signatures)


def test_the_spellings_the_rules_fold_are_one_component_on_both_sides() -> None:
    """The hidden reuse the tool exists to find: two variants, one part, two spellings of it."""
    signatures = signatures_of(
        [
            Row("A", "SA-0101", "BGI-2031", "Bolt set M8", "4"),
            Row("C", "OCC-SA-0101", "BG1-2031", "Bolt set M8", "4"),
        ]
    )
    assert components_of(signatures["A:SA0101"]) == components_of(signatures["C:0CCSA0101"]) == [reference_key("BGI-2031")]


# --- Decision 26: which groups feed the signatures -------------------------------------------------


def test_a_group_under_review_for_a_supplier_or_cost_conflict_still_feeds_the_signatures() -> None:
    dataset = dataset_of(
        [
            Row("A", "SA-0101", "SHELL-ROOF", "Roof assembly", supplier="Atelier Lys Métal", cost="1200,00"),
            Row("C", "OCC-SA-0101", "SHELL-ROOF", "Roof assembly", supplier="Normandie Structures", cost="1310,00"),
        ]
    )
    resolution, _ = resolve(dataset)
    assert resolution.groups[0].verdict is GroupVerdict.REVIEW
    assert set(resolution.groups[0].diverging) == {Attribute.SUPPLIER, Attribute.COST}

    signatures = {built.sub_assembly_id: built.signature for built in build_signatures(dataset, resolution)}
    assert components_of(signatures["A:SA0101"]) == components_of(signatures["C:0CCSA0101"]) == [reference_key("SHELL-ROOF")]


def test_every_planted_conflict_of_the_committed_dataset_is_still_in_the_signatures_that_hold_it(
    committed: tuple[NormalizedDataset, Resolution, tuple[SubAssemblySignature, ...]],
) -> None:
    """Decision 26 on the real data: reading `auto` groups only would blind the backtest here.

    The dataset plants a supplier, cost or unit conflict on components that appear in most of the
    newest variant's sub-assemblies. Each of them must still be in the signature of every
    sub-assembly whose lines carry it.
    """
    dataset, resolution, signatures = committed
    by_sub_assembly = {built.sub_assembly_id: built.signature for built in signatures}
    conflicted = {group.reference_key for group in resolution.groups if group.verdict is GroupVerdict.REVIEW}
    assert len(conflicted) >= 10, "the committed dataset is the one Decision 26 was written about"

    holders = {(line.parent_id, line.child_id) for line in dataset.lines if line.child_id in conflicted and line.parent_id}
    assert holders
    for sub_assembly_id, component in sorted(holders):
        assert component in by_sub_assembly[sub_assembly_id].by_component, f"{component} was dropped from {sub_assembly_id}"


def test_a_rejected_group_is_split_before_the_signatures_are_built(
    committed: tuple[NormalizedDataset, Resolution, tuple[SubAssemblySignature, ...]],
) -> None:
    """The other half of Decision 26: two products behind one key never share a signature line."""
    _, resolution, signatures = committed
    rejected = [group for group in resolution.groups if group.verdict is GroupVerdict.REJECT]
    assert rejected, "the committed dataset plants the must-not-merge pairs this is about"

    seen = {item.component for built in signatures for item in built.signature.items}
    for group in rejected:
        assert group.reference_key not in seen, f"{group.reference_key} was kept whole although its designations name two products"
        assert {component.id for component in group.components} & seen


# --- the lines a signature is read off -------------------------------------------------------------


def test_several_lines_of_one_component_carry_their_total() -> None:
    """A bill of materials names a part once per position; the signature is a multiset of parts."""
    signatures = signatures_of(
        [
            Row("A", "SA-0101", "SHELL-BOLT", "Bolt set M8", "4"),
            Row("A", "SA-0101", "SHELL-BOLT", "Bolt set M8", "6"),
        ]
    )
    assert signatures["A:SA0101"] == expected({"SHELL-BOLT": 10.0})


def test_a_line_whose_amount_cannot_be_read_leaves_its_component_out_and_is_counted() -> None:
    dataset = dataset_of(
        [
            Row("A", "SA-0101", "SHELL-ROOF", "Roof assembly", "1"),
            Row("A", "SA-0101", "SHELL-SEAL", "Door seal", "abc"),
        ]
    )
    resolution, _ = resolve(dataset)
    signatures = {built.sub_assembly_id: built.signature for built in build_signatures(dataset, resolution)}
    assert components_of(signatures["A:SA0101"]) == [reference_key("SHELL-ROOF")]
    assert [issue.field for issue in dataset.issues] == ["quantity"]


def test_two_units_for_one_part_in_one_sub_assembly_are_not_added_up() -> None:
    """After normalization the units are SI: a residual difference is a defect, not an amount."""
    signatures = signatures_of(
        [
            Row("A", "SA-0101", "SHELL-GLUE", "Structural glue", "2", "kg"),
            Row("A", "SA-0101", "SHELL-GLUE", "Structural glue", "3", "m"),
            Row("A", "SA-0101", "SHELL-GLUE", "Structural glue", "500", "g"),
        ]
    )
    assert signatures["A:SA0101"] == expected({"SHELL-GLUE": 2.5}, {"SHELL-GLUE": "kg"})


# --- what the signature says it could not read -------------------------------------------------
# A signature is compared as the *content* of a sub-assembly, so a line that reached no item of
# it must not simply vanish: a shorter multiset is a smaller sub-assembly to `compare`, and two
# signatures nothing could be read of are identical to it.


def test_a_line_whose_amount_cannot_be_read_is_counted_on_the_signature_it_is_missing_from() -> None:
    built = built_of(
        [
            Row("A", "SA-0101", "SHELL-ROOF", "Roof assembly", "1"),
            Row("A", "SA-0101", "SHELL-SEAL", "Door seal", "abc"),
        ]
    )
    assert components_of(built["A:SA0101"].signature) == [reference_key("SHELL-ROOF")]
    assert built["A:SA0101"].lines_left_out == 1


def test_a_line_resolve_places_in_no_component_is_counted_on_the_signature_it_is_missing_from() -> None:
    """An empty reference names no component, so the row reaches no item — and the part is real."""
    built = built_of(
        [
            Row("A", "SA-0101", "SHELL-ROOF", "Roof assembly", "1"),
            Row("A", "SA-0101", "", "Door seal", "1"),
        ]
    )
    assert components_of(built["A:SA0101"].signature) == [reference_key("SHELL-ROOF")]
    assert built["A:SA0101"].lines_left_out == 1


def test_a_sub_assembly_read_whole_leaves_nothing_out() -> None:
    built = built_of([Row("A", "SA-0101", "SHELL-ROOF", "Roof assembly", "1"), Row("A", "SA-0101", "SHELL-SEAL", "Door seal", "1,5", "m")])
    assert built["A:SA0101"].lines_left_out == 0


def test_the_committed_dataset_is_read_whole(committed: tuple[NormalizedDataset, Resolution, tuple[SubAssemblySignature, ...]]) -> None:
    """The dirt of #2 is in the references and the units, not in unreadable lines: every answer of the demo rests on all of them."""
    _, _, signatures = committed
    assert [built.sub_assembly_id for built in signatures if built.lines_left_out] == []


def test_a_line_naming_no_sub_assembly_lands_in_no_signature() -> None:
    """Decision 28: an unknown variant leaves `parent_id` empty, and no sub-assembly is created."""
    orphan = RawBomRow(2, "L00002", "Q", "SA-0101", "Carbody shell", "SHELL-ROOF", "Roof assembly", "1", "pcs", "Atelier Lys Métal", "10,00")
    dataset = normalize(
        RawDataset(
            variants=(RawVariantRow(1, "A", "Variant A", DESIGN_DATES["A"], "Hauts-de-France", "48", "0", "electric"),),
            bom=(
                RawBomRow(1, "L00001", "A", "SA-0101", "Carbody shell", "SHELL-ROOF", "Roof assembly", "1", "pcs", "Atelier Lys Métal", "10,00"),
                orphan,
            ),
            notes=(),
        )
    )
    resolution, _ = resolve(dataset)
    signatures = build_signatures(dataset, resolution)
    assert [built.sub_assembly_id for built in signatures] == ["A:SA0101"]
    assert signatures[0].signature == expected({"SHELL-ROOF": 1.0})
