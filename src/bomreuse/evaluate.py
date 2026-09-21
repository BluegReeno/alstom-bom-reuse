"""The one claim this build makes, measured: the backtest, scored against the ground truth.

This is the only module that reads the ground truth — CLAUDE.md rule 2, made structural by
docs/ARCHITECTURE.md A5 and kept honest by an AST test that scans every other module of the
package. The path is a parameter, never a constant, and not even a default: `evaluate` scores
the file the command line names, and the pipeline's entry functions have no parameter that could
carry one.

Three predictors answer the same question about the same items — the tool's backtest, and the two
naive searches of `baseline.py` — and **one** function scores all three. Nothing here reads the
tool more kindly than a baseline: same relation, same ancestor rule, same items, same counts.

The two vocabularies meet here and nowhere else (Decision 30). The ground truth *asserts* `new`:
it generated the data, so it knows. The pipeline can only *observe* `specific` — that it compared
a sub-assembly against every older one and found no match — and a pipeline claiming `new` would
be asserting the absence of something it merely failed to find, on data whose dirtiness is the
point of the tool. `ANSWERS` is that translation, and it runs one way: for each thing the truth
says, the one prediction that answers it. A `specific` where the truth says `reused` is a match
missed to a typo and stays a miss; the relation has no reverse entry.

No aggregate F1, here or anywhere (Decision 3), and no ratio without its counts: `Ratio` carries
the two numbers it was read off and cannot be printed as a float.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from bomreuse import baseline
from bomreuse.ground_truth import BacktestLabel, GroundTruth, Label, load_ground_truth
from bomreuse.model import Backtest, NormalizedDataset, Prediction, RawDataset, ReuseClass, SubAssemblySignature

#: The predictor whose value the two baselines are there to measure.
TOOL: Final[str] = "tool"
_TOOL_DESCRIPTION: Final[str] = "signatures over the canonical components, against the variants designed earlier"

#: The correctness relation: for each thing the ground truth says, the **one** prediction that
#: answers it (Decision 30). Exhaustive over both enumerations — a test asserts that every member
#: of `Label` and every member of `ReuseClass` appears — so a class added to either side breaks a
#: test instead of drifting a ratio in silence. It is read in this direction only.
ANSWERS: Final[Mapping[Label, ReuseClass]] = {
    "reused": ReuseClass.REUSED,
    "reusable": ReuseClass.REUSABLE,
    "new": ReuseClass.SPECIFIC,
}


class EvaluationError(ValueError):
    """The ground-truth file cannot be read, or does not describe the dataset that was run."""


@dataclass(frozen=True, slots=True)
class Ratio:
    """A ratio carried as the two counts it was read off: `8/9` is printable, `0.89` is not.

    Fifteen items is too few for a decimal to mean anything, and a reader who cannot see the
    denominator cannot tell `4/4` from `40/40` (Decision 3).
    """

    hits: int
    total: int

    def __str__(self) -> str:
        return f"{self.hits}/{self.total}"


@dataclass(frozen=True, slots=True)
class Predictor:
    """One answer to the backtest, and the identity it names sub-assemblies under.

    `identity` maps `(variant, raw sub-assembly reference) -> the id this predictor predicts
    under`. The ground truth names a sub-assembly by the raw reference the files carry; the tool
    names it by the folded key `normalize` gave it, a baseline by the raw string itself. Scoring
    each predictor through its own identity is what lets one relation judge all three without
    either side borrowing the other's notion of sameness.
    """

    name: str
    description: str
    predictions: tuple[Prediction, ...]
    identity: Mapping[tuple[str, str], str]


@dataclass(frozen=True, slots=True)
class ClassScore:
    """One row of the table: a ground-truth label, and how one predictor did on it.

    `answer` is the prediction that answers `label`, carried on the row so the output can say —
    once — which word of the tool's vocabulary the `new` row is scoring.
    """

    label: Label
    answer: ReuseClass
    precision: Ratio
    recall: Ratio


@dataclass(frozen=True, slots=True)
class Score:
    """What one predictor got right, by class and overall."""

    predictor: str
    description: str
    classes: tuple[ClassScore, ...]
    correct: Ratio


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Everything `bomreuse evaluate` prints, computed.

    The variants are carried because the score is only worth what the chronology is worth: a
    backtest that had compared the newest variant with itself would print healthy ratios ([A7]).

    `lines_left_out` is carried for the same reason: a class decided on the two lines of a
    sub-assembly that parsed is not the class its whole content would have earned, so a ratio
    read off truncated signatures must not look like one read off complete ones.
    """

    ground_truth_path: Path
    target_variant_id: str
    ancestor_variant_ids: tuple[str, ...]
    labelled: Mapping[Label, int]
    lines_left_out: int
    scores: tuple[Score, ...]

    @property
    def items(self) -> int:
        return sum(self.labelled.values())


