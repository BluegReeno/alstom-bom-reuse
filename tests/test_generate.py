"""What the generator plants, checked in memory: the contract's counts, the defects, the honesty rules."""

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from bomreuse import catalogue
from bomreuse.catalogue import FactScript, NoteScript
from bomreuse.generate import (
    DEFAULT_SEED,
    Dataset,
    GenerationError,
    OutputPathError,
    TrueModel,
    build_true_model,
    derive_ground_truth,
    generate,
    render,
)
from bomreuse.ground_truth import GroundTruth
from bomreuse.spec import DatasetRules, DatasetSpec, MustNotMergePair, StoryCase, TypoFamily, load_spec

SPEC: DatasetSpec = load_spec()
CASES: tuple[StoryCase, ...] = SPEC.story_cases
FAMILIES: tuple[TypoFamily, ...] = SPEC.typo_families
PAIRS: tuple[MustNotMergePair, ...] = SPEC.must_not_merge
OUT_OF_REACH = {spelling for family in FAMILIES if not family.within_rules_reach for spelling in family.variants}


@dataclass(frozen=True)
class Build:
    model: TrueModel
    dataset: Dataset
    truth: GroundTruth


def build(seed: int) -> Build:
    model = build_true_model(SPEC)
    dataset = render(model, SPEC, seed)
    return Build(model, dataset, derive_ground_truth(model, dataset, SPEC, seed))


@pytest.fixture(scope="module")
def built() -> Build:
    return build(DEFAULT_SEED)


# --- the contract's counts -------------------------------------------------------------------


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_a_story_sub_assembly_holds_exactly_what_the_spec_says(built: Build, case: StoryCase, side: str) -> None:
    variant = case.left_variant if side == "left" else case.right_variant
    expected = case.left if side == "left" else case.right
    lines = [line for line in built.model.lines if line.variant_id == variant and line.sub_assembly == case.sub_assembly]
    assert {line.reference: line.quantity for line in lines} == dict(expected)
    for line in lines:
        assert line.base_unit == case.units.get(line.reference, SPEC.dataset.default_unit), line.reference


def test_true_ids_are_sequential_and_step_over_the_ids_the_spec_reserves(built: Build) -> None:
    reserved = {true_id for pair in PAIRS for true_id in (pair.left_true_component, pair.right_true_component)}
    free = [part.true_id for part in built.model.parts.values() if part.true_id not in reserved]
    assert free[0] == "TRUE-0001"
    assert free == sorted(free) and len(set(free)) == len(free)
    assert int(free[-1][5:]) > int(max(reserved)[5:]), "the master must be long enough to reach the reserved range"
    assert reserved <= {part.true_id for part in built.model.parts.values()}


# --- planted spellings -----------------------------------------------------------------------


@pytest.mark.parametrize("family", FAMILIES, ids=[family.id for family in FAMILIES])
def test_every_spelling_of_every_typo_family_is_emitted(built: Build, family: TypoFamily) -> None:
    emitted = {row.component_ref for row in built.dataset.bom if row.true.reference == family.canonical}
    assert {family.canonical, *family.variants} <= emitted
    planted = next(f for f in built.truth.typo_families if f.family_id == family.id)
    assert set(planted.emitted) == set(family.variants)
    assert planted.within_rules_reach == family.within_rules_reach


def test_the_out_of_reach_spellings_sit_exactly_where_the_plan_puts_them(built: Build) -> None:
    where = {row.component_ref: (row.variant_id, row.true.sub_assembly) for row in built.dataset.bom if row.component_ref in OUT_OF_REACH}
    assert set(where) == OUT_OF_REACH
    assert where["SEAT-FIX-KIT-447"] == (built.model.newest, catalogue.PANELS)
    variant, sub_assembly = where["BGI-2013"]
    assert variant != built.model.newest and sub_assembly not in catalogue.STORY_SUB_ASSEMBLIES
    in_newest = [r for r in built.dataset.bom if r.variant_id == built.model.newest and r.component_ref in OUT_OF_REACH]
    assert len(in_newest) == 1, "the newest variant is allowed exactly one out-of-reach spelling"


