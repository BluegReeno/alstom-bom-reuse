"""The two naive searches: what they find, what they cannot say, and what they are not allowed to read.

They exist to be beaten, which is exactly why they are tested like the tool: a baseline that
quietly read the normalized dataset, or that could answer *reusable*, would make the one gap this
build measures smaller than it is.
"""

import ast
from collections.abc import Callable, Collection
from pathlib import Path

import pytest

from bomreuse.baseline import exact_reference, same_name, sub_assembly_id, sub_assembly_ids
from bomreuse.ingest import read_raw
from bomreuse.model import Prediction, RawBomRow, RawDataset, ReuseClass
from test_pipeline_invariants import package_imports

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"
SOURCE = (ROOT / "src" / "bomreuse" / "baseline.py").read_text(encoding="utf-8")

#: The raw types a search may touch. Everything else `model.py` exports carries a normalized value.
RAW_TYPES = {"Prediction", "RawBomRow", "RawDataset", "ReuseClass"}

#: Both searches have the signature `evaluate` calls them through.
Search = Callable[[RawDataset, str, Collection[str]], tuple[Prediction, ...]]


def row(number: int, variant: str, reference: str, designation: str, component: str = "PART-1") -> RawBomRow:
    return RawBomRow(
        row_number=number,
        line_id=f"L{number:05d}",
        variant_id=variant,
        sub_assembly_ref=reference,
        sub_assembly_designation=designation,
        component_ref=component,
        designation="a part",
        quantity="1",
        unit="pcs",
        supplier="Someone",
        unit_cost_eur="1,00",
    )


def dataset_of(*rows: RawBomRow) -> RawDataset:
    return RawDataset(variants=(), bom=rows, notes=())


def ran(search: Search, *rows: RawBomRow) -> dict[str, Prediction]:
    return {prediction.sub_assembly_id: prediction for prediction in search(dataset_of(*rows), "C", ("A", "B"))}


# --- what they may read ---------------------------------------------------------------------


def test_the_searches_import_no_module_that_normalizes() -> None:
    """The gap must not close because a baseline borrowed the reference key or the SI units."""
    imported = package_imports(SOURCE)
    assert "normalize" not in imported, "a naive search that normalizes is not the search it is compared against"
    assert imported <= {"model"}, f"baseline.py imports {sorted(imported)}"


def test_the_searches_touch_only_the_raw_types() -> None:
    imported = {
        alias.name
        for node in ast.walk(ast.parse(SOURCE))
        if isinstance(node, ast.ImportFrom) and node.module == "bomreuse.model"
        for alias in node.names
    }
    assert imported <= RAW_TYPES, f"baseline.py reads {sorted(imported - RAW_TYPES)}, which carry normalized values"


# --- what they may say ----------------------------------------------------------------------


@pytest.mark.parametrize("search", [exact_reference, same_name])
def test_a_search_answers_in_the_prediction_vocabulary_and_never_in_the_ground_truths(search: Search) -> None:
    """`reused` or `specific`; `new` is a word only the ground truth may use (Decision 30)."""
    raw = read_raw(COMMITTED_RAW)
    predictions = search(raw, "C", ("A", "B", "D", "E"))
    assert predictions
    for prediction in predictions:
        assert isinstance(prediction.reuse_class, ReuseClass)
        assert prediction.reuse_class in (ReuseClass.REUSED, ReuseClass.SPECIFIC), "a search that reads no content cannot say 'reusable'"
        assert prediction.reuse_class.value != "new"
        assert prediction.diff is None
        assert prediction.variant_id == "C"


@pytest.mark.parametrize("search", [exact_reference, same_name])
def test_a_search_answers_for_every_sub_assembly_of_the_target_variant_and_no_other(search: Search) -> None:
    raw = read_raw(COMMITTED_RAW)
    answered = {prediction.sub_assembly_id for prediction in search(raw, "C", ("A", "B", "D", "E"))}
    expected = {sub_assembly_id("C", row.sub_assembly_ref) for row in raw.bom if row.variant_id == "C"}
    assert answered == expected


