"""`bomreuse normalize` reads where it is told, writes one artifact where it is told, and nothing else."""

import shutil
from pathlib import Path

import pytest

from bomreuse.cli import main
from bomreuse.ingest import read_raw
from bomreuse.model import NORMALIZED_FILE, load_dataset
from bomreuse.normalize import normalize

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"


def test_normalize_writes_the_artifact_and_says_what_it_read(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    assert main(["normalize", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    assert [path.name for path in out.iterdir()] == [NORMALIZED_FILE]
    printed = capsys.readouterr().out
    for label in ("BOM lines", "notes", "variants", "components", "sub-assemblies", "suppliers", "issues", NORMALIZED_FILE):
        assert label in printed


def test_the_artifact_reads_back_into_the_objects_the_pipeline_built(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main(["normalize", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    assert load_dataset(out / NORMALIZED_FILE) == normalize(read_raw(COMMITTED_RAW))


def test_running_twice_gives_the_same_bytes(tmp_path: Path) -> None:
    for name in ("first", "second"):
        assert main(["normalize", "--raw", str(COMMITTED_RAW), "--out", str(tmp_path / name)]) == 0
    assert (tmp_path / "first" / NORMALIZED_FILE).read_bytes() == (tmp_path / "second" / NORMALIZED_FILE).read_bytes()


@pytest.mark.parametrize("given, missing", [(["--raw", "somewhere"], "--out"), (["--out", "somewhere"], "--raw")])
def test_neither_path_has_a_default(capsys: pytest.CaptureFixture[str], given: list[str], missing: str) -> None:
    """docs/ARCHITECTURE.md A5: what the pipeline reads and writes is said on the command line, never assumed."""
    with pytest.raises(SystemExit) as caught:
        main(["normalize", *given])
    assert caught.value.code == 2
    assert missing in capsys.readouterr().err


def test_there_is_no_option_that_could_carry_anything_but_the_two_directories(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["normalize", "--help"])
    options = {word.rstrip(",") for word in capsys.readouterr().out.split() if word.startswith("--")}
    assert options == {"--help", "--raw", "--out"}


@pytest.mark.parametrize("inside", [".", "out", "nested/out"])
def test_an_output_directory_inside_the_raw_directory_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str], inside: str) -> None:
    raw = tmp_path / "raw"
    shutil.copytree(COMMITTED_RAW, raw)
    assert main(["normalize", "--raw", str(raw), "--out", str(raw / inside)]) == 2
    assert "inputs are read-only" in capsys.readouterr().err
    assert sorted(path.name for path in raw.iterdir()) == ["bom.csv", "notes.csv", "variants.csv"], "nothing may be written when the request is refused"


def test_a_raw_directory_without_the_files_is_reported_not_raised(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    assert main(["normalize", "--raw", str(raw), "--out", str(out)]) == 1
    assert "not found" in capsys.readouterr().err
    assert not out.exists(), "nothing is written when the input cannot be read"


def test_a_malformed_file_is_reported_with_its_row_and_nothing_is_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    shutil.copytree(COMMITTED_RAW, raw)
    with (raw / "bom.csv").open("a", encoding="utf-8") as handle:
        handle.write("L99999;A;too;short\n")
    assert main(["normalize", "--raw", str(raw), "--out", str(out)]) == 1
    assert "bom.csv row 697 has 4 cells" in capsys.readouterr().err
    assert not out.exists()


def test_unreadable_values_are_counted_and_do_not_fail_the_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    shutil.copytree(COMMITTED_RAW, raw)
    with (raw / "bom.csv").open("a", encoding="utf-8") as handle:
        handle.write("L99998;A;SA-0101;carbody shell;BGI-2031;Bolt set;abc;pcs;Portalys;1,00\n")
        handle.write("L99999;A;SA-0101;carbody shell;BGI-2031;Bolt set;xyz;cm;Portalys;1,00\n")
    assert main(["normalize", "--raw", str(raw), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "issues            3" in printed
    assert "bom.csv quantity: not a number  2" in printed and "bom.csv unit: unknown unit  1" in printed
    restored = load_dataset(out / NORMALIZED_FILE)
    assert len(restored.lines) == 698 and len(restored.issues) == 3
