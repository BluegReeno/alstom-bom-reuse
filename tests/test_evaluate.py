"""The scorer: one relation, one function, three predictors treated alike.

These tests guard the only place where the tool's vocabulary and the ground truth's meet
(Decision 30). Two things matter more than the ratios themselves: the relation is **exhaustive**
over both enumerations, so a class added to either side breaks a test instead of drifting a
score; and it runs **one way**, so a match missed to a typo stays a miss and is never repaired
into a hit "for symmetry".

The fixtures are hand-written ground truths, because the point is what the scorer does with an
answer, not what the committed dataset happens to contain. The committed dataset is scored in
`test_cli_evaluate.py` and end to end in `test_e2e_backtest.py`.
"""

from pathlib import Path
from typing import get_args

import pytest

from bomreuse import baseline
from bomreuse.evaluate import ANSWERS, EvaluationError, Predictor, Ratio, Score, evaluate, score
from bomreuse.ground_truth import SCHEMA_VERSION, Ancestor, BacktestLabel, Diff, GroundTruth, Label, QuantityChange, dump_ground_truth
from bomreuse.ingest import read_raw
from bomreuse.model import Prediction, ReuseClass
from bomreuse.normalize import normalize
from bomreuse.resolve import resolve
from bomreuse.signatures import backtest, build_signatures
from bomreuse.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"
COMMITTED_GROUND_TRUTH = ROOT / "data" / "ground_truth" / "ground_truth.json"

#: One component, so a hand-written ground truth validates without a catalogue behind it.
COMPONENT = {"true_component_id": "TRUE-0001", "designation": "a part", "base_unit": "pcs", "raw_references": ("PART-1",)}


def truth_of(*items: BacktestLabel, newest_variant: str = "C") -> GroundTruth:
    return GroundTruth(
        schema_version=SCHEMA_VERSION,
        spec_version="1",
        seed=1,
        newest_variant=newest_variant,
        components=(COMPONENT,),
        typo_families=(),
        must_not_merge=(),
        backtest=items,
        defects=(),
        notes=(),
    )


def labelled(reference: str, label: Label, *ancestors: tuple[str, str]) -> BacktestLabel:
    """One backtest item. A `reusable` label carries a diff because its schema demands one."""
    diff = Diff(added=(), removed=(), quantity_changed=(QuantityChange(true_component_id="TRUE-0001", left=2.0, right=1.0, unit="pcs"),))
    return BacktestLabel(
        variant_id="C",
        sub_assembly_ref=reference,
        sub_assembly_designation="a sub-assembly",
        label=label,
        planted_as="new" if label == "new" else "open_reuse",
        story_case_id=None,
        ancestors=tuple(Ancestor(variant_id=variant, sub_assembly_ref=reference, diff=diff if label == "reusable" else None) for variant, reference in ancestors),
        unsafe=(),
    )


def predicted(reference: str, reuse_class: ReuseClass, ancestor: str = "") -> Prediction:
    return Prediction(sub_assembly_id=f"C:{reference}", variant_id="C", reuse_class=reuse_class, ancestor_id=ancestor, diff=None)


def scored(truth: GroundTruth, *predictions: Prediction) -> Score:
    """One hand-written answer, scored under the identity a baseline would build for it.

    The identity covers every sub-assembly the ground truth names — the items and their
    ancestors — because that is what `baseline.sub_assembly_ids` covers: every `(variant, raw
    reference)` pair the files carry.
    """
    named = {(item.variant_id, item.sub_assembly_ref) for item in truth.backtest}
    named |= {(ancestor.variant_id, ancestor.sub_assembly_ref) for item in truth.backtest for ancestor in item.ancestors}
    identity = {key: f"{key[0]}:{key[1]}" for key in named}
    return score(Predictor(name="fixture", description="a hand-written answer", predictions=predictions, identity=identity), truth)


def rows(result: Score) -> dict[Label, tuple[Ratio, Ratio]]:
    return {row.label: (row.precision, row.recall) for row in result.classes}


# --- the relation ---------------------------------------------------------------------------


def test_the_relation_is_exhaustive_over_both_vocabularies() -> None:
    """A class added to either side breaks this test rather than drifting a ratio in silence."""
    assert set(ANSWERS) == set(get_args(Label))
    assert set(ANSWERS.values()) == set(ReuseClass)
    assert len(ANSWERS) == len(ReuseClass), "one label, one answer: the table must not fold two labels onto one class"


def test_specific_is_the_answer_to_new_and_to_nothing_else() -> None:
    assert ANSWERS["new"] is ReuseClass.SPECIFIC
    assert "specific" not in get_args(Label), "the divergence is deliberate: neither side is renamed"