@pytest.mark.parametrize("pair", PAIRS, ids=[pair.id for pair in PAIRS])
def test_both_sides_of_a_must_not_merge_pair_are_emitted_under_their_reserved_ids(built: Build, pair: MustNotMergePair) -> None:
    owner = {raw: c.true_component_id for c in built.truth.components for raw in c.raw_references}
    assert owner[pair.left_reference] == pair.left_true_component
    assert owner[pair.right_reference] == pair.right_true_component
    for reference in (pair.left_reference, pair.right_reference):
        spellings = {row.component_ref for row in built.dataset.bom if row.true.reference == reference}
        assert spellings == {reference}, "no typo is ever applied to a must-not-merge reference"
    assert pair.id in {declared.id for declared in built.truth.must_not_merge}


def test_generated_typos_are_planted_on_every_planned_component(built: Build) -> None:
    for plan in catalogue.TYPO_PLANS:
        spellings = {row.component_ref for row in built.dataset.bom if row.true.reference == plan.reference}
        assert len(spellings) >= 2 and plan.reference in spellings, plan.reference
    lighting = [r for r in built.dataset.bom if r.variant_id == built.model.newest and r.true.sub_assembly == catalogue.LIGHTING]
    assert sum(row.component_ref != row.true.reference for row in lighting) >= 2


# --- defects ---------------------------------------------------------------------------------


def test_every_defect_category_is_planted_and_recorded(built: Build) -> None:
    recorded = Counter(defect.defect_type for defect in built.truth.defects)
    assert set(recorded) == {"duplicate_reference", "unit_conflict", "supplier_conflict", "cost_conflict", "note_contradiction"}


def test_a_duplicate_reference_record_means_two_spellings_really_exist(built: Build) -> None:
    spellings: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in built.dataset.bom:
        spellings[(row.true.true_id, row.variant_id)].add(row.component_ref)
    for defect in built.truth.defects:
        if defect.defect_type == "duplicate_reference":
            first, second = defect.variant_pair
            assert len(spellings[(defect.true_component_id, first)] | spellings[(defect.true_component_id, second)]) > 1


def test_the_deviating_unit_lines_stay_out_of_the_newest_variant_and_of_the_story(built: Build) -> None:
    deviating = [row for row in built.dataset.bom if row.dimension != row.true.base_unit]
    assert len(deviating) == len(catalogue.UNIT_CONFLICTS)
    for row in deviating:
        assert row.variant_id != built.model.newest
        assert row.true.sub_assembly not in catalogue.STORY_SUB_ASSEMBLIES
    conflicted = {d.true_component_id for d in built.truth.defects if d.defect_type == "unit_conflict"}
    assert conflicted == {row.true.true_id for row in deviating}


def test_outside_the_planted_conflicts_a_component_costs_and_comes_from_the_same_everywhere(built: Build) -> None:
    costly = {built.model.parts[o.reference].true_id for o in catalogue.COST_OVERRIDES}
    sourced = {built.model.parts[o.reference].true_id for o in catalogue.SUPPLIER_OVERRIDES}
    costs: dict[str, set[float]] = defaultdict(set)
    suppliers: dict[str, set[str]] = defaultdict(set)
    for line in built.model.lines:
        costs[line.true_id].add(line.unit_cost)
        suppliers[line.true_id].add(line.supplier)
    assert {true_id for true_id, seen in costs.items() if len(seen) > 1} == costly
    assert {true_id for true_id, seen in suppliers.items() if len(seen) > 1} == sourced
    assert {d.true_component_id for d in built.truth.defects if d.defect_type == "cost_conflict"} == costly
    assert {d.true_component_id for d in built.truth.defects if d.defect_type == "supplier_conflict"} == sourced


def test_every_defect_cites_lines_that_carry_its_component_in_its_variants(built: Build) -> None:
    rows = {row.line_id: row for row in built.dataset.bom}
    for defect in built.truth.defects:
        assert defect.evidence_line_ids, defect.key
        for line_id in defect.evidence_line_ids:
            assert rows[line_id].true.true_id == defect.true_component_id
            assert rows[line_id].variant_id in defect.variant_pair


