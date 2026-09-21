"""End to end: generate a dataset with a test seed, play its newest variant as a new tender, find the reuse.

This is the pilot's main success criterion in miniature (CONTEXT.md), asserted rather than
printed. The ground truth is read here, by the test, and never by the pipeline.

*Found* means what it means to an engineer preparing a tender: the tool points at an older
sub-assembly the ground truth lists as an equivalent — *reused* when it reads the two as
identical, *reusable* when planted dirt puts a part out of the folding rules' reach, which is a
proposal to check rather than a match lost. *Not found* is `specific`: the tool looked, offered
nothing, and the sub-assembly would be re-designed. How many land in each class is
`bomreuse evaluate`'s figure to print; what this file asserts is that no planted reuse is lost
and no genuinely new sub-assembly is claimed to exist already.

The diff is asserted here and nowhere else: `evaluate` scores decisions, `pytest` guards the
evidence. A *reusable* proposal carrying the wrong diff would send an engineer to change the
wrong parts, and no ratio would show it.

The seed is not the committed one — the committed dataset is covered by the other files, and a
second seed moves the dirt without moving the story.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import pytest

from bomreuse.cli import main
from bomreuse.ground_truth import BacktestLabel, Diff, GroundTruth, load_ground_truth
from bomreuse.ingest import read_raw
from bomreuse.model import Prediction, ReuseClass, SignatureDiff
from bomreuse.normalize import normalize, reference_key
from bomreuse.resolve import resolve
from bomreuse.signatures import backtest, build_signatures
from bomreuse.spec import load_spec

#: Not the default seed: the committed dataset is checked elsewhere, and a second seed moves the dirt.
TEST_SEED = 11

#: What "the newest variant re-designed something that already existed" is planted as: a
#: sub-assembly carrying a brand-new reference, or the old reference over changed content.
RE_DESIGNED = ("hidden_reuse", "ref_reused_content_changed")


@dataclass(frozen=True, slots=True)
class Generated:
    """One generated dataset: what is true of it, what the tool answered, and how the two are joined."""

    truth: GroundTruth
    predictions: dict[str, Prediction]
    #: `(variant, raw sub-assembly reference) -> the id the tool predicts under`, as `evaluate` builds it.
    identity: dict[tuple[str, str], str]
    root: Path

    def answer(self, item: BacktestLabel) -> Prediction:
        return self.predictions[self.identity[(item.variant_id, item.sub_assembly_ref)]]

    def listed(self, item: BacktestLabel) -> dict[str, Diff | None]:
        """The ancestors the ground truth lists, by id, each with the diff it declares (Decision 25)."""
        return {self.identity[(ancestor.variant_id, ancestor.sub_assembly_ref)]: ancestor.diff for ancestor in item.ancestors}

    def labelled(self, *labels: str) -> list[BacktestLabel]:
        return [item for item in self.truth.backtest if item.label in labels]

    def keys_of(self, true_component_id: str) -> set[str]:
        """Every canonical component a true component can appear under: one key per spelling emitted.

        A typo the folding rules cannot reach gives one product a second key — which is exactly
        what turns some of these sub-assemblies into *reusable* — so this is a set, not a value.
        """
        component = next(component for component in self.truth.components if component.true_component_id == true_component_id)
        return {reference_key(reference) for reference in component.raw_references}


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Generated:
    root = tmp_path_factory.mktemp("e2e_backtest")
    raw_dir, ground_truth_path = root / "raw", root / "ground_truth.json"
    assert main(["generate", "--out", str(raw_dir), "--ground-truth", str(ground_truth_path), "--seed", str(TEST_SEED)]) == 0

    dataset = normalize(read_raw(raw_dir))
    resolution, _ = resolve(dataset)
    result = backtest(build_signatures(dataset, resolution), dataset.variants, load_spec().thresholds)
    return Generated(
        truth=load_ground_truth(ground_truth_path),
        predictions={prediction.sub_assembly_id: prediction for prediction in result.predictions},
        identity={(group.variant_id, reference): group.id for group in dataset.sub_assemblies for reference in group.raw_references},
        root=root,
    )


# --- the planted reuse is found ---------------------------------------------------------------


def test_the_dataset_plants_all_three_answers(generated: Generated) -> None:
    """A test on a dataset that planted nothing would prove nothing."""
    assert {item.label for item in generated.truth.backtest} == {"reused", "reusable", "new"}
    assert [item for item in generated.truth.backtest if item.planted_as in RE_DESIGNED]


def test_every_planted_reuse_is_found_and_points_at_a_listed_ancestor(generated: Generated) -> None:
    for item in generated.labelled("reused", "reusable"):
        prediction = generated.answer(item)
        existing = [ancestor.sub_assembly_ref for ancestor in item.ancestors]
        assert prediction.reuse_class is not ReuseClass.SPECIFIC, f"{item.sub_assembly_ref} ({item.sub_assembly_designation}) was lost: it exists as {existing}"
        assert prediction.ancestor_id in generated.listed(item), f"{item.sub_assembly_ref} points at {prediction.ancestor_id!r}, which the ground truth does not list"


def test_every_sub_assembly_the_newest_variant_re_designed_is_caught(generated: Generated) -> None:
    """The backtest's reason to exist: a new reference, or changed content, over something that already existed."""
    for item in [item for item in generated.truth.backtest if item.planted_as in RE_DESIGNED]:
        prediction = generated.answer(item)
        assert prediction.reuse_class is not ReuseClass.SPECIFIC, f"{item.sub_assembly_ref} was re-designed and the tool did not notice"
        assert prediction.ancestor_id in generated.listed(item)


