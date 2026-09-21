"""`bomreuse run` — the first end-to-end command a client would be shown.

It reads the raw CSV files, resolves the references and writes the artifacts, offline, and says
on stdout what it found. From the signatures issue on it also prints the reuse classes of the
newest variant, so the demo never depends on the HTML report having landed.
"""

import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from bomreuse import cli
from bomreuse.cli import main
from bomreuse.ingest import read_raw
from bomreuse.model import (
    FINDINGS_FILE,
    NORMALIZED_FILE,
    PREDICTIONS_FILE,
    RESOLUTION_FILE,
    RUN_ARTIFACTS,
    SIGNATURES_FILE,
    ModelError,
    load_backtest,
    load_dataset,
    load_findings,
    load_resolution,
    load_signatures,
)
from bomreuse.normalize import normalize
from bomreuse.resolve import resolve
from bomreuse.signatures import backtest, build_signatures
from bomreuse.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"
#: What a run writes, read from the one place it is declared (`model.RUN_ARTIFACTS`).
ARTIFACTS = list(RUN_ARTIFACTS)


def test_run_writes_the_artifacts_and_says_what_it_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    assert sorted(path.name for path in out.iterdir()) == sorted(ARTIFACTS)

    printed = capsys.readouterr().out
    for label in ("raw files", "BOM lines", "variants", "candidate groups", "canonical components", "auto", "review", "reject", "findings", "issues"):
        assert label in printed
    for artifact in ARTIFACTS:
        assert artifact in printed


def test_the_artifacts_read_back_into_the_objects_the_pipeline_built(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0

    dataset = normalize(read_raw(COMMITTED_RAW))
    resolution, findings = resolve(dataset)
    signatures = build_signatures(dataset, resolution)
    assert load_dataset(out / NORMALIZED_FILE) == dataset
    assert load_resolution(out / RESOLUTION_FILE) == resolution
    assert load_findings(out / FINDINGS_FILE) == findings
    assert load_signatures(out / SIGNATURES_FILE) == signatures
    assert load_backtest(out / PREDICTIONS_FILE) == backtest(signatures, dataset.variants, load_spec().thresholds)


def test_running_twice_gives_the_same_bytes(tmp_path: Path) -> None:
    for name in ("first", "second"):
        assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(tmp_path / name)]) == 0
    for artifact in ARTIFACTS:
        assert (tmp_path / "first" / artifact).read_bytes() == (tmp_path / "second" / artifact).read_bytes()


@pytest.mark.parametrize("given, missing", [(["--raw", "somewhere"], "--out"), (["--out", "somewhere"], "--raw")])
def test_neither_path_has_a_default(capsys: pytest.CaptureFixture[str], given: list[str], missing: str) -> None:
    """docs/ARCHITECTURE.md A5: what the pipeline reads and writes is said on the command line, never assumed."""
    with pytest.raises(SystemExit) as caught:
        main(["run", *given])
    assert caught.value.code == 2
    assert missing in capsys.readouterr().err


def test_there_is_no_option_that_could_carry_anything_but_the_two_directories(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["run", "--help"])
    options = {word.rstrip(",") for word in capsys.readouterr().out.split() if word.startswith("--")}
    assert options == {"--help", "--raw", "--out"}


@pytest.mark.parametrize("inside", [".", "out", "nested/out"])
def test_an_output_directory_inside_the_raw_directory_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str], inside: str) -> None:
    """Refused before anything is written. Every artifact is inside `--raw` here, so the first one decides."""
    raw = tmp_path / "raw"
    shutil.copytree(COMMITTED_RAW, raw)
    assert main(["run", "--raw", str(raw), "--out", str(raw / inside)]) == 2
    assert "inputs are read-only" in capsys.readouterr().err
    assert sorted(path.name for path in raw.iterdir()) == ["bom.csv", "notes.csv", "variants.csv"]


