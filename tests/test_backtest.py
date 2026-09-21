"""The backtest: the newest variant played as a new tender, against the variants before it.

This is the answer to the client's question, so the tests are written against it from both
sides: the committed dataset, where CONTEXT.md's worked example says what should come out, and
hand-written rows, where the chronology and the ancestors can be controlled.

`signatures.py` carries one verdict rule, the one issue #1 wrote and DECISIONS.md 17 froze. Two
tests keep it that way: the backtest is shown to go through `compare`, and the module is read to
check no second place decides a verdict.
"""

import ast
from pathlib import Path

import pytest

from bomreuse import signatures as signatures_module
from bomreuse.ingest import read_raw
from bomreuse.model import Backtest, Prediction, ReuseClass, SubAssemblySignature
from bomreuse.normalize import normalize, reference_key
from bomreuse.resolve import resolve
from bomreuse.signatures import Comparison, Verdict, backtest, build_signatures, compare, newest_variant
from bomreuse.spec import load_spec
from test_signature_build import DESIGN_DATES, Row, dataset_of

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"
SPEC = load_spec()


def ran(rows: list[Row], dates: dict[str, str] | None = None) -> Backtest:
    dataset = dataset_of(rows, dates or DESIGN_DATES)
    resolution, _ = resolve(dataset)
    return backtest(build_signatures(dataset, resolution), dataset.variants, SPEC.thresholds)


def sub_assembly(variant: str, reference: str, *components: tuple[str, str]) -> list[Row]:
    return [Row(variant, reference, component, designation) for component, designation in components]


#: Four components, so the budget is not the degenerate one docs/ARCHITECTURE.md A1 warns about.
SHELL = (("SHELL-UNDERFRAME", "Underframe"), ("SHELL-SIDEWALL", "Sidewall panel"), ("SHELL-ROOF", "Roof assembly"), ("SHELL-ENDWALL", "Endwall frame"))


@pytest.fixture(scope="module")
def committed() -> Backtest:
    dataset = normalize(read_raw(COMMITTED_RAW))
    resolution, _ = resolve(dataset)
    return backtest(build_signatures(dataset, resolution), dataset.variants, SPEC.thresholds)


def predictions_by_id(result: Backtest) -> dict[str, Prediction]:
    return {prediction.sub_assembly_id: prediction for prediction in result.predictions}


# --- which variant plays the new tender, and which ones it is compared with ----------------------


def test_the_newest_variant_is_the_one_designed_last() -> None:
    dataset = dataset_of(sub_assembly("A", "SA-0101", *SHELL) + sub_assembly("C", "OCC-SA-0101", *SHELL))
    newest = newest_variant(dataset.variants)
    assert newest is not None and newest.id == "C"


def test_the_backtest_is_run_on_the_newest_variant_against_the_older_ones(committed: Backtest) -> None:
    assert committed.target_variant_id == "C"
    assert committed.ancestor_variant_ids == ("A", "B", "D", "E")
    assert {prediction.variant_id for prediction in committed.predictions} == {"C"}


def test_the_newest_variant_is_never_its_own_ancestor(committed: Backtest) -> None:
    """Given only the older variants: a sub-assembly compared with itself answers *reused* always."""
    assert committed.target_variant_id not in committed.ancestor_variant_ids
    named = {prediction.ancestor_id for prediction in committed.predictions} - {""}
    assert named
    assert not [ancestor for ancestor in named if ancestor.startswith(f"{committed.target_variant_id}:")]


def test_a_sub_assembly_the_newest_variant_repeats_is_not_reused_from_itself() -> None:
    """The same content twice inside the newest variant, and nothing older: the answer is *specific*."""
    result = ran(sub_assembly("C", "OCC-SA-0101", *SHELL) + sub_assembly("C", "OCC-SA-0201", *SHELL))
    assert result.ancestor_variant_ids == ()
    assert {prediction.reuse_class for prediction in result.predictions} == {ReuseClass.SPECIFIC}