def test_specific_against_a_new_ground_truth_is_a_hit() -> None:
    result = scored(truth_of(labelled("OCC-SA-0310", "new")), predicted("OCC-SA-0310", ReuseClass.SPECIFIC))
    assert rows(result)["new"] == (Ratio(1, 1), Ratio(1, 1))
    assert result.correct == Ratio(1, 1)


def test_specific_against_a_reused_ground_truth_is_a_miss() -> None:
    """The relation runs one way: a match missed to a typo is a miss, not a symmetric hit."""
    result = scored(truth_of(labelled("SA-O107", "reused", ("A", "SA-0107"))), predicted("SA-O107", ReuseClass.SPECIFIC))
    assert rows(result)["reused"] == (Ratio(0, 0), Ratio(0, 1))
    assert rows(result)["new"] == (Ratio(0, 1), Ratio(0, 0)), "the wrong answer is still counted as claimed"
    assert result.correct == Ratio(0, 1)


@pytest.mark.parametrize("answered", [ReuseClass.REUSABLE, ReuseClass.SPECIFIC])
def test_only_the_one_answer_of_the_table_is_right(answered: ReuseClass) -> None:
    result = scored(truth_of(labelled("SA-0101", "reused", ("A", "SA-0101"))), predicted("SA-0101", answered, "A:SA-0101"))
    assert result.correct == Ratio(0, 1)


def test_an_item_the_predictor_says_nothing_about_is_a_miss() -> None:
    result = scored(truth_of(labelled("SA-0101", "reused", ("A", "SA-0101"))))
    assert rows(result)["reused"] == (Ratio(0, 0), Ratio(0, 1))
    assert result.correct == Ratio(0, 1)


# --- the ancestor rule (Decision 25) --------------------------------------------------------


def test_the_second_listed_ancestor_is_a_hit() -> None:
    """Listed ancestors are equal in true content; naming any one of them is enough to reuse from."""
    item = labelled("SA-0101", "reused", ("A", "SA-0101"), ("B", "SA-0102"))
    assert scored(truth_of(item), predicted("SA-0101", ReuseClass.REUSED, "B:SA-0102")).correct == Ratio(1, 1)


def test_an_ancestor_the_ground_truth_does_not_list_is_a_miss() -> None:
    item = labelled("SA-0101", "reused", ("A", "SA-0101"))
    result = scored(truth_of(item), predicted("SA-0101", ReuseClass.REUSED, "B:SA-0102"))
    assert rows(result)["reused"] == (Ratio(0, 1), Ratio(0, 1))


def test_the_ancestor_rule_applies_to_reusable_too() -> None:
    item = labelled("OCC-SA-0315", "reusable", ("A", "SA-0101"), ("B", "SA-0102"))
    assert scored(truth_of(item), predicted("OCC-SA-0315", ReuseClass.REUSABLE, "B:SA-0102")).correct == Ratio(1, 1)
    assert scored(truth_of(item), predicted("OCC-SA-0315", ReuseClass.REUSABLE, "A:SA-0999")).correct == Ratio(0, 1)


def test_a_new_label_lists_no_ancestor_so_the_class_alone_decides() -> None:
    result = scored(truth_of(labelled("OCC-SA-0314", "new")), predicted("OCC-SA-0314", ReuseClass.SPECIFIC, "A:SA-0101"))
    assert result.correct == Ratio(1, 1), "a `specific` prediction carries no ancestor to score anyway"


# --- the ratios -----------------------------------------------------------------------------


def test_precision_counts_what_was_claimed_and_recall_what_was_there() -> None:
    truth = truth_of(
        labelled("SA-0101", "reused", ("A", "SA-0101")),
        labelled("SA-0102", "reused", ("A", "SA-0102")),
        labelled("OCC-SA-0310", "new"),
    )
    result = scored(
        truth,
        predicted("SA-0101", ReuseClass.REUSED, "A:SA-0101"),
        predicted("SA-0102", ReuseClass.SPECIFIC),
        predicted("OCC-SA-0310", ReuseClass.REUSED, "A:SA-0101"),
    )
    assert rows(result)["reused"] == (Ratio(1, 2), Ratio(1, 2))
    assert rows(result)["new"] == (Ratio(0, 1), Ratio(0, 1))
    assert result.correct == Ratio(1, 3)


def test_every_ratio_carries_its_counts_and_never_a_float() -> None:
    assert str(Ratio(8, 9)) == "8/9"
    assert str(Ratio(0, 0)) == "0/0", "a predictor that claimed nothing says so; it does not divide by zero"
    assert not hasattr(Ratio(1, 2), "value"), "no float, no F1 (Decision 3)"


