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

from bomreuse import cli, notes
from bomreuse.artifacts import (
    FINDINGS_FILE,
    NORMALIZED_FILE,
    NOTE_FACTS_FILE,
    PREDICTIONS_FILE,
    RESOLUTION_FILE,
    RUN_ARTIFACTS,
    SIGNATURES_FILE,
    ModelError,
    load_backtest,
    load_dataset,
    load_findings,
    load_note_facts,
    load_resolution,
    load_signatures,
)
from bomreuse.checks import check, check_notes
from bomreuse.cli import main
from bomreuse.ingest import read_raw
from bomreuse.link import link
from bomreuse.model import (
    Backtest,
    ReuseClass,
)
from bomreuse.normalize import normalize
from bomreuse.notes import DEFAULT_CACHE_DIR, BackendError, KeywordReader, extract
from bomreuse.resolve import resolve
from bomreuse.signatures import backtest, build_signatures
from bomreuse.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"
#: What a run writes, read from the one place it is declared (`artifacts.RUN_ARTIFACTS`).
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
    note_facts = link(extract(dataset.notes, KeywordReader()), resolution)
    assert load_dataset(out / NORMALIZED_FILE) == dataset
    assert load_resolution(out / RESOLUTION_FILE) == resolution
    assert load_note_facts(out / NOTE_FACTS_FILE) == note_facts
    assert load_findings(out / FINDINGS_FILE) == findings + check(dataset, resolution) + check_notes(dataset, resolution, note_facts)
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


def test_there_is_no_option_but_the_paths_the_spec_and_how_the_notes_are_read(capsys: pytest.CaptureFixture[str]) -> None:
    """docs/ARCHITECTURE.md A5: nothing the ground truth could travel through reaches the pipeline.

    The spec is the contract the reuse threshold is read from, the same file `generate` takes;
    a run that classifies by it says which one it used instead of finding one next to its own
    source (`spec.DEFAULT_SPEC_PATH`). The two note options choose a reader and name its model;
    neither is a path, and no option here takes one but `--raw`, `--out` and `--spec`.
    """
    with pytest.raises(SystemExit):
        main(["run", "--help"])
    options = {word.rstrip(",") for word in capsys.readouterr().out.split() if word.startswith("--")}
    assert options == {"--help", "--raw", "--out", "--spec", "--notes", "--notes-model"}


def test_the_threshold_the_run_classifies_by_is_the_one_in_the_spec_it_is_given(tmp_path: Path) -> None:
    """A dataset generated under another spec must not be classified by the committed one."""
    strict = tmp_path / "strict.toml"
    committed_spec = (ROOT / "data" / "dataset_spec.toml").read_text(encoding="utf-8")
    strict.write_text(committed_spec.replace("max_abs_diff = 3", "max_abs_diff = 1").replace("diff_ratio = 0.25", "diff_ratio = 0.05"), encoding="utf-8")

    out, tighter = tmp_path / "out", tmp_path / "tighter"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(tighter), "--spec", str(strict)]) == 0

    classes = {prediction.sub_assembly_id: prediction.reuse_class for prediction in load_backtest(out / PREDICTIONS_FILE).predictions}
    under_strict = {prediction.sub_assembly_id: prediction.reuse_class for prediction in load_backtest(tighter / PREDICTIONS_FILE).predictions}
    assert under_strict != classes
    moved = [key for key, reuse_class in classes.items() if under_strict[key] is not reuse_class]
    assert all(under_strict[key] is ReuseClass.SPECIFIC for key in moved), "a smaller budget can only move a sub-assembly out of reuse"


