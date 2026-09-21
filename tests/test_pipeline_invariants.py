"""The pipeline's honesty invariants: it never sees the ground truth, never touches its inputs, and shows its work.

CLAUDE.md rule 2 — "The ground truth is for scoring only. The pipeline never reads `ground_truth`
files. Only the evaluation module does. A test enforces it." — and rule 3 — inputs are read-only.
These are the tests that sentence promises. Every score `evaluate` prints later is only worth
something if they hold, so they are written with the first pipeline stage, not after the last.

Two angles on the isolation, because each one alone can be fooled (docs/ARCHITECTURE.md A5):

- **runtime**: the pipeline runs on a copy of the raw files in a directory where no ground truth
  exists, which proves it does not *need* it; then with the real one laid out beside the raw
  files exactly as in the repository, which proves it does not *peek*: same artifact byte for
  byte, and no file of that name opened.
- **static**: no pipeline module so much as names it. It proves nobody wrote the peek — for the
  spellings a scanner can see (`'ground' + '_truth'` passes it; the runtime test is what catches that).

The third invariant is R11: every finding the pipeline writes names the rule that produced it,
carries that rule's confidence, and cites the rows it was read from. It is asserted on the file
`bomreuse run` writes, not on the objects behind it, because the file is what a reviewer opens.

The runtime tests run `bomreuse run` — the whole pipeline — so a stage added later is covered
without anyone remembering to add it here; the static one covers new modules by itself. The
artifacts they read are `artifacts.RUN_ARTIFACTS`, never a second list: an artifact a later issue
adds must not be able to appear outside the determinism and read-only checks.
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

from bomreuse.artifacts import FINDINGS_FILE, RUN_ARTIFACTS, load_findings
from bomreuse.cli import main
from bomreuse.rules import CATALOGUE

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "bomreuse"
COMMITTED_RAW = ROOT / "data" / "raw"

#: What is *not* the pipeline: the generator's side (it writes the ground truth), the entry point
#: (it routes the path `evaluate` is given, and nothing else), and `evaluate.py` — the only
#: legitimate reader, which arrives with #5 and is listed now so this rule is not edited, and
#: quietly widened, on the day it lands. Every other module of `src/bomreuse/` is scanned,
#: including the ones that do not exist yet.
NOT_PIPELINE = {"generate.py", "catalogue.py", "dirt.py", "ground_truth.py", "cli.py", "evaluate.py"}
#: `rglob`, so that a sub-package added later is scanned without anyone remembering to list it.
PIPELINE_MODULES = sorted(str(path.relative_to(SRC)) for path in SRC.rglob("*.py") if str(path.relative_to(SRC)) not in NOT_PIPELINE)
GENERATOR_SIDE = {"generate", "catalogue", "dirt", "ground_truth", "evaluate"}

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
    assert {"ingest.py", "normalize.py", "model.py", "artifacts.py", "resolve.py", "rules.py"} <= set(PIPELINE_MODULES)
    assert not NOT_PIPELINE & set(PIPELINE_MODULES)


@pytest.mark.parametrize("module", PIPELINE_MODULES)
def test_no_pipeline_module_names_the_ground_truth(module: str) -> None:
    found = mentions_ground_truth((SRC / module).read_text(encoding="utf-8"))
    assert found == [], (
        f"{module} names the ground truth: {found}. CLAUDE.md rule 2: the ground truth is for scoring only — "
        f"the pipeline never reads it, only the evaluation module does."
    )


def package_imports(source: str) -> set[str]:
    """The modules of this package a source imports, however the import is spelled.

    `from bomreuse.generate import x`, `from bomreuse import generate`, `import bomreuse.generate`
    — and the relative forms, `from .generate import x` and `from . import generate`, where
    `node.module` holds no package name at all and only `node.level` says the import is ours.
    """
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            parts = node.module.split(".") if node.module else []
            if node.level == 0 and parts[:1] == ["bomreuse"]:
                parts = parts[1:]
            elif node.level == 0:
                continue
            imported |= {parts[0]} if parts else {alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[1] for alias in node.names if alias.name.startswith("bomreuse.")}
    return imported


def dynamic_imports(source: str) -> list[str]:
    """`importlib` and `__import__` take a module name as a string a scanner cannot follow: neither has a use in the pipeline."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(alias.name.split(".")[0] == "importlib" for alias in node.names):
            found.append(f"line {node.lineno}: import importlib")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] == "importlib":
            found.append(f"line {node.lineno}: from {node.module} import …")
        elif isinstance(node, ast.Name) and node.id == "__import__":
            found.append(f"line {node.lineno}: __import__")
    return found


@pytest.mark.parametrize(
    "source",
    [
        "from bomreuse.generate import generate\n",
        "from bomreuse import generate\n",
        "from bomreuse import spec, generate as g\n",
        "import bomreuse.generate\n",
        "import bomreuse.generate as g\n",
        "from .generate import generate\n",
        "from . import generate\n",
        "from . import spec, generate as g\n",
        "from ..generate import generate\n",
        "def run():\n    from .generate import generate\n    return generate\n",
    ],
)
def test_the_import_scanner_sees_the_generator_however_it_is_imported(source: str) -> None:
    assert "generate" in package_imports(source), source


@pytest.mark.parametrize("source", ["import generate\n", "from csv import reader\n", "from bomreuse.model import RawText\n", "from .model import RawText\n", "from other.generate import x\n"])
def test_the_import_scanner_lets_the_rest_through(source: str) -> None:
    assert not package_imports(source) & GENERATOR_SIDE


@pytest.mark.parametrize("source", ["import importlib\n", "import importlib.util\n", "from importlib import import_module\n", "X = __import__('bomreuse.generate')\n"])
def test_the_import_scanner_flags_an_import_it_could_not_follow(source: str) -> None:
    assert dynamic_imports(source), source