# --- one function, three predictors ---------------------------------------------------------


def test_one_scorer_treats_the_three_predictors_alike() -> None:
    """Same answers, different predictor: same score. Nothing in the scorer knows which is the tool."""
    truth = truth_of(labelled("SA-0101", "reused", ("A", "SA-0101")), labelled("OCC-SA-0310", "new"))
    answers = (predicted("SA-0101", ReuseClass.REUSED, "A:SA-0101"), predicted("OCC-SA-0310", ReuseClass.SPECIFIC))
    identity = {("C", "SA-0101"): "C:SA-0101", ("C", "OCC-SA-0310"): "C:OCC-SA-0310", ("A", "SA-0101"): "A:SA-0101"}
    results = [score(Predictor(name=name, description=name, predictions=answers, identity=identity), truth) for name in ("tool", "exact reference", "same name")]
    assert {result.predictor for result in results} == {"tool", "exact reference", "same name"}
    assert all(rows(result) == rows(results[0]) and result.correct == results[0].correct for result in results)


def test_one_function_scores_a_tool_shaped_answer_and_a_fixture_from_each_baseline() -> None:
    """Three fixtures of the three shapes, one `score`: what differs is the answer, not the treatment.

    The tool names folded ids and can say `reusable`; a baseline names raw strings and can only
    say `reused` or `specific`. Each is right about exactly one of the three items here, and each
    is right for a different reason — which is what the three rows of the output are for.
    """
    truth = truth_of(
        labelled("SA-O107", "reused", ("A", "SA-0107")),
        labelled("OCC-SA-0315", "reusable", ("B", "SA-0215")),
        labelled("OCC-SA-0314", "new"),
    )
    folded = {("C", "SA-O107"): "C:SA0107", ("C", "OCC-SA-0315"): "C:0CCSA0315", ("C", "OCC-SA-0314"): "C:0CCSA0314", ("A", "SA-0107"): "A:SA0107", ("B", "SA-0215"): "B:SA0215"}
    raw_strings = {key: f"{key[0]}:{key[1]}" for key in folded}

    tool = Predictor(
        name="tool",
        description="folded keys, and content compared",
        predictions=(
            Prediction(sub_assembly_id="C:SA0107", variant_id="C", reuse_class=ReuseClass.REUSED, ancestor_id="A:SA0107", diff=None),
            Prediction(sub_assembly_id="C:0CCSA0315", variant_id="C", reuse_class=ReuseClass.REUSABLE, ancestor_id="B:SA0215", diff=None),
            Prediction(sub_assembly_id="C:0CCSA0314", variant_id="C", reuse_class=ReuseClass.SPECIFIC, ancestor_id="", diff=None),
        ),
        identity=folded,
    )
    exact = Predictor(
        name=baseline.EXACT_REFERENCE,
        description="the raw reference, character for character",
        predictions=tuple(predicted(reference, ReuseClass.SPECIFIC) for reference in ("SA-O107", "OCC-SA-0315", "OCC-SA-0314")),
        identity=raw_strings,
    )
    namesakes = Predictor(
        name=baseline.SAME_NAME,
        description="the raw designation",
        predictions=(
            predicted("SA-O107", ReuseClass.REUSED, "A:SA-0107"),
            predicted("OCC-SA-0315", ReuseClass.REUSED, "B:SA-0215"),
            predicted("OCC-SA-0314", ReuseClass.REUSED, "B:SA-0215"),
        ),
        identity=raw_strings,
    )

    assert score(tool, truth).correct == Ratio(3, 3)
    assert rows(score(tool, truth)) == {"reused": (Ratio(1, 1), Ratio(1, 1)), "reusable": (Ratio(1, 1), Ratio(1, 1)), "new": (Ratio(1, 1), Ratio(1, 1))}
    # The typo'd and the re-designed sub-assembly are both declared absent: only `new` is right.
    assert rows(score(exact, truth)) == {"reused": (Ratio(0, 0), Ratio(0, 1)), "reusable": (Ratio(0, 0), Ratio(0, 1)), "new": (Ratio(1, 3), Ratio(1, 1))}
    # A namesake everywhere: the reuse is found, the change and the new one are claimed to exist.
    assert rows(score(namesakes, truth)) == {"reused": (Ratio(1, 3), Ratio(1, 1)), "reusable": (Ratio(0, 0), Ratio(0, 1)), "new": (Ratio(0, 0), Ratio(0, 1))}