# --- the dirt that is only noise ---------------------------------------------------------------


def test_mixed_units_decimal_commas_and_count_spellings_all_occur(built: Build) -> None:
    units = {row.unit for row in built.dataset.bom}
    assert {"pcs", "units", "u", "m", "mm", "kg", "g"} <= units
    assert any("," in row.quantity for row in built.dataset.bom)
    assert any("," in row.unit_cost_eur for row in built.dataset.bom) and any("." in row.unit_cost_eur for row in built.dataset.bom)


def test_supplier_names_carry_case_and_space_noise_but_stay_the_same_name(built: Build) -> None:
    assert any(row.supplier != row.true.supplier for row in built.dataset.bom)
    for row in built.dataset.bom:
        assert row.supplier.strip().casefold() == row.true.supplier.casefold()


# --- volume ------------------------------------------------------------------------------------


def test_the_dataset_has_the_size_the_brief_asks_for(built: Build) -> None:
    per_variant = Counter(row.variant_id for row in built.dataset.bom)
    assert all(100 <= n <= 250 for n in per_variant.values()), per_variant
    assert 500 <= sum(per_variant.values()) <= 1500
    assert 4 <= len(per_variant) <= 6
    line_ids = [row.line_id for row in built.dataset.bom]
    assert line_ids == [f"L{i:05d}" for i in range(1, len(line_ids) + 1)]


def test_the_notes_come_in_three_languages_and_many_state_nothing(built: Build) -> None:
    assert 35 <= len(built.truth.notes) <= 45
    assert {note.language for note in built.truth.notes} == {"fr", "en", "mixed"}
    assert sum(not note.facts for note in built.truth.notes) >= 8


@pytest.mark.parametrize("pattern", ["remplacé par", "obsolete since", "do not use on", "ne pas utiliser sur"])
@pytest.mark.parametrize("seed", [DEFAULT_SEED, 1, 2, 3])
def test_the_wordings_the_brief_quotes_appear_literally(seed: int, pattern: str) -> None:
    dataset = render(build_true_model(SPEC), SPEC, seed)
    assert any(pattern in note.text for note in dataset.notes)


def test_some_notes_cite_a_part_by_a_dirty_spelling_and_the_mapping_knows_it(built: Build) -> None:
    owner = {raw: c.true_component_id for c in built.truth.components for raw in c.raw_references}
    dirty = [n for n in built.dataset.notes if n.script.fact and n.script.fact.cited_as]
    assert dirty
    for note in dirty:
        assert note.cited_reference in note.text
        assert owner[note.cited_reference] == built.model.parts[note.script.fact.reference].true_id


def test_about_half_of_the_stated_facts_are_respected_by_the_bom(built: Build) -> None:
    """Precision on note contradictions needs negatives."""
    stating = {note.note_id for note in built.truth.notes if note.facts}
    contradicted = {d.note_id for d in built.truth.defects if d.defect_type == "note_contradiction"}
    assert contradicted < stating
    assert 0.3 <= len(contradicted) / len(stating) <= 0.7


# --- the backtest ------------------------------------------------------------------------------


def test_every_sub_assembly_of_the_newest_variant_is_labelled_under_its_raw_reference(built: Build) -> None:
    emitted = {row.sub_assembly_ref for row in built.dataset.bom if row.variant_id == built.model.newest}
    assert {label.sub_assembly_ref for label in built.truth.backtest} == emitted
    older = {(row.variant_id, row.sub_assembly_ref) for row in built.dataset.bom if row.variant_id != built.model.newest}
    for label in built.truth.backtest:
        assert {(a.variant_id, a.sub_assembly_ref) for a in label.ancestors} <= older


def test_the_two_planted_unsafe_reuses_are_flagged_on_the_label_and_recorded_as_defects(built: Build) -> None:
    unsafe = {label.sub_assembly_designation: label.unsafe for label in built.truth.backtest if label.unsafe}
    assert set(unsafe) == {catalogue.AUX, catalogue.BIKE}
    contradictions = {(d.true_component_id, d.note_id) for d in built.truth.defects if d.defect_type == "note_contradiction"}
    for parts in unsafe.values():
        for part in parts:
            assert (part.true_component_id, part.note_id) in contradictions
    labels = {label.sub_assembly_designation: label.label for label in built.truth.backtest}
    assert (labels[catalogue.AUX], labels[catalogue.BIKE]) == ("reused", "reusable")


