"""The catalogue covers the contract, and has the structure the backtest story needs.

These tests run before any dirt exists: a missing or misplaced entry in ~170 hand-written
components and 40 note scripts must fail here, in seconds, and not as a strange score later.
"""

from collections import Counter

import pytest

from bomreuse import catalogue
from bomreuse.catalogue import FromStory
from bomreuse.dirt import BASE_UNITS, can_apply
from bomreuse.spec import DatasetSpec, StoryCase, load_spec

SPEC: DatasetSpec = load_spec()
CONTENTS = catalogue.contents(SPEC)
COMPONENTS = {component.reference: component for component in catalogue.COMPONENTS}
VARIANTS = {variant.id: variant for variant in catalogue.VARIANTS}
NEWEST = max(catalogue.VARIANTS, key=lambda variant: variant.design_date).id
CASES: tuple[StoryCase, ...] = SPEC.story_cases


def carriers(reference: str) -> set[tuple[str, str]]:
    return {key for key, counts in CONTENTS.items() if reference in counts}


# --- the component master ------------------------------------------------------------------


def test_a_reference_is_declared_once() -> None:
    duplicated = [reference for reference, n in Counter(c.reference for c in catalogue.COMPONENTS).items() if n > 1]
    assert not duplicated


def test_every_component_is_measured_in_a_base_unit_and_costs_something() -> None:
    for component in catalogue.COMPONENTS:
        assert component.base_unit in BASE_UNITS, component.reference
        assert component.unit_cost > 0, component.reference


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_every_story_component_is_in_the_master_with_the_unit_the_spec_gives_it(case: StoryCase) -> None:
    for reference in {*case.left, *case.right}:
        assert reference in COMPONENTS, f"{case.id}: {reference} has no ComponentDef"
        expected = case.units.get(reference, SPEC.dataset.default_unit)
        assert COMPONENTS[reference].base_unit == expected, f"{reference}: the spec says {expected}"


def test_every_reference_used_anywhere_is_in_the_master() -> None:
    used = {reference for counts in CONTENTS.values() for reference in counts}
    used |= {note.fact.reference for note in catalogue.NOTES if note.fact}
    used |= {note.fact.replaced_by for note in catalogue.NOTES if note.fact and note.fact.replaced_by}
    assert used <= COMPONENTS.keys(), sorted(used - COMPONENTS.keys())


def test_no_component_is_declared_and_never_used() -> None:
    used = {reference for counts in CONTENTS.values() for reference in counts}
    used |= {note.fact.replaced_by for note in catalogue.NOTES if note.fact and note.fact.replaced_by}
    assert COMPONENTS.keys() <= used, sorted(COMPONENTS.keys() - used)


# --- variants and sub-assemblies -----------------------------------------------------------


def test_the_newest_variant_is_c_by_its_date_not_by_its_letter() -> None:
    assert NEWEST == "C"
    assert 4 <= len(catalogue.VARIANTS) <= 6


def test_seats_and_bike_spaces_follow_from_the_bill_of_materials() -> None:
    for variant in catalogue.VARIANTS:
        seating = CONTENTS[(variant.id, catalogue.SEATING)]
        assert variant.seats == 2 * seating["SEAT-FIX-DBL"], variant.id
        hooks = CONTENTS.get((variant.id, catalogue.BIKE), {}).get("BIKE-HOOK", 0)
        assert variant.bike_spaces == hooks, variant.id


def test_only_the_bike_cars_carry_a_bike_module() -> None:
    per_variant = Counter(variant_id for variant_id, _ in CONTENTS)
    assert per_variant == {"A": 14, "B": 15, "D": 14, "E": 14, "C": 15}
    assert {variant_id for variant_id, name in CONTENTS if name == catalogue.BIKE} == {"B", "C"}


def test_no_sub_assembly_is_below_the_minimum_size() -> None:
    minimum = SPEC.dataset.min_subassembly_size
    too_small = {key: len(counts) for key, counts in CONTENTS.items() if len(counts) < minimum}
    assert not too_small


def test_a_variant_never_uses_a_sub_assembly_reference_twice() -> None:
    for variant in catalogue.VARIANTS:
        references = [d.reference for d in catalogue.SUB_ASSEMBLIES if d.variant_id == variant.id]
        assert len(set(references)) == len(references), variant.id


def test_among_the_older_variants_one_reference_means_one_content() -> None:
    """An ancestor is named by `(variant, reference)`; the same reference must not hide two contents."""
    by_reference: dict[str, dict[str, float]] = {}
    for definition in catalogue.SUB_ASSEMBLIES:
        if definition.variant_id == NEWEST:
            continue
        content = CONTENTS[(definition.variant_id, definition.name)]
        assert by_reference.setdefault(definition.reference, content) == content, definition.reference


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_every_story_case_is_carried_on_both_sides_at_the_variants_the_spec_names(case: StoryCase) -> None:
    sources = {
        (d.variant_id, d.content.side)
        for d in catalogue.SUB_ASSEMBLIES
        if isinstance(d.content, FromStory) and d.content.case_id == case.id and d.name == case.sub_assembly
    }
    assert sources == {(case.left_variant, "left"), (case.right_variant, "right")}
    assert case.sub_assembly in catalogue.STORY_SUB_ASSEMBLIES


