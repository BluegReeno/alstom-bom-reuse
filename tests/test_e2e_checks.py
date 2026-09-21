"""End to end: generate a dataset with a test seed, run the pipeline, find the planted conflicts.

The ground truth is read here, by the test, and never by the pipeline. A planted conflict is
found when a finding of the matching rule cites rows of the conflicting lines; and no conflict
finding cites a row the ground truth does not list as evidence of a planted conflict of its type.
"""

from collections import defaultdict
from pathlib import Path

import pytest

from bomreuse.artifacts import FINDINGS_FILE, RESOLUTION_FILE, load_dataset, load_findings, load_resolution
from bomreuse.checks import CONFLICT_RULES
from bomreuse.cli import main
from bomreuse.ground_truth import load_ground_truth
from bomreuse.model import Attribute

#: Not the default seed: the committed dataset is checked elsewhere, and a second seed moves the dirt.
TEST_SEED = 7

_DEFECT_TYPE: dict[Attribute, str] = {
    Attribute.UNIT: "unit_conflict",
    Attribute.SUPPLIER: "supplier_conflict",
    Attribute.COST: "cost_conflict",
}


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("e2e_checks")
    raw, out = root / "raw", root / "out"
    assert main(["generate", "--out", str(raw), "--ground-truth", str(root / "ground_truth.json"), "--seed", str(TEST_SEED)]) == 0
    assert main(["run", "--raw", str(raw), "--out", str(out)]) == 0
    return root


def _planted(root: Path) -> dict[str, dict[str, set[str]]]:
    """defect type -> true component -> every line id the ground truth cites for it."""
    planted: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for defect in load_ground_truth(root / "ground_truth.json").defects:
        if defect.defect_type in _DEFECT_TYPE.values():
            planted[defect.defect_type][defect.true_component_id].update(defect.evidence_line_ids)
    return planted


def _found(root: Path) -> dict[str, list[set[str]]]:
    """defect type -> for each conflict finding, the line ids of every row of its component."""
    dataset = load_dataset(root / "out" / "normalized.json")
    line_id = {line.row_number: line.line_id for line in dataset.lines}
    rows_of = {component.id: component.rows for component in load_resolution(root / "out" / RESOLUTION_FILE).components}
    found: dict[str, list[set[str]]] = defaultdict(list)
    for finding in load_findings(root / "out" / FINDINGS_FILE):
        if finding.rule_id in CONFLICT_RULES:
            found[_DEFECT_TYPE[CONFLICT_RULES[finding.rule_id]]].append({line_id[row] for row in rows_of[finding.subject]})
    return found


@pytest.mark.parametrize("defect_type", sorted(_DEFECT_TYPE.values()))
def test_every_planted_conflict_is_found(run: Path, defect_type: str) -> None:
    planted, found = _planted(run)[defect_type], _found(run)[defect_type]
    assert planted, f"the generator planted no {defect_type}: the test would prove nothing"
    for true_id, evidence in planted.items():
        assert any(evidence & lines for lines in found), f"{defect_type} on {true_id} not found"


@pytest.mark.parametrize("defect_type", sorted(_DEFECT_TYPE.values()))
def test_no_conflict_is_reported_where_none_was_planted(run: Path, defect_type: str) -> None:
    evidence = set().union(*_planted(run)[defect_type].values())
    cited = {
        row.row_id
        for finding in load_findings(run / "out" / FINDINGS_FILE)
        if CONFLICT_RULES.get(finding.rule_id) is not None and _DEFECT_TYPE[CONFLICT_RULES[finding.rule_id]] == defect_type
        for row in finding.source_rows
    }
    assert cited and cited <= evidence
