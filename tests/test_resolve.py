"""Resolution: which references become one component, which stay apart, and what is reported.

Every case goes through the real path — raw CSV cells, `normalize`, then `resolve` — so that a
test never hands `resolve` a reference key of its own making. The key belongs to `normalize`
(DECISIONS.md 27) and inheriting it is half of what this module promises.
"""

import ast
from pathlib import Path

import pytest

from bomreuse.ingest import read_raw
from bomreuse.model import Attribute, Finding, GroupVerdict, NormalizedDataset, RawBomRow, RawDataset, RawVariantRow, Resolution
from bomreuse.normalize import normalize
from bomreuse.resolve import match_reference, resolve
from bomreuse.rules import CATALOGUE
from bomreuse.spec import DEFAULT_SPEC_PATH, MustNotMergePair, load_spec

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "bomreuse"
COMMITTED_RAW = ROOT / "data" / "raw"

#: A BOM row as the file holds it: reference, designation, quantity, unit, supplier, cost.
Row = tuple[str, str, str, str, str, str]

_A_PART: Row = ("SHELL-ROOF", "Roof panel", "1", "pcs", "Atelier Lys Métal", "1200,00")


def dataset_of(*rows: Row) -> NormalizedDataset:
    """One variant, one sub-assembly, and the rows given — normalized exactly as the CLI would."""
    return normalize(
        RawDataset(
            variants=(RawVariantRow(1, "A", "Standard car", "2019-03-14", "Hauts-de-France", "48", "0", "electric"),),
            bom=tuple(
                RawBomRow(
                    row_number=number,
                    line_id=f"L{number:05d}",
                    variant_id="A",
                    sub_assembly_ref="SA-0101",
                    sub_assembly_designation="Carbody shell",
                    component_ref=reference,
                    designation=designation,
                    quantity=quantity,
                    unit=unit,
                    supplier=supplier,
                    unit_cost_eur=cost,
                )
                for number, (reference, designation, quantity, unit, supplier, cost) in enumerate(rows, start=1)
            ),
            notes=(),
        )
    )


def resolved(*rows: Row) -> tuple[Resolution, tuple[Finding, ...]]:
    return resolve(dataset_of(*rows))


def component_ids(resolution: Resolution) -> list[str]:
    return [component.id for component in resolution.components]


# --- one component, or two -----------------------------------------------------------------------