def test_the_seed_moves_the_dirt_never_the_story() -> None:
    """DECISIONS.md 17: fixed story cases. Any seed yields the same labels, ancestors and diffs."""
    first, second = build(1), build(2)
    assert [row.raw() for row in first.dataset.bom] != [row.raw() for row in second.dataset.bom]
    assert first.truth.backtest == second.truth.backtest
    assert first.truth.must_not_merge == second.truth.must_not_merge
    assert [n.facts for n in first.truth.notes] == [n.facts for n in second.truth.notes]
    assert first.model == second.model


@pytest.mark.parametrize("seed", range(1, 26))
def test_any_seed_yields_a_dataset_that_holds_together(seed: int) -> None:
    """A generated spelling colliding with another component's reference would raise here."""
    assert build(seed).truth.seed == seed


@pytest.mark.parametrize("seed", [DEFAULT_SEED, *range(1, 26)])
def test_every_reused_label_keeps_an_ancestor_whose_raw_lines_say_what_the_truth_says(seed: int) -> None:
    """Ancestors are equal in true content; a unit conflict or an out-of-reach spelling makes one
    of them differ in the raw files. The evaluation accepts any listed ancestor — which is only
    fair while one of them, at least, can honestly be seen as identical."""
    built = build(seed)
    dirty = {
        (row.variant_id, row.sub_assembly_ref)
        for row in built.dataset.bom
        if row.dimension != row.true.base_unit or row.component_ref in OUT_OF_REACH
    }
    for label in built.truth.backtest:
        if label.label == "reused":
            clean = [a for a in label.ancestors if (a.variant_id, a.sub_assembly_ref) not in dirty]
            assert clean, f"{label.sub_assembly_designation}: every listed ancestor carries a unit conflict or an out-of-reach spelling"


# --- what stops the generation -----------------------------------------------------------------


def test_a_string_standing_for_two_components_stops_the_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    colliding = NoteScript(
        "B",
        "2023-05-09",
        "fr",
        fact=FactScript("replacement", "BIKE-STRAP", cited_as="BIKE-HOOK", replaced_by="BIKE-STRAP-V2", effective_date="2023-05-01"),
    )
    monkeypatch.setattr(catalogue, "NOTES", (*catalogue.NOTES, colliding))
    with pytest.raises(GenerationError, match="stands for both"):
        build(DEFAULT_SEED)


def test_a_sub_assembly_below_the_minimum_size_stops_the_generation() -> None:
    demanding = replace(SPEC, dataset=DatasetRules(min_subassembly_size=5, default_unit="pcs"))
    with pytest.raises(GenerationError, match="below dataset.min_subassembly_size"):
        build_true_model(demanding)


def test_a_spelling_with_nowhere_to_go_stops_the_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalogue, "FORCED_SPELLINGS", {"SEAT-FIX-KIT-447": ("C", catalogue.BIKE)})
    with pytest.raises(GenerationError, match="no line left"):
        build(DEFAULT_SEED)


def test_a_note_about_a_part_the_master_does_not_hold_stops_the_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    stray = NoteScript("A", "2020-01-06", "en", fact=FactScript("obsolescence", "NOT-IN-MASTER", effective_date="2020-01-01"))
    monkeypatch.setattr(catalogue, "NOTES", (*catalogue.NOTES, stray))
    with pytest.raises(GenerationError, match="NOT-IN-MASTER"):
        build_true_model(SPEC)


def test_generate_itself_refuses_a_ground_truth_inside_the_raw_directory(tmp_path: Path) -> None:
    """docs/ARCHITECTURE.md A5: the guard belongs to the function, not to one of its callers."""
    raw = tmp_path / "raw"
    with pytest.raises(OutputPathError, match="must not be written inside"):
        generate(SPEC, DEFAULT_SEED, raw, raw / "nested" / "gt.json")
    assert not raw.exists(), "nothing may be written when the request is refused"