# --- the declared answers ------------------------------------------------------------------


def test_every_sub_assembly_of_the_newest_variant_has_one_declared_answer() -> None:
    declared = [label.name for label in catalogue.LABELS]
    assert sorted(declared) == sorted(name for variant_id, name in CONTENTS if variant_id == NEWEST)


def test_the_newest_variant_holds_the_planned_mix() -> None:
    mix = Counter(label.planted_as for label in catalogue.LABELS)
    assert mix == {"open_reuse": 4, "hidden_reuse": 5, "near_reuse": 3, "ref_reused_content_changed": 1, "new": 2}


def test_open_reuse_keeps_the_reference_and_hidden_reuse_does_not() -> None:
    older = {d.reference for d in catalogue.SUB_ASSEMBLIES if d.variant_id != NEWEST}
    newest = {d.name: d.reference for d in catalogue.SUB_ASSEMBLIES if d.variant_id == NEWEST}
    for label in catalogue.LABELS:
        if label.planted_as in ("open_reuse", "ref_reused_content_changed"):
            assert newest[label.name] in older, label.name
        else:
            assert newest[label.name] not in older, label.name


def test_only_reusable_answers_declare_their_ancestors() -> None:
    for label in catalogue.LABELS:
        assert bool(label.reusable_from) == (label.label == "reusable"), label.name
        assert NEWEST not in label.reusable_from


# --- planted conflicts and spellings -------------------------------------------------------


def test_planted_components_live_outside_the_story_sub_assemblies() -> None:
    planted = {family.canonical for family in SPEC.typo_families}
    planted |= {ref for pair in SPEC.must_not_merge for ref in (pair.left_reference, pair.right_reference)}
    for reference in planted:
        names = {name for _, name in carriers(reference)}
        assert names, f"{reference} is carried nowhere"
        assert not names & catalogue.STORY_SUB_ASSEMBLIES, reference


def test_the_two_members_of_a_must_not_merge_pair_never_share_a_sub_assembly() -> None:
    """A false merge by #4 must cost precision, not crash `Signature` on a duplicate component."""
    for pair in SPEC.must_not_merge:
        left, right = carriers(pair.left_reference), carriers(pair.right_reference)
        assert not {name for _, name in left} & {name for _, name in right}, pair.id
        assert len({variant for variant, _ in left}) >= 2 and len({variant for variant, _ in right}) >= 2


def test_the_generic_bolt_has_room_for_every_spelling_the_spec_declares() -> None:
    spellings = {s for family in SPEC.typo_families if family.canonical == "BGI-2031" for s in family.variants}
    assert len(carriers("BGI-2031")) >= len(spellings) + 2
    assert len({name for _, name in carriers("BGI-2031")}) >= 3


def test_forced_spellings_are_spec_spellings_placed_where_their_component_is() -> None:
    family_of = {s: family for family in SPEC.typo_families for s in family.variants}
    for spelling, place in catalogue.FORCED_SPELLINGS.items():
        assert place in carriers(family_of[spelling].canonical), spelling


def test_unit_conflicts_avoid_the_newest_variant_and_the_story() -> None:
    assert 2 <= len(catalogue.UNIT_CONFLICTS) <= 3
    for conflict in catalogue.UNIT_CONFLICTS:
        assert conflict.variant_id != NEWEST
        assert conflict.sub_assembly not in catalogue.STORY_SUB_ASSEMBLIES
        assert (conflict.variant_id, conflict.sub_assembly) in carriers(conflict.reference)
        assert conflict.raw_unit != COMPONENTS[conflict.reference].base_unit


def test_supplier_and_cost_overrides_are_real_blunt_and_disjoint() -> None:
    assert 4 <= len(catalogue.SUPPLIER_OVERRIDES) <= 6 and 4 <= len(catalogue.COST_OVERRIDES) <= 6
    for supplier in catalogue.SUPPLIER_OVERRIDES:
        assert supplier.supplier != COMPONENTS[supplier.reference].supplier
        assert supplier.variant_id in {variant for variant, _ in carriers(supplier.reference)}
    for cost in catalogue.COST_OVERRIDES:
        assert cost.unit_cost >= 1.15 * COMPONENTS[cost.reference].unit_cost, cost.reference
        assert cost.variant_id in {variant for variant, _ in carriers(cost.reference)}
    assert not {s.reference for s in catalogue.SUPPLIER_OVERRIDES} & {c.reference for c in catalogue.COST_OVERRIDES}