def test_a_genuinely_new_sub_assembly_is_not_claimed_to_exist_already(generated: Generated) -> None:
    """The negatives, without which finding everything would be free."""
    new = generated.labelled("new")
    assert new
    for item in new:
        prediction = generated.answer(item)
        assert prediction.reuse_class is ReuseClass.SPECIFIC, f"{item.sub_assembly_ref} is new and the tool proposed {prediction.ancestor_id}"
        assert prediction.ancestor_id == ""


# --- the diff is the evidence the proposal rests on -------------------------------------------


def test_every_near_reuse_carries_the_diff_the_ground_truth_declares(generated: Generated) -> None:
    """What an engineer would have to change to take the older sub-assembly over, part by part."""
    near = generated.labelled("reusable")
    assert near, "no near-reuse planted: the diff would be asserted on nothing"
    for item in near:
        prediction = generated.answer(item)
        assert prediction.reuse_class is ReuseClass.REUSABLE, f"{item.sub_assembly_ref} is a near-reuse and came out {prediction.reuse_class}"
        declared = generated.listed(item)[prediction.ancestor_id]
        assert declared is not None, "a 'reusable' label carries a diff against every ancestor it lists"
        assert_same_diff(generated, prediction.diff, declared, item.sub_assembly_ref)


def assert_same_diff(generated: Generated, found: SignatureDiff | None, declared: Diff, where: str) -> None:
    """The tool's diff against the ground truth's: one written in canonical components, one in true ids."""
    assert found is not None, f"{where}: a 'reusable' answer without a diff is a proposal without its evidence"
    assert len(found.added) == len(declared.added), f"{where}: added {found.added} against {declared.added}"
    assert len(found.removed) == len(declared.removed), f"{where}: removed {found.removed} against {declared.removed}"
    assert len(found.quantity_changed) == len(declared.quantity_changed), f"{where}: {found.quantity_changed} against {declared.quantity_changed}"

    for side, declared_side in ((found.added, declared.added), (found.removed, declared.removed)):
        for expected in declared_side:
            keys = generated.keys_of(expected.true_component_id)
            assert any(item.component in keys and _close(item.quantity, expected.quantity) and item.unit == expected.unit for item in side), f"{where}: {expected} not in {side}"
    for change in declared.quantity_changed:
        keys = generated.keys_of(change.true_component_id)
        assert any(
            found_change.component in keys
            and _close(found_change.left.quantity, change.left)
            and _close(found_change.right.quantity, change.right)
            and found_change.left.unit == found_change.right.unit == change.unit
            for found_change in found.quantity_changed
        ), f"{where}: {change} not in {found.quantity_changed}"


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9)


# --- and the command scores it -----------------------------------------------------------------


def test_evaluate_scores_this_dataset_too(generated: Generated, capsys: pytest.CaptureFixture[str]) -> None:
    """The command of the acceptance criteria, on a dataset that is not the committed one."""
    assert main(["evaluate", "--ground-truth", str(generated.root / "ground_truth.json"), "--raw", str(generated.root / "raw")]) == 0
    printed = capsys.readouterr().out
    assert "precision" in printed and "recall" in printed