@pytest.mark.parametrize("module", PIPELINE_MODULES)
def test_no_pipeline_module_imports_the_generator_side(module: str) -> None:
    """The other half of docs/ARCHITECTURE.md A3: the generator imports no pipeline module, and the reverse."""
    source = (SRC / module).read_text(encoding="utf-8")
    imported = package_imports(source)
    assert not imported & GENERATOR_SIDE, f"{module} imports {sorted(imported)}"
    assert dynamic_imports(source) == [], f"{module} imports by name, which no static check can follow"


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
    the pipeline needed one, it would fail here.
    """
    raw, out = tmp_path / "raw", tmp_path / "out"
    shutil.copytree(COMMITTED_RAW, raw)
    monkeypatch.chdir(tmp_path)
    assert not [path for path in tmp_path.rglob("*") if _MENTION.search(path.name)]

    assert main(["run", "--raw", "raw", "--out", "out"]) == 0
    assert sorted(path.name for path in out.iterdir()) == sorted(RUN_ARTIFACTS)


#: Paths opened while the list is armed. An audit hook cannot be removed once added, so it is
#: added once and only records between `_OPENED.clear()` and the end of the test that armed it.
_OPENED: list[str] = []
_ARMED: list[bool] = []


def _record_opens(event: str, args: tuple[object, ...]) -> None:
    if _ARMED and event == "open":
        _OPENED.append(os.fsdecode(args[0]) if isinstance(args[0], (str, bytes, os.PathLike)) else repr(args[0]))


def test_a_decoy_beside_the_raw_files_changes_nothing_and_is_never_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The differential half of the isolation: the repository's layout, with and without its ground truth.

    Same bytes out proves a peek had no effect; the audit hook proves there was no peek, which
    is the stronger claim — a pipeline could read the file and, today, do nothing with it.
    """
    assert not _MENTION.search(str(tmp_path)), "the temporary directory itself must not look like a hit"
    artifacts = {}
    for name in ("without", "with"):
        root = tmp_path / name
        shutil.copytree(COMMITTED_RAW, root / "data" / "raw")
    decoy = tmp_path / "with" / "data" / "ground_truth"
    shutil.copytree(ROOT / "data" / "ground_truth", decoy)
    before = snapshot(decoy)
    assert before, "the decoy is the committed ground truth: the most tempting one there is"

    sys.addaudithook(_record_opens)
    for name in ("without", "with"):
        monkeypatch.chdir(tmp_path / name)
        _OPENED.clear()
        _ARMED.append(True)
        try:
            assert main(["run", "--raw", "data/raw", "--out", "out"]) == 0
        finally:
            _ARMED.clear()
        assert [path for path in _OPENED if path.endswith("bom.csv")], "the hook sees what the run opens"
        assert [path for path in _OPENED if _MENTION.search(path)] == []
        artifacts[name] = [(tmp_path / name / "out" / artifact).read_bytes() for artifact in RUN_ARTIFACTS]

    assert artifacts["with"] == artifacts["without"]
    assert snapshot(decoy) == before


@pytest.mark.parametrize("command", ["normalize", "run"])
def test_a_run_leaves_its_inputs_exactly_as_they_were(tmp_path: Path, command: str) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    shutil.copytree(COMMITTED_RAW, raw)
    before = snapshot(raw)
    assert sorted(before) == ["bom.csv", "notes.csv", "variants.csv"]

    assert main([command, "--raw", str(raw), "--out", str(out)]) == 0

    assert snapshot(raw) == before, "same files, same sizes, same sha256: nothing changed, nothing was added"
    assert sorted(path.name for path in raw.iterdir()) == ["bom.csv", "notes.csv", "variants.csv"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["out", "raw"]


def test_the_committed_inputs_are_those_the_run_was_checked_on(tmp_path: Path) -> None:
    """The same guarantee on the real directory, since that is the one people will point the tool at."""
    before = snapshot(COMMITTED_RAW)
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(tmp_path / "out")]) == 0
    assert snapshot(COMMITTED_RAW) == before


# --- traceable findings ------------------------------------------------------------------------------


def test_every_finding_the_pipeline_writes_carries_its_rows_its_rule_and_a_confidence(tmp_path: Path) -> None:
    """R11, read off the artifact a reviewer opens rather than off the objects that made it."""
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    findings = load_findings(out / FINDINGS_FILE)
    assert findings, "a pipeline that emits no finding cannot show that its findings are traceable"

    for finding in findings:
        assert finding.rule_id in CATALOGUE, f"{finding.rule_id} is not in the rule catalogue: the finding cannot be traced"
        assert finding.confidence == CATALOGUE[finding.rule_id].confidence
        assert finding.source_rows, finding
        for row in finding.source_rows:
            assert row.source_file in ("variants.csv", "bom.csv", "notes.csv")
            assert row.row_number >= 1


# --- determinism -----------------------------------------------------------------------------------


@pytest.mark.parametrize("artifact", RUN_ARTIFACTS)
def test_the_artifacts_are_byte_identical_across_processes(tmp_path: Path, artifact: str) -> None:
    """Two interpreters with different hash seeds: this is the test that catches an iterated `set`."""
    written = []
    for hash_seed in ("1", "2"):
        out = tmp_path / hash_seed
        subprocess.run(
            [sys.executable, "-m", "bomreuse.cli", "run", "--raw", str(COMMITTED_RAW), "--out", str(out)],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
        )
        written.append((out / artifact).read_bytes())
    assert written[0] == written[1]
    assert str(tmp_path).encode() not in written[0], "the artifact does not say where it was written"