# --- exact reference ------------------------------------------------------------------------


def test_the_exact_reference_search_matches_character_for_character() -> None:
    found = ran(
        exact_reference,
        row(1, "A", "SA-0101", "carbody shell"),
        row(2, "A", "SA-0107", "auxiliary converter"),
        row(3, "C", "SA-0101", "carbody shell"),
        row(4, "C", "SA-O107", "auxiliary converter"),
        row(5, "C", "OCC-SA-0302", "trailer bogie"),
    )
    assert found["C:SA-0101"].reuse_class is ReuseClass.REUSED
    assert found["C:SA-0101"].ancestor_id == "A:SA-0101"
    # The typo family and the renumbered reference are what this search cannot see.
    assert found["C:SA-O107"].reuse_class is ReuseClass.SPECIFIC
    assert found["C:SA-O107"].ancestor_id == ""
    assert found["C:OCC-SA-0302"].reuse_class is ReuseClass.SPECIFIC


def test_a_reference_found_only_in_the_target_variant_is_no_match() -> None:
    found = ran(exact_reference, row(1, "C", "SA-0101", "carbody shell"), row(2, "C", "SA-0101", "carbody shell", "PART-2"))
    assert found["C:SA-0101"].reuse_class is ReuseClass.SPECIFIC


def test_a_variant_outside_the_chronology_is_no_ancestor() -> None:
    """Only the variants `evaluate` hands over are older: `D` is not among them here."""
    found = ran(exact_reference, row(1, "D", "SA-0101", "carbody shell"), row(2, "C", "SA-0101", "carbody shell"))
    assert found["C:SA-0101"].reuse_class is ReuseClass.SPECIFIC


# --- same name ------------------------------------------------------------------------------


def test_the_same_name_search_ignores_case_and_spacing_but_nothing_else() -> None:
    found = ran(
        same_name,
        row(1, "A", "SA-0102", "Trailer  Bogie"),
        row(2, "A", "SA-0110", "toilet module"),
        row(3, "C", "OCC-SA-0302", "trailer bogie"),
        row(4, "C", "OCC-SA-0310", "toilet modules"),
    )
    assert found["C:OCC-SA-0302"].reuse_class is ReuseClass.REUSED
    assert found["C:OCC-SA-0302"].ancestor_id == "A:SA-0102"
    assert found["C:OCC-SA-0310"].reuse_class is ReuseClass.SPECIFIC


def test_a_blank_designation_is_not_a_namesake() -> None:
    """Two sub-assemblies missing that column are not the same sub-assembly."""
    found = ran(same_name, row(1, "A", "SA-0101", "   "), row(2, "C", "OCC-SA-0301", ""))
    assert found["C:OCC-SA-0301"].reuse_class is ReuseClass.SPECIFIC


def test_the_ancestor_named_is_the_first_in_variant_order() -> None:
    """Several older sub-assemblies match; any is a valid source (Decision 25), and the answer must not move."""
    rows = [
        row(1, "B", "SA-0101", "carbody shell"),
        row(2, "A", "SA-0101", "carbody shell"),
        row(3, "C", "SA-0101", "carbody shell"),
    ]
    assert ran(same_name, *rows)["C:SA-0101"].ancestor_id == "A:SA-0101"
    assert ran(same_name, *reversed(rows))["C:SA-0101"].ancestor_id == "A:SA-0101"


# --- the identity the scorer reads them through ---------------------------------------------


def test_the_baselines_name_sub_assemblies_by_the_raw_reference() -> None:
    identity = sub_assembly_ids(read_raw(COMMITTED_RAW))
    assert identity[("C", "SA-O107")] == "C:SA-O107", "the typo is kept: it is what the file says"
    assert identity[("A", "SA-0107")] == "A:SA-0107"
    assert ("C", "SA0107") not in identity, "no folding, no key, no normalization"