def test_a_variant_whose_design_date_cannot_be_read_is_not_an_ancestor() -> None:
    """It cannot be placed in the chronology, so naming it would claim a knowledge of the order."""
    rows = sub_assembly("A", "SA-0101", *SHELL) + sub_assembly("B", "SA-0101", *SHELL) + sub_assembly("C", "OCC-SA-0101", *SHELL)
    result = ran(rows, {**DESIGN_DATES, "B": "not a date"})
    assert result.ancestor_variant_ids == ("A",)
    assert predictions_by_id(result)["C:0CCSA0101"].ancestor_id == "A:SA0101"


def test_no_readable_design_date_anywhere_means_no_backtest_rather_than_a_guess() -> None:
    dates = {variant: "" for variant in DESIGN_DATES}
    assert ran(sub_assembly("A", "SA-0101", *SHELL) + sub_assembly("C", "OCC-SA-0101", *SHELL), dates) == Backtest("", (), ())


# --- what each class promises --------------------------------------------------------------------


def test_a_reused_prediction_names_an_ancestor_whose_signature_is_identical(committed: Backtest) -> None:
    dataset = normalize(read_raw(COMMITTED_RAW))
    resolution, _ = resolve(dataset)
    by_id = {built.sub_assembly_id: built.signature for built in build_signatures(dataset, resolution)}

    reused = [prediction for prediction in committed.predictions if prediction.reuse_class is ReuseClass.REUSED]
    assert reused, "a backtest finding no reuse at all could not show what a reused answer promises"
    for prediction in reused:
        assert prediction.diff is None
        assert by_id[prediction.ancestor_id] == by_id[prediction.sub_assembly_id]


def test_a_reusable_prediction_carries_a_non_empty_diff_and_the_ancestor_it_is_read_against(committed: Backtest) -> None:
    reusable = [prediction for prediction in committed.predictions if prediction.reuse_class is ReuseClass.REUSABLE]
    assert reusable
    for prediction in reusable:
        assert prediction.ancestor_id
        assert prediction.diff is not None and not prediction.diff.is_empty()


def test_a_specific_prediction_names_no_ancestor_and_no_diff(committed: Backtest) -> None:
    specific = [prediction for prediction in committed.predictions if prediction.reuse_class is ReuseClass.SPECIFIC]
    assert specific, "without a genuinely new sub-assembly the other two classes mean nothing"
    for prediction in specific:
        assert prediction.ancestor_id == ""
        assert prediction.diff is None


def test_a_sub_assembly_nothing_could_be_read_of_is_specific_rather_than_reused() -> None:
    """Two signatures the pipeline could read nothing into have an empty diff, and an empty diff
    is how `compare` says *identical*. Absence of readable evidence is not evidence of identity,
    and a false *reused* is the worst answer this tool can give (`resolve.py`).
    """
    rows = [Row("A", "SA-0999", "MYST-PART-A", "Mystery part A", "abc"), Row("C", "OCC-SA-0998", "MYST-PART-B", "Mystery part B", "xyz")]
    prediction = predictions_by_id(ran(rows))["C:0CCSA0998"]
    assert prediction.reuse_class is ReuseClass.SPECIFIC
    assert prediction.ancestor_id == "" and prediction.diff is None


def test_the_diff_says_what_the_newest_variant_adds_to_the_ancestor_not_the_other_way_round() -> None:
    """The direction *is* the deliverable: read the wrong way round, the table tells the client
    to remove the part they have to add. The verdict is symmetric, so nothing but the evidence
    would move if the two signatures were swapped at the call site.
    """
    hook = ("SHELL-BIKE-HOOK", "Bike hook")
    prediction = predictions_by_id(ran(sub_assembly("A", "SA-0101", *SHELL) + sub_assembly("C", "OCC-SA-0101", *SHELL, hook)))["C:0CCSA0101"]
    assert prediction.reuse_class is ReuseClass.REUSABLE
    assert prediction.diff is not None
    assert [item.component for item in prediction.diff.added] == [reference_key("SHELL-BIKE-HOOK")]
    assert prediction.diff.removed == ()


def test_every_sub_assembly_of_the_newest_variant_gets_exactly_one_answer(committed: Backtest) -> None:
    dataset = normalize(read_raw(COMMITTED_RAW))
    target = [sub_assembly.id for sub_assembly in dataset.sub_assemblies if sub_assembly.variant_id == committed.target_variant_id]
    assert [prediction.sub_assembly_id for prediction in committed.predictions] == target