@pytest.mark.parametrize("link", [os.symlink, os.link], ids=["symlink", "hard-link"])
def test_an_artifact_landing_on_an_input_through_a_link_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], link: Callable[[Path, Path], None]
) -> None:
    """Each artifact in turn, with `--out` outside `--raw` so that one alone decides.

    A guard that checked only the first would let the second overwrite `bom.csv` with its own
    JSON and exit 0 — the pipeline's only input destroyed by a run reporting success. The names
    come from what a run really writes, so an artifact a later issue adds is covered here
    without anyone remembering to add it.
    """
    for artifact in _artifacts_a_run_writes(tmp_path / "reference"):
        raw, out = tmp_path / artifact / "raw", tmp_path / artifact / "out"
        shutil.copytree(COMMITTED_RAW, raw)
        out.mkdir()
        bom = raw / "bom.csv"
        untouched = bom.read_bytes()
        link(bom, out / artifact)

        assert main(["run", "--raw", str(raw), "--out", str(out)]) == 2, f"{artifact} is never checked against the raw directory"
        assert "inputs are read-only" in capsys.readouterr().err
        assert bom.read_bytes() == untouched


def _artifacts_a_run_writes(out: Path) -> list[str]:
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    return sorted(path.name for path in out.iterdir())


def test_a_raw_directory_that_is_not_one_stops_the_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--raw", str(tmp_path / "nowhere"), "--out", str(tmp_path / "out")]) == 1
    assert "error:" in capsys.readouterr().err
    assert not (tmp_path / "out").exists(), "nothing is written when the input cannot be read"


def test_an_artifact_the_model_refuses_is_reported_rather_than_raised(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """`run` hands each stage the previous stage's file, so the model's own error is its error path.

    A command shows a message and an exit code, never a traceback — including for the one error
    type `model` promises on a file it is asked to read.
    """

    def refuse(path: Path) -> None:
        raise ModelError(f"normalized dataset at {path} is not valid JSON: forced")

    monkeypatch.setattr(cli, "load_dataset", refuse)
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(tmp_path / "out")]) == 1
    assert "error: normalized dataset at" in capsys.readouterr().err


def test_unreadable_values_are_counted_on_the_summary_the_client_reads(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Every stage after `normalize` ignores them on the ground that `normalize` counted them.

    That is only honest while the count is on the screen the reader is looking at: without it a
    dirtier BOM reads as a tidier one, because an unreadable value removes conflicts and findings.
    """
    raw, out = tmp_path / "raw", tmp_path / "out"
    shutil.copytree(COMMITTED_RAW, raw)
    with (raw / "bom.csv").open("a", encoding="utf-8") as handle:
        handle.write("L99998;A;SA-0101;carbody shell;BGI-2031;Bolt set;abc;pcs;Portalys;1,00\n")
    assert main(["run", "--raw", str(raw), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "issues            1" in printed
    assert "bom.csv quantity: not a number  1" in printed


def test_the_summary_shows_the_reuse_class_of_every_sub_assembly_of_the_newest_variant(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The demo's safety net (Decision 29): the answer is on stdout, whatever the report does.

    Asserted line by line against the artifact the same run wrote, so the table cannot drift
    from the predictions — and against the counts underneath, so no ratio is shown alone.
    """
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    result = load_backtest(out / PREDICTIONS_FILE)
    designations = {signature.sub_assembly_id: signature.designations for signature in load_signatures(out / SIGNATURES_FILE)}

    assert f"backtest          {result.target_variant_id} " in printed
    assert ", ".join(result.ancestor_variant_ids) in printed
    for prediction in result.predictions:
        line = next(line for line in printed.splitlines() if line.strip().startswith(prediction.sub_assembly_id))
        assert designations[prediction.sub_assembly_id][0] in line
        assert prediction.reuse_class.value in line
        assert prediction.ancestor_id in line
        if prediction.diff is not None:
            assert prediction.diff.added or prediction.diff.removed or prediction.diff.quantity_changed
            for item in (*prediction.diff.added, *prediction.diff.removed):
                assert item.component in line
    for reuse_class in ("reused", "reusable", "specific"):
        count = sum(prediction.reuse_class.value == reuse_class for prediction in result.predictions)
        assert f"  {reuse_class:<16}{count}" in printed


def test_a_reusable_sub_assembly_says_on_one_line_what_would_have_to_change(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A class without its diff is a claim a reader cannot check; the demo shows the diff."""
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    reusable = [prediction for prediction in load_backtest(out / PREDICTIONS_FILE).predictions if prediction.reuse_class.value == "reusable"]
    assert reusable

    for prediction in reusable:
        line = next(line for line in printed.splitlines() if line.strip().startswith(prediction.sub_assembly_id))
        assert prediction.diff is not None
        for change in prediction.diff.quantity_changed:
            assert f"{change.component} {change.left.quantity:g} {change.left.unit} -> {change.right.quantity:g} {change.right.unit}" in line