def evaluate(
    raw: RawDataset,
    dataset: NormalizedDataset,
    signatures: tuple[SubAssemblySignature, ...],
    result: Backtest,
    ground_truth_path: Path,
) -> Evaluation:
    """Score the tool and the two naive searches against the ground truth the caller names.

    The signatures are read for one number only — the BOM lines they could not read — because
    the score is worth what the evidence under it is worth.
    """
    truth = _load(ground_truth_path)
    if truth.newest_variant != result.target_variant_id:
        raise EvaluationError(
            f"{ground_truth_path} calls {truth.newest_variant!r} the newest variant and the run played "
            f"{result.target_variant_id!r}: the two do not describe the same dataset"
        )

    older = result.ancestor_variant_ids
    naive = baseline.sub_assembly_ids(raw)
    predictors = (
        Predictor(
            name=TOOL,
            description=_TOOL_DESCRIPTION,
            predictions=result.predictions,
            identity={(group.variant_id, reference): group.id for group in dataset.sub_assemblies for reference in group.raw_references},
        ),
        Predictor(
            name=baseline.EXACT_REFERENCE,
            description=baseline.DESCRIPTIONS[baseline.EXACT_REFERENCE],
            predictions=baseline.exact_reference(raw, result.target_variant_id, older),
            identity=naive,
        ),
        Predictor(
            name=baseline.SAME_NAME,
            description=baseline.DESCRIPTIONS[baseline.SAME_NAME],
            predictions=baseline.same_name(raw, result.target_variant_id, older),
            identity=naive,
        ),
    )
    return Evaluation(
        ground_truth_path=ground_truth_path,
        target_variant_id=result.target_variant_id,
        ancestor_variant_ids=older,
        labelled={label: sum(1 for item in truth.backtest if item.label == label) for label in ANSWERS},
        lines_left_out=sum(signature.lines_left_out for signature in signatures),
        scores=tuple(score(predictor, truth) for predictor in predictors),
    )


def score(predictor: Predictor, truth: GroundTruth) -> Score:
    """Precision and recall on the three reuse classes, for one predictor.

    The items are the ground truth's, never the predictor's: a predictor answering about a
    sub-assembly the ground truth does not list would otherwise pad its own denominator. Saying
    nothing about a listed one is a miss like any other wrong answer — a sub-assembly the pipeline
    could not carry this far is one the tool did not find.
    """
    by_id = {prediction.sub_assembly_id: prediction for prediction in predictor.predictions}
    answered = {item.sub_assembly_ref: _answer(item, predictor.identity, by_id) for item in truth.backtest}
    right = {item.sub_assembly_ref: _is_hit(item, answered[item.sub_assembly_ref], predictor.identity) for item in truth.backtest}

    classes = []
    for label, answer in ANSWERS.items():
        # A hit carries the truth's label *and* that label's answer, so one count is the numerator
        # of both ratios: what was right among what was claimed, and among what was there to find.
        hits = sum(1 for item in truth.backtest if item.label == label and right[item.sub_assembly_ref])
        claimed = sum(1 for item in truth.backtest if _claims(answered[item.sub_assembly_ref], answer))
        there = sum(1 for item in truth.backtest if item.label == label)
        classes.append(ClassScore(label=label, answer=answer, precision=Ratio(hits, claimed), recall=Ratio(hits, there)))

    return Score(
        predictor=predictor.name,
        description=predictor.description,
        classes=tuple(classes),
        correct=Ratio(sum(right.values()), len(truth.backtest)),
    )


def _claims(prediction: Prediction | None, answer: ReuseClass) -> bool:
    """Whether the predictor put this item in that class — right or wrong. The precision denominator."""
    return prediction is not None and prediction.reuse_class is answer


def _answer(item: BacktestLabel, identity: Mapping[tuple[str, str], str], by_id: Mapping[str, Prediction]) -> Prediction | None:
    """What this predictor said about this sub-assembly, or `None` when it said nothing at all."""
    predicted_under = identity.get((item.variant_id, item.sub_assembly_ref))
    return by_id.get(predicted_under) if predicted_under is not None else None


def _is_hit(item: BacktestLabel, prediction: Prediction | None, identity: Mapping[tuple[str, str], str]) -> bool:
    """The relation of Decision 30, applied to one sub-assembly.

    The class must be the one `ANSWERS` gives the truth's label, and — when the truth lists
    ancestors — the prediction must name one of them. *Which* one is never scored: listed
    ancestors are equal in true content, and planted dirt makes some of them differ in the raw
    files, so naming any one of them is enough to reuse from (Decision 25). A `new` label lists
    none, and there the class alone decides.
    """
    if prediction is None or prediction.reuse_class is not ANSWERS[item.label]:
        return False
    if not item.ancestors:
        return True
    keys = [(ancestor.variant_id, ancestor.sub_assembly_ref) for ancestor in item.ancestors]
    return prediction.ancestor_id in {identity[key] for key in keys if key in identity}


def _load(path: Path) -> GroundTruth:
    try:
        return load_ground_truth(path)
    except OSError as exc:
        raise EvaluationError(f"{path} cannot be read: {exc.strerror or exc}") from exc
    except ValueError as exc:  # pydantic's ValidationError, and the schema's own cross-checks
        raise EvaluationError(f"{path} is not a ground truth this version can score: {exc}") from exc