def test_a_spec_that_cannot_be_read_stops_the_run_before_any_artifact_is_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The last stage reads it; failing there would leave the artifacts of a run that did not finish."""
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out), "--spec", str(tmp_path / "nope.toml")]) == 1
    assert "error:" in capsys.readouterr().err
    assert not out.exists()


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
    type `artifacts` promises on a file it is asked to read.
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


def test_an_answer_resting_on_less_than_the_whole_sub_assembly_says_so_on_its_row(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A line the pipeline could not read shortens a signature, and a shorter signature is a
    smaller sub-assembly to the comparison. The `issues` count says how dirty the file is; this
    says which answer is affected, so a truncated *reused* cannot read as a whole one.
    """
    raw, out = tmp_path / "raw", tmp_path / "out"
    shutil.copytree(COMMITTED_RAW, raw)
    with (raw / "bom.csv").open("a", encoding="utf-8") as handle:
        handle.write("L99998;C;SA-0101;CARBODY SHELL;SHELL-BIKE-HOOK;Bike hook;4;bananes;Atelier Lys Métal;12,00\n")

    assert main(["run", "--raw", str(raw), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    truncated = {signature.sub_assembly_id for signature in load_signatures(out / SIGNATURES_FILE) if signature.lines_left_out}
    assert truncated == {"C:SA0101"}
    line = next(line for line in printed.splitlines() if line.strip().startswith("C:SA0101 "))
    assert "[1 line not read]" in line


def test_a_dataset_with_no_readable_design_date_says_so_instead_of_guessing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The backtest needs a chronology. Without one the run still succeeds and says what is missing."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    shutil.copytree(COMMITTED_RAW, raw)
    variants = (raw / "variants.csv").read_text(encoding="utf-8").splitlines()
    header, rows = variants[0], [row.split(";") for row in variants[1:]]
    for row in rows:
        row[2] = "date unknown"
    (raw / "variants.csv").write_text("\n".join([header, *(";".join(row) for row in rows)]) + "\n", encoding="utf-8")

    assert main(["run", "--raw", str(raw), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "no variant carries a readable design date" in printed
    assert load_backtest(out / PREDICTIONS_FILE) == Backtest("", (), ())


def test_the_summary_shows_the_inconsistencies_by_type_with_their_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The second half of the client's question, on the same stdout as the first."""
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    findings = load_findings(out / FINDINGS_FILE)

    counts = {kind: sum(finding.rule_id == f"checks.{kind}_conflict" for finding in findings) for kind in ("unit", "supplier", "cost")}
    assert all(counts.values()), counts
    assert f"inconsistencies   {sum(counts.values())} components whose rows disagree" in printed
    block = printed[printed.index("inconsistencies   ") :]
    for kind, count in counts.items():
        assert f"  {kind:<16}{count}" in block
    first_unit_conflict = next(finding for finding in findings if finding.rule_id == "checks.unit_conflict")
    assert first_unit_conflict.message in block


def test_a_reuse_resting_on_a_part_in_conflict_is_flagged_on_its_row(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The row a design engineer must not trust at face value says so where they read it.

    Every *reused* or *reusable* row whose parts carry a conflict names each such part; no other
    row carries the flag, and a *specific* row never does — it proposes no reuse to warn against.
    """
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    in_conflict = {finding.subject for finding in load_findings(out / FINDINGS_FILE) if finding.rule_id.startswith("checks.")}
    parts = {signature.sub_assembly_id: {item.component for item in signature.signature.items} for signature in load_signatures(out / SIGNATURES_FILE)}

    flagged = 0
    for prediction in load_backtest(out / PREDICTIONS_FILE).predictions:
        line = next(line for line in printed.splitlines() if line.strip().startswith(f"{prediction.sub_assembly_id} "))
        expected = sorted(parts[prediction.sub_assembly_id] & in_conflict) if prediction.reuse_class is not ReuseClass.SPECIFIC else []
        assert ("[check: " in line) == bool(expected), line
        for component in expected:
            assert f"{component} (" in line
        flagged += bool(expected)
    assert flagged, "the committed dataset plants conflicts under reused sub-assemblies: the test would prove nothing"


# --- the notes, on the same stdout -----------------------------------------------------------------


def test_the_summary_says_which_reader_read_the_notes_and_what_it_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    note_facts = load_note_facts(out / NOTE_FACTS_FILE)

    assert note_facts.facts, "the committed notes carry facts the fallback reads: the test would prove nothing"
    assert f"notes             {note_facts.notes_read} read by keyword" in printed
    assert f"  facts           {len(note_facts.facts)} (" in printed
    assert f"  unusable output {note_facts.invalid_outputs}" in printed


def test_the_summary_shows_what_the_notes_contradict_by_kind_with_their_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    findings = load_findings(out / FINDINGS_FILE)

    counts = {kind: sum(finding.rule_id == f"checks.note_{kind}" for finding in findings) for kind in ("obsolescence", "replacement", "restriction")}
    assert all(counts.values()), counts
    assert f"note vs BOM       {sum(counts.values())} parts a note contradicts the BOM about" in printed
    block = printed[printed.index("note vs BOM       ") :]
    for kind, count in counts.items():
        assert f"  {kind:<16}{count}" in block


def test_a_reuse_resting_on_a_part_a_note_speaks_against_is_flagged_on_its_row(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The demo's sharpest row: a sub-assembly the tool calls reusable, holding a part a note retired."""
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    obsolete = {finding.subject for finding in load_findings(out / FINDINGS_FILE) if finding.rule_id == "checks.note_obsolescence"}
    parts = {signature.sub_assembly_id: {item.component for item in signature.signature.items} for signature in load_signatures(out / SIGNATURES_FILE)}

    flagged = [
        prediction
        for prediction in load_backtest(out / PREDICTIONS_FILE).predictions
        if prediction.reuse_class is not ReuseClass.SPECIFIC and parts[prediction.sub_assembly_id] & obsolete
    ]
    assert flagged, "the committed notes retire a part under a reused sub-assembly: the test would prove nothing"
    for prediction in flagged:
        line = next(line for line in printed.splitlines() if line.strip().startswith(f"{prediction.sub_assembly_id} "))
        for component in sorted(parts[prediction.sub_assembly_id] & obsolete):
            assert f"{component} (" in line and "obsolescence" in line


# --- offline by default ------------------------------------------------------------------------------


def test_the_default_run_makes_no_call_at_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLAUDE.md rule 5, from the inside: with the fallback there is nothing to be unreachable."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the default run reached for the network")

    monkeypatch.setattr(notes, "urlopen", refuse)
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(tmp_path / "out")]) == 0


def test_the_default_run_writes_nothing_outside_the_output_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The response cache belongs to the model reader; a run that never calls a model creates none."""
    raw = tmp_path / "raw"
    shutil.copytree(COMMITTED_RAW, raw)
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--raw", "raw", "--out", "out"]) == 0
    assert sorted(path.name for path in tmp_path.iterdir()) == ["out", "raw"]


# --- and the model, when it is asked for ----------------------------------------------------------------


class _FakeBackend:
    """Stands in for `OllamaBackend`, so the wiring is tested without a model or a socket."""

    def __init__(self, model: str, answer: str | BackendError = '{"facts": []}') -> None:
        self.model = model
        self._answer = answer
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        if isinstance(self._answer, BackendError):
            raise self._answer
        return self._answer


def test_the_model_reader_is_used_when_it_is_asked_for_and_named_in_the_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[_FakeBackend] = []

    def backend(model: str) -> _FakeBackend:
        built.append(_FakeBackend(model))
        return built[-1]

    monkeypatch.setattr(cli, "OllamaBackend", backend)
    monkeypatch.chdir(tmp_path)  # the response cache is written beside the working directory
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out), "--notes", "llm", "--notes-model", "some-model"]) == 0

    assert [fake.model for fake in built] == ["some-model"]
    note_facts = load_note_facts(out / NOTE_FACTS_FILE)
    assert (note_facts.reader, note_facts.facts) == ("llm:some-model", ())
    assert built[0].calls == note_facts.notes_read, "one call per note"
    assert "read by llm:some-model" in capsys.readouterr().out
    assert list((tmp_path / DEFAULT_CACHE_DIR).glob("some-model-*.json")), "the answers are cached, outside the artifacts"


def test_a_model_that_does_not_answer_stops_the_run_and_says_what_to_run_instead(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asking for a model that is not there is an error; the offline path is one flag away, and said."""
    monkeypatch.setattr(cli, "OllamaBackend", lambda model: _FakeBackend(model, BackendError("nothing answered")))
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(tmp_path / "out"), "--notes", "llm"]) == 1
    assert "--notes keyword" in capsys.readouterr().err