def test_typo_plans_can_be_applied_and_leave_the_spec_components_alone() -> None:
    reserved = {family.canonical for family in SPEC.typo_families}
    reserved |= {ref for pair in SPEC.must_not_merge for ref in (pair.left_reference, pair.right_reference)}
    assert 10 <= len(catalogue.TYPO_PLANS) <= 14
    for plan in catalogue.TYPO_PLANS:
        assert plan.reference not in reserved, plan.reference
        assert can_apply(plan.reference, plan.kind), plan
        assert set(plan.places) <= carriers(plan.reference), plan
    assert sum(("C", catalogue.LIGHTING) in plan.places for plan in catalogue.TYPO_PLANS) >= 2


# --- notes ---------------------------------------------------------------------------------


def test_the_notes_have_the_planned_mix() -> None:
    assert 35 <= len(catalogue.NOTES) <= 45
    kinds = Counter(note.fact.fact_type if note.fact else "none" for note in catalogue.NOTES)
    assert kinds == {"replacement": 12, "obsolescence": 8, "restriction": 8, "none": 12}
    languages = Counter(note.language for note in catalogue.NOTES)
    assert languages["fr"] > languages["en"] > languages["mixed"] >= 6


def test_a_note_states_a_fact_or_carries_a_text_and_is_filed_after_its_variant_was_designed() -> None:
    for note in catalogue.NOTES:
        assert note.fact is not None or note.text is not None, note
        assert note.date >= VARIANTS[note.variant_id].design_date, note


STOCK_PHRASES = (
    "remplacé par", "à la place de", "replaced by", "instead of", "superseded by",
    "obsolète", "obsolete", "ne pas utiliser", "ne pas monter", "interdit", "do not use", "do not fit", "not approved",
)  # fmt: skip


def test_some_notes_state_nothing_while_citing_a_part_next_to_a_stock_phrase() -> None:
    """The trap for a keyword reader: a replacement turned down, an obsolescence rejected, an open question."""
    references = {component.reference for component in catalogue.COMPONENTS}
    traps = [
        note
        for note in catalogue.NOTES
        if note.fact is None
        and any(reference in note.text for reference in references)
        and any(phrase in note.text.lower() for phrase in ("remplacé par", "replaced by", "obsolete"))
    ]
    assert len(traps) >= 3


def test_a_fact_in_its_own_words_cites_the_part_and_uses_no_stock_phrase() -> None:
    own = [note for note in catalogue.NOTES if note.fact is not None and note.text is not None]
    assert len(own) >= 2
    for note in own:
        assert "{ref}" in note.text, note
        assert ("{new}" in note.text) == (note.fact.fact_type == "replacement"), note
        assert not any(phrase in note.text.lower() for phrase in STOCK_PHRASES), note


def test_every_fact_is_complete_for_its_type() -> None:
    for note in catalogue.NOTES:
        fact = note.fact
        if fact is None:
            continue
        assert (fact.replaced_by is not None) == (fact.fact_type == "replacement"), fact
        assert (fact.effective_date is not None) == (fact.fact_type != "restriction"), fact
        assert (fact.scope is not None) == (fact.fact_type == "restriction"), fact
        if fact.scope is not None:
            assert fact.scope in catalogue.SCOPES and fact.scope in catalogue.SCOPE_WORDING


def test_every_kind_of_note_has_wording_in_every_language() -> None:
    for fact_type in ("replacement", "obsolescence", "restriction"):
        for language in ("fr", "en", "mixed"):
            assert catalogue.NOTE_TEMPLATES[(fact_type, language)]


def test_a_group_of_notes_is_never_smaller_than_its_stock_of_wordings() -> None:
    """Wordings are dealt in turn, so this is what guarantees every one of them is used."""
    groups = Counter((note.fact.fact_type, note.language) for note in catalogue.NOTES if note.fact and note.text is None)
    for group, templates in catalogue.NOTE_TEMPLATES.items():
        assert groups[group] >= len(templates), group


def test_the_scopes_say_what_the_variants_are() -> None:
    assert set(catalogue.SCOPES["bike_car"]) == {v.id for v in catalogue.VARIANTS if v.bike_spaces > 0}
    assert set(catalogue.SCOPES["bi_mode"]) == {v.id for v in catalogue.VARIANTS if v.traction == "bi-mode"}
    assert set(catalogue.SCOPES["standard_car"]) == {v.id for v in catalogue.VARIANTS if v.bike_spaces == 0}
    assert set(catalogue.SCOPES["electric"]) == {v.id for v in catalogue.VARIANTS if v.traction == "electric"}


def test_notes_read_like_a_log_in_date_order_and_never_announce_the_past_as_future() -> None:
    """"Obsolete since 2026-02-01" in a note dated 2025 reads wrong: a dated fact is filed once it is effective."""
    for variant in catalogue.VARIANTS:
        dates = [note.date for note in catalogue.NOTES if note.variant_id == variant.id]
        assert dates == sorted(dates), variant.id
    for note in catalogue.NOTES:
        if note.fact and note.fact.effective_date:
            assert note.date >= note.fact.effective_date, note
