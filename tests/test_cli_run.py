"""`bomreuse run` — the first end-to-end command a client would be shown.

It reads the raw CSV files, resolves the references and writes the artifacts, offline, and says
on stdout what it found. From the signatures issue on it also prints the reuse classes of the
newest variant, so the demo never depends on the HTML report having landed.
"""

import shutil
from pathlib import Path

import pytest

from bomreuse import cli
from bomreuse.cli import main
from bomreuse.ingest import read_raw
from bomreuse.model import FINDINGS_FILE, NORMALIZED_FILE, RESOLUTION_FILE, ModelError, load_dataset, load_findings, load_resolution
from bomreuse.normalize import normalize
from bomreuse.resolve import resolve

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"
ARTIFACTS = [NORMALIZED_FILE, RESOLUTION_FILE, FINDINGS_FILE]


def test_run_writes_the_artifacts_and_says_what_it_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    assert sorted(path.name for path in out.iterdir()) == sorted(ARTIFACTS)

    printed = capsys.readouterr().out
    for label in ("raw files", "BOM lines", "variants", "candidate groups", "canonical components", "auto", "review", "reject", "findings"):
        assert label in printed
    for artifact in ARTIFACTS:
        assert artifact in printed


def test_the_artifacts_read_back_into_the_objects_the_pipeline_built(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0

    dataset = normalize(read_raw(COMMITTED_RAW))
    resolution, findings = resolve(dataset)
    assert load_dataset(out / NORMALIZED_FILE) == dataset
    assert load_resolution(out / RESOLUTION_FILE) == resolution
    assert load_findings(out / FINDINGS_FILE) == findings


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
    """Refused before anything is written, and for every artifact, not only the first."""
    raw = tmp_path / "raw"
    shutil.copytree(COMMITTED_RAW, raw)
    assert main(["run", "--raw", str(raw), "--out", str(raw / inside)]) == 2
    assert "inputs are read-only" in capsys.readouterr().err
    assert sorted(path.name for path in raw.iterdir()) == ["bom.csv", "notes.csv", "variants.csv"]


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
