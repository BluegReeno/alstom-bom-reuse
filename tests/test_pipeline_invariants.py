"""The pipeline's honesty invariants: it never sees the ground truth, and it never touches its inputs.

CLAUDE.md rule 2 — "The ground truth is for scoring only. The pipeline never reads `ground_truth`
files. Only the evaluation module does. A test enforces it." — and rule 3 — inputs are read-only.
These are the tests that sentence promises. Every score `evaluate` prints later is only worth
something if they hold, so they are written with the first pipeline stage, not after the last.

Two angles on the isolation, because each one alone can be fooled (docs/ARCHITECTURE.md A5):

- **runtime**: the pipeline runs on a copy of the raw files in a directory where no ground truth
  exists. It proves the pipeline does not *need* it — not that it would not peek if it could.
- **static**: no pipeline module so much as names it. It proves nobody wrote the peek — for the
  spellings a scanner can see.

Later issues extend the runtime test to `bomreuse run`; the static one covers new modules by itself.
"""

import ast
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bomreuse.cli import main
from bomreuse.model import NORMALIZED_FILE

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "bomreuse"
COMMITTED_RAW = ROOT / "data" / "raw"

#: What is *not* the pipeline: the generator's side (it writes the ground truth), the entry point
#: (it routes the path `evaluate` is given, and nothing else), and `evaluate.py` — the only
#: legitimate reader, which arrives with #5 and is listed now so this rule is not edited, and
#: quietly widened, on the day it lands. Every other module of `src/bomreuse/` is scanned,
#: including the ones that do not exist yet.
NOT_PIPELINE = {"generate.py", "catalogue.py", "dirt.py", "ground_truth.py", "cli.py", "evaluate.py"}
PIPELINE_MODULES = sorted(path.name for path in SRC.glob("*.py") if path.name not in NOT_PIPELINE)

_MENTION = re.compile(r"ground[\s_\-]*truth", re.IGNORECASE)


# --- the scanner -------------------------------------------------------------------------------


def mentions_ground_truth(source: str) -> list[str]:
    """Every place a module names the ground truth, outside its docstrings.

    Docstrings are exempt on purpose: "this module never reads the ground truth" is documentation,
    and forbidding the sentence would forbid stating the rule. Everything else counts — imports,
    identifiers, attributes, parameters, keywords, and string constants (a path is a string).
    Comments are not in the AST; they cannot open a file either.
    """
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    found: list[str] = []
    for node in ast.walk(tree):
        names: list[str | None] = []
        if isinstance(node, ast.Import):
            names = [part for alias in node.names for part in (alias.name, alias.asname)]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module, *(part for alias in node.names for part in (alias.name, alias.asname))]
        elif isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, ast.keyword):
            names = [node.arg]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Constant) and id(node) not in docstrings:
            if isinstance(node.value, str):
                names = [node.value]
            elif isinstance(node.value, bytes):
                names = [node.value.decode("utf-8", errors="replace")]
        for name in names:
            if name and _MENTION.search(name):
                found.append(f"line {getattr(node, 'lineno', '?')}: {type(node).__name__} {name!r}")
    return found


@pytest.mark.parametrize(
    "source",
    [
        "from bomreuse import ground_truth as gt\n",
        "from bomreuse.ground_truth import load_ground_truth\n",
        "import bomreuse.ground_truth\n",
        "from bomreuse import spec as ground_truth\n",
        "def run(raw, ground_truth_path):\n    return raw\n",
        "def run(raw):\n    return helper(raw, groundTruth=None)\n",
        "def run(raw):\n    return raw.ground_truth\n",
        "def load_ground_truth(path):\n    return path\n",
        "class GroundTruthReader:\n    pass\n",
        "GT = 'data/ground_truth/ground_truth.json'\n",
        "PATH = 'data/GROUND-TRUTH/x.json'\n",
        "def run(raw):\n    return open(f'{raw}/../ground_truth/x.json')\n",
        "MESSAGE = 'the ground truth is near'\n",
        "BLOB = b'ground_truth'\n",
        "def run(raw):\n    x = 1\n    'a string in the middle of a body is not a docstring: ground truth'\n    return x\n",
    ],
)
def test_the_scanner_flags_every_way_of_naming_the_ground_truth(source: str) -> None:
    """A scanner that cannot fail proves nothing."""
    assert mentions_ground_truth(source), source


