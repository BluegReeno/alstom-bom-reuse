"""The generator's honesty invariants: reproducible, leak-free, isolated, and agreeing with the verdict rule.

These are the tests whose silent disappearance would matter most — every score `evaluate` prints
later rests on them.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bomreuse.generate import BOM_COLUMNS, DEFAULT_SEED, NOTE_COLUMNS, VARIANT_COLUMNS, build_true_model, generate
from bomreuse.ground_truth import BacktestLabel, Diff, GroundTruth, load_ground_truth
from bomreuse.signatures import Comparison, Signature, Verdict, compare
from bomreuse.spec import DatasetSpec, load_spec

SPEC: DatasetSpec = load_spec()
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "bomreuse"

#: The generator's side of the code base. Nothing in it may import the pipeline it will be scored against.
GENERATOR_MODULES = ("generate.py", "catalogue.py", "dirt.py", "ground_truth.py")
ALLOWED_IMPORTS = {"spec", "catalogue", "dirt", "ground_truth"}


def files_of(raw: Path, truth: Path) -> dict[str, bytes]:
    found = {path.name: path.read_bytes() for path in sorted(raw.iterdir())}
    found[truth.name] = truth.read_bytes()
    return found


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    base = tmp_path_factory.mktemp("dataset")
    raw, truth = base / "raw", base / "truth" / "ground_truth.json"
    generate(SPEC, DEFAULT_SEED, raw, truth)
    return raw, truth


# --- determinism -------------------------------------------------------------------------------


def test_the_same_seed_gives_byte_identical_files(generated: tuple[Path, Path], tmp_path: Path) -> None:
    raw, truth = tmp_path / "raw", tmp_path / "truth" / "ground_truth.json"
    generate(SPEC, DEFAULT_SEED, raw, truth)
    assert files_of(raw, truth) == files_of(*generated)


def test_the_same_seed_gives_byte_identical_files_across_processes(tmp_path: Path) -> None:
    """Two interpreters with different hash seeds: this is the test that catches an iterated `set`."""
    outputs = []
    for hash_seed in ("1", "2"):
        raw, truth = tmp_path / hash_seed / "raw", tmp_path / hash_seed / "truth" / "ground_truth.json"
        subprocess.run(
            [sys.executable, "-m", "bomreuse.cli", "generate", "--out", str(raw), "--ground-truth", str(truth)],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
        )
        outputs.append(files_of(raw, truth))
    assert outputs[0] == outputs[1]


def test_nothing_in_the_output_depends_on_where_or_when_it_was_written(generated: tuple[Path, Path]) -> None:
    for name, content in files_of(*generated).items():
        assert str(generated[0].parent).encode() not in content, name


# --- nothing leaks into the pipeline's input -----------------------------------------------------


def test_the_raw_directory_holds_the_three_input_files_with_their_exact_headers(generated: tuple[Path, Path]) -> None:
    raw, _ = generated
    headers = {path.name: path.read_text(encoding="utf-8").splitlines()[0] for path in raw.iterdir()}
    assert headers == {
        "variants.csv": ";".join(VARIANT_COLUMNS),
        "bom.csv": ";".join(BOM_COLUMNS),
        "notes.csv": ";".join(NOTE_COLUMNS),
    }


def test_no_raw_file_reveals_a_true_id_a_label_or_a_defect_tag(generated: tuple[Path, Path]) -> None:
    raw, truth_path = generated
    truth = load_ground_truth(truth_path)
    forbidden = {"TRUE-", *(label.planted_as for label in truth.backtest), *(defect.defect_type for defect in truth.defects)}
    forbidden -= {"new"}  # an ordinary word, e.g. "new region"
    for path in raw.iterdir():
        text = path.read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in text, f"{path.name} contains {word!r}"
        assert "\r" not in text and not text.startswith("\ufeff")


# --- isolation -----------------------------------------------------------------------------------


def bomreuse_imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "bomreuse":
            parts = node.module.split(".")
            imported |= {parts[1]} if len(parts) > 1 else {alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[1] for alias in node.names if alias.name.startswith("bomreuse.")}
    return imported


@pytest.mark.parametrize("module", GENERATOR_MODULES)
def test_the_generator_side_imports_no_pipeline_module(module: str) -> None:
    imported = bomreuse_imports(SRC / module)
    for forbidden in ("resolve", "normalize", "signatures"):
        assert forbidden not in imported, (
            f"{module} imports bomreuse.{forbidden}. Identity is owned by the generator and must share nothing "
            f"with the code it is scored against, or the score becomes circular (docs/ARCHITECTURE.md A3)."
        )
    assert imported <= ALLOWED_IMPORTS, f"{module} imports {sorted(imported - ALLOWED_IMPORTS)}"


def test_the_ground_truth_schema_depends_on_nothing() -> None:
    assert bomreuse_imports(SRC / "ground_truth.py") == set()


def test_no_source_file_holds_a_ground_truth_path() -> None:
    """docs/ARCHITECTURE.md A5: the path is an argument. Violating it must require changing a signature."""
    for path in SRC.glob("*.py"):
        assert "data/ground_truth" not in path.read_text(encoding="utf-8"), path.name


# --- the bridge: declared labels against the verdict rule ------------------------------------------

BEST_FIRST = (Verdict.IDENTICAL, Verdict.REUSABLE, Verdict.SPECIFIC)
LABEL_OF = {Verdict.IDENTICAL: "reused", Verdict.REUSABLE: "reusable", Verdict.SPECIFIC: "new"}


def true_signatures() -> dict[tuple[str, str], Signature]:
    """`(variant, raw sub-assembly reference) -> signature over true ids`, from the true model."""
    model = build_true_model(SPEC)
    signatures: dict[tuple[str, str], Signature] = {}
    for (variant_id, name), counts in model.contents.items():
        by_id = {model.parts[reference].true_id: quantity for reference, quantity in counts.items()}
        units = {model.parts[reference].true_id: model.parts[reference].definition.base_unit for reference in counts}
        signatures[(variant_id, model.sub_assembly_refs[(variant_id, name)])] = Signature.from_counts(by_id, units)
    return signatures


def as_tuples(diff: Diff) -> tuple[list[tuple[str, float, str]], list[tuple[str, float, str]], list[tuple[str, float, float]]]:
    return (
        [(i.true_component_id, i.quantity, i.unit) for i in diff.added],
        [(i.true_component_id, i.quantity, i.unit) for i in diff.removed],
        [(c.true_component_id, c.left, c.right) for c in diff.quantity_changed],
    )


def rule_as_tuples(result: Comparison) -> tuple[list[tuple[str, float, str]], list[tuple[str, float, str]], list[tuple[str, float, float]]]:
    return (
        [(i.component, i.quantity, i.unit) for i in result.diff.added],
        [(i.component, i.quantity, i.unit) for i in result.diff.removed],
        [(c.component, c.left.quantity, c.right.quantity) for c in result.diff.quantity_changed],
    )


@pytest.fixture(scope="module")
def truth(generated: tuple[Path, Path]) -> GroundTruth:
    return load_ground_truth(generated[1])


def test_every_declared_answer_is_the_one_the_verdict_rule_gives_on_the_true_content(truth: GroundTruth) -> None:
    """Two independent statements of the story: the catalogue's declarations, and `signatures.compare`.

    When they disagree, fix the catalogue — never the thresholds (DECISIONS.md 17).
    """
    signatures = true_signatures()
    older = {key: signature for key, signature in signatures.items() if key[0] != truth.newest_variant}
    assert len(truth.backtest) == sum(key[0] == truth.newest_variant for key in signatures)

    label: BacktestLabel
    for label in truth.backtest:
        newest = signatures[(label.variant_id, label.sub_assembly_ref)]
        results = {key: compare(ancestor, newest, SPEC.thresholds) for key, ancestor in older.items()}
        best = min((result.verdict for result in results.values()), key=BEST_FIRST.index)
        hint = f"{label.sub_assembly_designation}: fix the catalogue, never the thresholds (DECISIONS.md 17)"

        assert LABEL_OF[best] == label.label, f"the rule says {best}, the catalogue declares {label.label}. {hint}"
        reaching = {key for key, result in results.items() if result.verdict == best} if best != Verdict.SPECIFIC else set()
        declared = {(ancestor.variant_id, ancestor.sub_assembly_ref) for ancestor in label.ancestors}
        assert declared == reaching, f"ancestors declared {sorted(declared)}, the rule reaches {sorted(reaching)}. {hint}"

        for ancestor in label.ancestors:
            if ancestor.diff is not None:
                result = results[(ancestor.variant_id, ancestor.sub_assembly_ref)]
                assert as_tuples(ancestor.diff) == rule_as_tuples(result), f"diff against {ancestor.variant_id}. {hint}"


def test_the_exact_reference_search_has_something_to_find_and_something_to_get_wrong(truth: GroundTruth) -> None:
    """The baseline of #5 must not score zero by construction, nor be right whenever it answers."""
    kept = [label for label in truth.backtest if label.planted_as in ("open_reuse", "ref_reused_content_changed")]
    assert {label.label for label in kept} == {"reused", "reusable"}
    for label in kept:
        assert label.sub_assembly_ref in {ancestor.sub_assembly_ref for ancestor in label.ancestors}


# --- the committed dataset -------------------------------------------------------------------------

COMMITTED_RAW = ROOT / "data" / "raw"
COMMITTED_TRUTH = ROOT / "data" / "ground_truth" / "ground_truth.json"


def test_the_committed_dataset_is_what_the_generator_produces_today(generated: tuple[Path, Path]) -> None:
    """A catalogue edit without a regeneration would leave every later score measured on stale data.

    To fix: `uv run bomreuse generate --out data/raw --ground-truth data/ground_truth/ground_truth.json`.
    """
    assert files_of(COMMITTED_RAW, COMMITTED_TRUTH) == files_of(*generated)


def test_inputs_and_ground_truth_live_apart_and_alone() -> None:
    assert sorted(path.name for path in COMMITTED_RAW.iterdir()) == ["bom.csv", "notes.csv", "variants.csv"]
    assert [path.name for path in COMMITTED_TRUTH.parent.iterdir()] == ["ground_truth.json"]
