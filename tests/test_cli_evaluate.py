"""`bomreuse evaluate` — the one claim, printed.

The command runs the pipeline itself and scores it, so its figures can never be those of a stale
artifact in `out/`. What is checked here is the contract of the output: the three reuse classes
for the tool and for both naive searches, the counts beside every ratio, no decimal anywhere, and
the one line that reconciles the two vocabularies. The figures themselves are not asserted —
there are no regression floors in this build; `evaluate` prints them and the README quotes them.
"""

import re
from pathlib import Path

import pytest

from bomreuse import baseline
from bomreuse.cli import main
from bomreuse.evaluate import evaluate
from bomreuse.ingest import read_raw
from bomreuse.normalize import normalize
from bomreuse.resolve import resolve
from bomreuse.signatures import backtest, build_signatures
from bomreuse.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"
COMMITTED_GROUND_TRUTH = ROOT / "data" / "ground_truth" / "ground_truth.json"

#: A ratio as the output writes it, and the decimal it must never write instead (Decision 3).
_RATIO = re.compile(r"\b\d+/\d+\b")
_DECIMAL = re.compile(r"\b\d+\.\d+\b")


def ran(capsys: pytest.CaptureFixture[str], *extra: str) -> str:
    assert main(["evaluate", "--ground-truth", str(COMMITTED_GROUND_TRUTH), *extra]) == 0
    return capsys.readouterr().out


def test_evaluate_scores_the_tool_and_both_naive_searches(capsys: pytest.CaptureFixture[str]) -> None:
    out = ran(capsys, "--raw", str(COMMITTED_RAW))
    for predictor in ("tool", baseline.EXACT_REFERENCE, baseline.SAME_NAME):
        assert predictor in out
    for label in ("reused", "reusable", "new"):
        assert f"  {label:<16}precision " in out, f"the {label} row is missing for at least one predictor"
    assert out.count("precision ") == 9, "three classes, three predictors"
    assert out.count("recall ") == 9


def test_every_ratio_carries_its_counts_and_no_decimal_is_printed(capsys: pytest.CaptureFixture[str]) -> None:
    out = ran(capsys, "--raw", str(COMMITTED_RAW))
    assert _DECIMAL.search(out) is None, "counts next to every ratio, never a float"
    for line in out.splitlines():
        if "precision " in line:
            assert len(_RATIO.findall(line)) == 2, line
    assert "f1" not in out.lower(), "no aggregate F1, anywhere (Decision 3)"


def test_the_output_says_which_prediction_answers_the_ground_truths_new(capsys: pytest.CaptureFixture[str]) -> None:
    """The rows are the ground truth's words; the divergence is explained once, and only once."""
    out = ran(capsys, "--raw", str(COMMITTED_RAW))
    assert "the prediction that answers 'new' is 'specific'" in out
    assert out.count("'specific'") == 1


def test_the_printed_figures_are_the_ones_the_scorer_computed(capsys: pytest.CaptureFixture[str]) -> None:
    out = ran(capsys, "--raw", str(COMMITTED_RAW))
    raw = read_raw(COMMITTED_RAW)
    dataset = normalize(raw)
    resolution, _ = resolve(dataset)
    result = backtest(build_signatures(dataset, resolution), dataset.variants, load_spec().thresholds)
    evaluation = evaluate(raw, dataset, result, COMMITTED_GROUND_TRUTH)

    assert f"{evaluation.items} (" in out
    for score in evaluation.scores:
        assert f"  {'correct':<16}{score.correct}" in out
        for row in score.classes:
            assert f"  {row.label:<16}precision {str(row.precision):<10}recall {row.recall}" in out


def test_evaluate_says_which_variant_it_played_and_against_which_ones(capsys: pytest.CaptureFixture[str]) -> None:
    """A backtest that had compared the newest variant with itself would print healthy ratios ([A7])."""
    out = ran(capsys, "--raw", str(COMMITTED_RAW))
    assert "C played as the new tender against A, B, D, E" in out
    assert str(COMMITTED_GROUND_TRUTH) in out


def test_the_ground_truth_path_has_no_default() -> None:
    """A5: the one path that is always an argument."""
    with pytest.raises(SystemExit) as refused:
        main(["evaluate", "--raw", str(COMMITTED_RAW)])
    assert refused.value.code == 2


def test_the_raw_directory_defaults_to_the_committed_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The command of the acceptance criteria, run from a directory that holds nothing."""
    monkeypatch.chdir(tmp_path)
    assert ran(capsys) == ran(capsys, "--raw", str(COMMITTED_RAW))


def test_a_missing_raw_directory_is_reported_and_nothing_is_scored(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["evaluate", "--ground-truth", str(COMMITTED_GROUND_TRUTH), "--raw", str(tmp_path / "nowhere")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err


def test_a_ground_truth_that_cannot_be_read_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["evaluate", "--ground-truth", str(tmp_path / "nowhere.json"), "--raw", str(COMMITTED_RAW)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot be read" in captured.err


def test_evaluate_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """It scores; the artifacts are `run`'s to write, and the inputs are read-only either way."""
    monkeypatch.chdir(tmp_path)
    ran(capsys)
    assert list(tmp_path.iterdir()) == []