@pytest.mark.parametrize(
    "source",
    [
        '"""This module never reads the ground truth."""\n\nX = 1\n',
        'def run(raw):\n    """Never handed the ground_truth path (A5)."""\n    return raw\n',
        'class Reader:\n    """Knows nothing of data/ground_truth/."""\n\n    def read(self):\n        """Nor of the ground truth."""\n',
        "# the ground truth is for scoring only\nX = 'data/raw'\n",
        "def run(raw):\n    return raw.ground, raw.truth, 'truth on the ground'\n",
    ],
)
def test_the_scanner_lets_documentation_and_unrelated_words_through(source: str) -> None:
    assert mentions_ground_truth(source) == []


# --- static isolation ----------------------------------------------------------------------------


def test_the_new_pipeline_modules_are_among_those_scanned() -> None:
    assert {"ingest.py", "normalize.py", "model.py"} <= set(PIPELINE_MODULES)
    assert not NOT_PIPELINE & set(PIPELINE_MODULES)


@pytest.mark.parametrize("module", PIPELINE_MODULES)
def test_no_pipeline_module_names_the_ground_truth(module: str) -> None:
    found = mentions_ground_truth((SRC / module).read_text(encoding="utf-8"))
    assert found == [], (
        f"{module} names the ground truth: {found}. CLAUDE.md rule 2: the ground truth is for scoring only — "
        f"the pipeline never reads it, only the evaluation module does."
    )


@pytest.mark.parametrize("module", PIPELINE_MODULES)
def test_no_pipeline_module_imports_the_generator_side(module: str) -> None:
    """The other half of docs/ARCHITECTURE.md A3: the generator imports no pipeline module, and the reverse."""
    imported: set[str] = set()
    for node in ast.walk(ast.parse((SRC / module).read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "bomreuse":
            parts = node.module.split(".")
            imported |= {parts[1]} if len(parts) > 1 else {alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[1] for alias in node.names if alias.name.startswith("bomreuse.")}
    assert not imported & {"generate", "catalogue", "dirt", "ground_truth", "evaluate"}, f"{module} imports {sorted(imported)}"


# --- runtime isolation, and read-only inputs -------------------------------------------------------


def snapshot(directory: Path) -> dict[str, tuple[int, str]]:
    """relative path -> (size, sha256), for every file under `directory`."""
    return {
        str(path.relative_to(directory)): (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_the_pipeline_runs_where_no_ground_truth_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A copy of the raw files, alone in a temporary directory, with the working directory moved there.

    No relative path can reach the repository, and nothing under `tmp_path` is a ground truth: if
    the pipeline needed one, it would fail here. Later issues extend this to `bomreuse run`.
    """
    raw, out = tmp_path / "raw", tmp_path / "out"
    shutil.copytree(COMMITTED_RAW, raw)
    monkeypatch.chdir(tmp_path)
    assert not [path for path in tmp_path.rglob("*") if _MENTION.search(path.name)]

    assert main(["normalize", "--raw", "raw", "--out", "out"]) == 0
    assert (out / NORMALIZED_FILE).is_file()


def test_a_run_leaves_its_inputs_exactly_as_they_were(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    shutil.copytree(COMMITTED_RAW, raw)
    before = snapshot(raw)
    assert sorted(before) == ["bom.csv", "notes.csv", "variants.csv"]

    assert main(["normalize", "--raw", str(raw), "--out", str(out)]) == 0

    assert snapshot(raw) == before, "same files, same sizes, same sha256: nothing changed, nothing was added"
    assert sorted(path.name for path in raw.iterdir()) == ["bom.csv", "notes.csv", "variants.csv"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["out", "raw"]


def test_the_committed_inputs_are_those_the_run_was_checked_on(tmp_path: Path) -> None:
    """The same guarantee on the real directory, since that is the one people will point the tool at."""
    before = snapshot(COMMITTED_RAW)
    assert main(["normalize", "--raw", str(COMMITTED_RAW), "--out", str(tmp_path / "out")]) == 0
    assert snapshot(COMMITTED_RAW) == before


# --- determinism -----------------------------------------------------------------------------------


def test_the_artifact_is_byte_identical_across_processes(tmp_path: Path) -> None:
    """Two interpreters with different hash seeds: this is the test that catches an iterated `set`."""
    artifacts = []
    for hash_seed in ("1", "2"):
        out = tmp_path / hash_seed
        subprocess.run(
            [sys.executable, "-m", "bomreuse.cli", "normalize", "--raw", str(COMMITTED_RAW), "--out", str(out)],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
        )
        artifacts.append((out / NORMALIZED_FILE).read_bytes())
    assert artifacts[0] == artifacts[1]
    assert str(tmp_path).encode() not in artifacts[0], "the artifact does not say where it was written"