# --- the worked example of CONTEXT.md --------------------------------------------------------------


def test_the_committed_dataset_answers_the_question_the_worked_example_asks(committed: Backtest) -> None:
    """Most of the car reused from A and B, the bike module reusable from B, the anchorage new.

    Written against CONTEXT.md's table rather than against a count, so the test says what the
    tool should find and not what it happens to score.
    """
    predictions = predictions_by_id(committed)
    assert predictions["C:SA0101"].reuse_class is ReuseClass.REUSED  # carbody shell
    assert predictions["C:SA0101"].ancestor_id == "A:SA0101"
    assert predictions["C:0CCSA0315"].reuse_class is ReuseClass.REUSABLE  # bike module
    assert predictions["C:0CCSA0315"].ancestor_id.startswith("B:")
    assert predictions["C:0CCSA0314"].reuse_class is ReuseClass.SPECIFIC  # floor and wall anchorage
    assert predictions["C:SA0213"].reuse_class is ReuseClass.REUSABLE  # seating module: same seat, different count


def test_the_hidden_reuse_a_new_reference_would_hide_is_found() -> None:
    """The newest variant re-emits an older sub-assembly under its own references: still *reused*."""
    older = sub_assembly("A", "SA-0101", *SHELL)
    newest = [Row("C", "OCC-SA-0101", reference.lower(), designation) for reference, designation in SHELL]
    predictions = predictions_by_id(ran(older + newest))
    assert predictions["C:0CCSA0101"].reuse_class is ReuseClass.REUSED
    assert predictions["C:0CCSA0101"].ancestor_id == "A:SA0101"


# --- one verdict rule, and the answer does not move with the input order -----------------------------


def test_the_answer_does_not_move_with_the_order_the_ancestors_arrive_in(committed: Backtest) -> None:
    """Several ancestors usually reach the same verdict; which one is named must not be luck."""
    dataset = normalize(read_raw(COMMITTED_RAW))
    resolution, _ = resolve(dataset)
    built = build_signatures(dataset, resolution)
    shuffled = backtest(tuple(reversed(built)), dataset.variants, SPEC.thresholds)
    assert predictions_by_id(shuffled) == predictions_by_id(committed)


def test_the_backtest_classifies_through_the_verdict_function_of_issue_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not a second copy of the A1 rule: the comparison the story cases are checked against."""
    calls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def spy(left: object, right: object, thresholds: object) -> Comparison:
        assert isinstance(left, signatures_module.Signature) and isinstance(right, signatures_module.Signature)
        calls.append((tuple(item.component for item in left.items), tuple(item.component for item in right.items)))
        return compare(left, right, thresholds)  # type: ignore[arg-type]

    monkeypatch.setattr(signatures_module, "compare", spy)
    # The two sides differ, so the assertion below fails if they are ever passed the other way round.
    result = ran(sub_assembly("A", "SA-0101", *SHELL) + sub_assembly("C", "OCC-SA-0101", *SHELL, ("SHELL-BIKE-HOOK", "Bike hook")))

    assert len(calls) == 1, "one comparison per (ancestor, sub-assembly of the newest variant) pair"
    ancestor, target = calls[0]
    assert set(target) - set(ancestor) == {reference_key("SHELL-BIKE-HOOK")}, "the ancestor is compared on the left, the newest variant on the right"
    assert not set(ancestor) - set(target)
    assert predictions_by_id(result)["C:0CCSA0101"].reuse_class is ReuseClass.REUSABLE


def test_no_second_place_in_the_module_decides_a_verdict() -> None:
    """`Verdict` is named where the A1 rule is applied, and in the table that translates it.

    A copy of the rule written into the backtest would read a verdict member somewhere else, and
    would then be free to drift from the story cases `test_verdict_story_cases.py` checks.
    """
    source = Path(signatures_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for inner in ast.walk(node)
        if isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name) and inner.value.id == "Verdict"
    }
    assert functions == {"compare"}