def test_each_predictor_is_scored_through_its_own_identity() -> None:
    """The tool names `C:SA0107`, a baseline `C:SA-O107`; the same answer must score the same."""
    truth = truth_of(labelled("SA-O107", "reused", ("A", "SA-0107")))
    folded = Predictor(
        name="tool",
        description="folded keys",
        predictions=(Prediction(sub_assembly_id="C:SA0107", variant_id="C", reuse_class=ReuseClass.REUSED, ancestor_id="A:SA0107", diff=None),),
        identity={("C", "SA-O107"): "C:SA0107", ("A", "SA-0107"): "A:SA0107"},
    )
    assert score(folded, truth).correct == Ratio(1, 1)
    assert scored(truth, predicted("SA-O107", ReuseClass.REUSED, "A:SA-0107")).correct == Ratio(1, 1)


# --- the committed dataset, and the ground truth it is scored against -----------------------


def scored_committed() -> dict[str, Score]:
    raw = read_raw(COMMITTED_RAW)
    dataset = normalize(raw)
    resolution, _ = resolve(dataset)
    signatures = build_signatures(dataset, resolution)
    result = backtest(signatures, dataset.variants, load_spec().thresholds)
    return {result.predictor: result for result in evaluate(raw, dataset, signatures, result, COMMITTED_GROUND_TRUTH).scores}


def test_the_three_predictors_are_the_tool_and_the_two_naive_searches() -> None:
    assert sorted(scored_committed()) == sorted(["tool", baseline.EXACT_REFERENCE, baseline.SAME_NAME])


def test_the_tool_beats_both_naive_searches_on_the_committed_dataset() -> None:
    """The one value claim, as a test. The figures themselves are `evaluate`'s to print, not a floor."""
    scores = scored_committed()
    assert scores["tool"].correct.hits > scores[baseline.EXACT_REFERENCE].correct.hits
    assert scores["tool"].correct.hits > scores[baseline.SAME_NAME].correct.hits
    assert all(result.correct.total == 15 for result in scores.values()), "the three answer the same 15 items"


def test_each_naive_search_is_handed_the_chronology_the_run_played() -> None:
    """The gap is measured, not manufactured.

    A baseline handed no older variant to look at answers `specific` to everything and still
    passes every other assertion here, while every ratio the README quotes widens in the tool's
    favour. This asserts no predictor's quality and no figure — only that a search reading
    nothing but raw references still finds the references the files spell identically.
    """
    scores = scored_committed()
    for name in (baseline.EXACT_REFERENCE, baseline.SAME_NAME):
        reused = next(row for row in scores[name].classes if row.label == "reused")
        assert reused.recall.hits > 0, f"{name} found no reuse at all: it was handed no ancestor to look at"


def test_neither_naive_search_ever_says_reusable() -> None:
    for name in (baseline.EXACT_REFERENCE, baseline.SAME_NAME):
        reusable = next(row for row in scored_committed()[name].classes if row.label == "reusable")
        assert reusable.precision == Ratio(0, 0), "a search that reads no content claims no near-reuse"
        assert reusable.recall.hits == 0


def test_a_ground_truth_of_another_dataset_is_refused_rather_than_scored(tmp_path: Path) -> None:
    """`--raw` and `--ground-truth` are independent arguments: a mismatch must stop, not print ratios."""
    raw = read_raw(COMMITTED_RAW)
    dataset = normalize(raw)
    resolution, _ = resolve(dataset)
    signatures = build_signatures(dataset, resolution)
    result = backtest(signatures, dataset.variants, load_spec().thresholds)
    elsewhere = tmp_path / "ground_truth.json"
    dump_ground_truth(truth_of(newest_variant="E"), elsewhere)

    with pytest.raises(EvaluationError, match="do not describe the same dataset"):
        evaluate(raw, dataset, signatures, result, elsewhere)


def test_an_unreadable_ground_truth_is_an_evaluation_error(tmp_path: Path) -> None:
    raw = read_raw(COMMITTED_RAW)
    dataset = normalize(raw)
    resolution, _ = resolve(dataset)
    signatures = build_signatures(dataset, resolution)
    result = backtest(signatures, dataset.variants, load_spec().thresholds)
    with pytest.raises(EvaluationError, match="cannot be read"):
        evaluate(raw, dataset, signatures, result, tmp_path / "nowhere.json")

    broken = tmp_path / "broken.json"
    broken.write_text('{"schema_version": "1"}', encoding="utf-8")
    with pytest.raises(EvaluationError, match="not a ground truth"):
        evaluate(raw, dataset, signatures, result, broken)