def test_the_spellings_the_rules_reach_become_one_canonical_component() -> None:
    """The acceptance case of issue #4: case, separators and homoglyphs all fold onto one key."""
    resolution, _ = resolved(
        ("BGI-2031", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"),
        ("BG1-2031", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"),
        ("bgi 2031 ", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"),
    )
    assert len(component_ids(resolution)) == 1
    assert resolution.components[0].raw_references == ("BG1-2031", "BGI-2031", "bgi 2031 ")
    assert resolution.groups[0].verdict is GroupVerdict.AUTO


def test_a_transposition_stays_a_second_component_and_the_miss_is_by_construction() -> None:
    """`BGI-2013` is the typo family the spec declares out of reach: undoing it needs string distance."""
    resolution, _ = resolved(
        ("BGI-2031", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"),
        ("BGI-2013", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"),
    )
    assert len(component_ids(resolution)) == 2

    family = next(f for f in load_spec().typo_families if f.kind == "transposition")
    assert not family.within_rules_reach, "the spec must still call this family out of reach, or this test is measuring nothing"


@pytest.mark.parametrize("pair", load_spec(DEFAULT_SPEC_PATH).must_not_merge, ids=lambda pair: pair.id)
def test_the_must_not_merge_pairs_of_the_spec_are_not_merged(pair: MustNotMergePair) -> None:
    """The two references share a canonical key on purpose; only the `reject` rule keeps them apart.

    A failure here is a false merge on the committed dataset — the worst error this tool can
    make — and the pair is named so the shortfall is reported rather than counted away.
    """
    resolution, _ = resolve(normalize(read_raw(COMMITTED_RAW)))
    holders = {
        component.id
        for component in resolution.components
        for reference in component.raw_references
        if reference.strip() in (pair.left_reference, pair.right_reference)
    }
    assert len(holders) == 2, f"{pair.id}: {pair.left_reference} and {pair.right_reference} landed in {sorted(holders)} — {pair.reason}"


# --- the verdict ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "second_row, attribute",
    [
        (("SEAT-RAIL", "Seat rail", "2", "pcs", "Atelier Lys Métal", "121,00"), Attribute.UNIT),
        (("SEAT-RAIL", "Seat rail", "1000", "mm", "Artois Polymères", "121,00"), Attribute.SUPPLIER),
        (("SEAT-RAIL", "Seat rail", "1000", "mm", "Atelier Lys Métal", "134,00"), Attribute.COST),
    ],
    ids=["unit", "supplier", "cost"],
)
def test_a_group_diverging_on_one_attribute_is_reviewed_and_reported(second_row: Row, attribute: Attribute) -> None:
    resolution, findings = resolved(("SEAT-RAIL", "Seat rail", "1000", "mm", "Atelier Lys Métal", "121,00"), second_row)
    group = resolution.groups[0]
    assert group.verdict is GroupVerdict.REVIEW
    assert group.diverging == (attribute,)
    assert len(component_ids(resolution)) == 1, "a divergence is a finding, not a doubt about what the part is (Decision 26)"

    conflict = one_finding("resolution.group_conflict", findings)
    assert attribute.value in conflict.message
    assert {row.row_number for row in conflict.source_rows} == {1, 2}


def test_a_designation_said_at_greater_length_is_reviewed_not_split() -> None:
    """`seat rail` inside `seat rail, aluminium`: one product described twice, and a finding."""
    resolution, findings = resolved(
        ("SEAT-RAIL", "Seat rail", "1", "pcs", "Atelier Lys Métal", "121,00"),
        ("SEAT-RAIL", "Seat rail, aluminium", "1", "pcs", "Atelier Lys Métal", "121,00"),
    )
    assert resolution.groups[0].verdict is GroupVerdict.REVIEW
    assert resolution.groups[0].diverging == (Attribute.DESIGNATION,)
    assert one_finding("resolution.group_conflict", findings)


def test_designations_that_name_two_products_split_the_group_back_apart() -> None:
    resolution, findings = resolved(
        ("SEAT-RAIL-I", "Floor rail, stainless steel", "6", "pcs", "Atelier Lys Métal", "312.00"),
        ("SEAT-RAIL-1", "Mounting rail, aluminium, mark 1", "2", "pcs", "Atelier Lys Métal", "121,00"),
    )
    group = resolution.groups[0]
    assert group.verdict is GroupVerdict.REJECT
    assert component_ids(resolution) == ["SEATRA111#1", "SEATRA111#2"]
    assert [component.raw_references for component in group.components] == [("SEAT-RAIL-I",), ("SEAT-RAIL-1",)]
    assert [component.rows for component in group.components] == [(1,), (2,)]

    split = one_finding("resolution.group_split", findings)
    assert "SEAT-RAIL-I" in split.message and "SEAT-RAIL-1" in split.message
    assert {row.row_number for row in split.source_rows} == {1, 2}


def test_two_spellings_of_one_amount_are_not_a_unit_conflict() -> None:
    """`1000 mm` and `1 m`: normalization already made them one amount, so nothing survives to report."""
    resolution, findings = resolved(
        ("SEAT-RAIL", "Seat rail", "1000", "mm", "Atelier Lys Métal", "121,00"),
        ("SEAT-RAIL", "Seat rail", "1", "m", "Atelier Lys Métal", "121,00"),
    )
    assert resolution.groups[0].verdict is GroupVerdict.AUTO
    assert findings == ()


def test_rows_that_agree_on_everything_need_no_review() -> None:
    resolution, findings = resolved(_A_PART, _A_PART)
    assert resolution.groups[0].verdict is GroupVerdict.AUTO
    assert resolution.groups[0].diverging == ()
    assert findings == (), "one reference, one spelling, no disagreement: nothing to tell anyone"


def test_a_value_normalize_could_not_read_is_not_a_disagreement() -> None:
    """It is already a `NormalizationIssue`; calling it a conflict would report one defect twice."""
    dataset = dataset_of(
        ("SHELL-ROOF", "Roof panel", "1", "pcs", "Atelier Lys Métal", "1200,00"),
        ("SHELL-ROOF", "Roof panel", "1", "pcs", "", ""),
    )
    assert dataset.issues, "the row really is unreadable, or this test proves nothing"
    resolution, findings = resolve(dataset)
    assert resolution.groups[0].verdict is GroupVerdict.AUTO
    assert findings == ()


# --- the duplicate-reference finding -------------------------------------------------------------


def test_several_spellings_of_one_reference_are_reported_with_one_row_each() -> None:
    resolution, findings = resolved(
        ("BGI-2031", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"),
        ("BGI-2031", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"),
        ("BGI-2O31", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"),
    )
    duplicate = one_finding("resolution.duplicate_reference", findings)
    assert duplicate.subject == resolution.components[0].id
    assert "BGI-2O31" in duplicate.message
    assert {row.row_number for row in duplicate.source_rows} == {1, 3}, "one row per spelling, not one per line"
    assert {row.source_file for row in duplicate.source_rows} == {"bom.csv"}


def test_a_split_part_that_is_itself_written_twice_is_still_reported() -> None:
    resolution, findings = resolved(
        ("DOOR-SEAL-O", "Gangway door seal, outer", "4", "pcs", "Artois Polymères", "81,00"),
        ("door-seal-o ", "Gangway door seal, outer", "4", "pcs", "Artois Polymères", "81,00"),
        ("DOOR-SEAL-0", "Inner door seal, revision 0", "2", "pcs", "Artois Polymères", "52,00"),
    )
    assert resolution.groups[0].verdict is GroupVerdict.REJECT
    duplicate = one_finding("resolution.duplicate_reference", findings)
    assert duplicate.subject == "D00RSEA10#1", "the finding is about the part that is written twice, not about the whole group"


# --- `match_reference`, and the fact that nobody else does this ------------------------------------


def test_match_reference_finds_a_component_through_any_spelling() -> None:
    resolution, _ = resolved(("BGI-2031", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"))
    for token in ("BGI-2031", "bgi 2031 ", "BG1_2O31"):
        candidate = match_reference(resolution, token)
        assert candidate is not None and candidate.raw_token == token
        assert [component.id for component in candidate.components] == ["BG12031"]


def test_match_reference_shows_the_ambiguity_of_a_split_group_instead_of_guessing() -> None:
    resolution, _ = resolved(
        ("SEAT-RAIL-I", "Floor rail, stainless steel", "6", "pcs", "Atelier Lys Métal", "312.00"),
        ("SEAT-RAIL-1", "Mounting rail, aluminium, mark 1", "2", "pcs", "Atelier Lys Métal", "121,00"),
    )
    candidate = match_reference(resolution, "SEAT-RAIL-1")
    assert candidate is not None
    assert [component.id for component in candidate.components] == ["SEATRA111#1", "SEATRA111#2"]


@pytest.mark.parametrize("token", ["", "   ", "---", "NOT-A-PART"])
def test_match_reference_returns_nothing_rather_than_the_nearest_thing(token: str) -> None:
    resolution, _ = resolved(("BGI-2031", "Bolt set M8", "4", "pcs", "Atelier Lys Métal", "3,50"))
    assert match_reference(resolution, token) is None


#: Where turning a string into a canonical component is allowed to happen (docs/ARCHITECTURE.md A7).
#: `link.py` joins this set in #6 — one line, deliberately, so that a second matcher is a decision.
MATCHERS = {"resolve.py"}


def names_used(source: str) -> set[str]:
    """Every identifier a module names: imports, calls, attributes."""
    used: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            used |= {part for alias in node.names for part in (alias.name, alias.asname) if part}
        elif isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
    return used


def test_the_name_scanner_sees_a_call_however_it_is_reached() -> None:
    assert "match_reference" in names_used("from bomreuse.resolve import match_reference\nmatch_reference(r, 'x')\n")
    assert "match_reference" in names_used("from bomreuse import resolve\nresolve.match_reference(r, 'x')\n")
    assert "match_reference" in names_used("from bomreuse.resolve import match_reference as m\n")
    assert "match_reference" not in names_used("from bomreuse.resolve import resolve\nresolve(dataset)\n")


@pytest.mark.parametrize("module", sorted(path.name for path in SRC.rglob("*.py") if path.name not in MATCHERS))
def test_only_resolve_turns_a_string_into_a_canonical_component(module: str) -> None:
    assert "match_reference" not in names_used((SRC / module).read_text(encoding="utf-8")), (
        f"{module} matches references itself. docs/ARCHITECTURE.md A7: only resolve.py does, "
        f"and link.py (#6) is the one module that may be added to MATCHERS."
    )


# --- every finding is traceable ----------------------------------------------------------------------


def one_finding(rule_id: str, findings: tuple[Finding, ...]) -> Finding:
    matching = [finding for finding in findings if finding.rule_id == rule_id]
    assert len(matching) == 1, f"expected one {rule_id}, got {[finding.rule_id for finding in findings]}"
    return matching[0]


def test_every_finding_resolution_emits_names_a_rule_of_the_catalogue_and_its_rows() -> None:
    _, findings = resolve(normalize(read_raw(COMMITTED_RAW)))
    assert findings
    for finding in findings:
        assert finding.rule_id in CATALOGUE, finding
        assert finding.confidence == CATALOGUE[finding.rule_id].confidence
        assert finding.source_rows, finding
        assert finding.subject and finding.message
