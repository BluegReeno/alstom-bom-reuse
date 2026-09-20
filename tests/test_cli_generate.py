"""`bomreuse generate` writes both outputs where the command line says, and nowhere else."""

from pathlib import Path

import pytest

from bomreuse.cli import main
from bomreuse.ground_truth import load_ground_truth


def test_generate_writes_the_three_raw_files_and_the_ground_truth(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raw, truth = tmp_path / "raw", tmp_path / "truth" / "gt.json"
    assert main(["generate", "--out", str(raw), "--ground-truth", str(truth), "--seed", "7"]) == 0
    assert sorted(path.name for path in raw.iterdir()) == ["bom.csv", "notes.csv", "variants.csv"]
    assert [path.name for path in truth.parent.iterdir()] == ["gt.json"]
    assert load_ground_truth(truth).seed == 7
    assert "BOM lines" in capsys.readouterr().out


def test_the_ground_truth_path_has_no_default(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """docs/ARCHITECTURE.md A5: the path is an argument, never a constant."""
    with pytest.raises(SystemExit) as caught:
        main(["generate", "--out", str(tmp_path / "raw")])
    assert caught.value.code == 2
    assert "--ground-truth" in capsys.readouterr().err


def test_the_raw_directory_has_no_default(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["generate", "--ground-truth", str(tmp_path / "gt.json")])
    assert caught.value.code == 2


@pytest.mark.parametrize("inside", ["gt.json", "nested/gt.json"])
def test_a_ground_truth_inside_the_raw_directory_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str], inside: str) -> None:
    raw = tmp_path / "raw"
    assert main(["generate", "--out", str(raw), "--ground-truth", str(raw / inside)]) == 2
    assert "must not be written inside" in capsys.readouterr().err
    assert not raw.exists(), "nothing may be written when the request is refused"


def test_an_unreadable_spec_is_reported_not_raised(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["generate", "--out", str(tmp_path / "raw"), "--ground-truth", str(tmp_path / "gt.json"), "--spec", str(tmp_path / "nope.toml")])
    assert code == 1
    assert "not found" in capsys.readouterr().err
