"""Inconsistencies: one canonical component whose rows disagree on its unit, supplier or cost.

This is the second half of the client's question — *and where are the inconsistencies?* — and
the half that makes a reuse unsafe to take at face value. A part whose supplier or cost moves
from one variant to the next is still that part (Decision 26): it stays merged, it stays in the
signatures, and the disagreement is reported here as a finding for a human to settle.

The checks run on the **canonical components**, after `resolve` has split what it rejected
(`key#1`, `key#2`), not on the reference keys. A split part is then checked like any other
component, and a supplier or cost divergence inside one part of a rejected group — which
`resolve` reports for `review` groups only — is not lost.

Every value compared is one `normalize` has already read: units are SI (`m`, `kg`, `pcs`),
suppliers are their normalized name, costs a number. So `1000 mm` against `1 m`, or `12,50`
against `12.50`, is agreement, and what is left to disagree is the data itself. There is no
tolerance on cost: the dataset spec declares none, and this module does not invent one.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from typing import Final

from bomreuse.model import Attribute, BomLine, Finding, NormalizedDataset, Resolution, SourceRow
from bomreuse.rules import COST_CONFLICT, SUPPLIER_CONFLICT, UNIT_CONFLICT, Rule

#: The file every row this module cites comes from. `checks` opens no file; this is a label.
_BOM: Final[str] = "bom.csv"

#: How a variant is named in a message when the row carries none (Decision 28 keeps the row).
_NO_VARIANT: Final[str] = "(no variant)"

#: One check per attribute: the rule it emits, and what it reads off a row. The order is the
#: order findings are emitted in, so the artifact does not move between two runs.
_CHECKS: Final[dict[Attribute, tuple[Rule, Callable[[BomLine], object]]]] = {
    Attribute.UNIT: (UNIT_CONFLICT, lambda row: row.quantity.unit),
    Attribute.SUPPLIER: (SUPPLIER_CONFLICT, lambda row: row.supplier.normalized),
    Attribute.COST: (COST_CONFLICT, lambda row: row.unit_cost.normalized),
}

#: The rules this module emits, for a reader of the findings that needs to tell them apart.
CONFLICT_RULES: Final[dict[str, Attribute]] = {rule.id: attribute for attribute, (rule, _) in _CHECKS.items()}


def check(dataset: NormalizedDataset, resolution: Resolution) -> tuple[Finding, ...]:
    """One finding per canonical component and per attribute its rows disagree on."""
    line_of_row = {line.row_number: line for line in dataset.lines}
    findings: list[Finding] = []
    for component in resolution.components:
        rows = sorted((line_of_row[number] for number in component.rows if number in line_of_row), key=lambda row: row.row_number)
        for attribute, (rule, read) in _CHECKS.items():
            finding = _conflict(component.id, attribute, rule, read, rows)
            if finding is not None:
                findings.append(finding)
    return tuple(findings)


def conflicts_by_component(findings: Iterable[Finding]) -> dict[str, tuple[Attribute, ...]]:
    """Which attributes each component is in conflict on, read back from the findings this module wrote."""
    found: dict[str, list[Attribute]] = defaultdict(list)
    for finding in findings:
        attribute = CONFLICT_RULES.get(finding.rule_id)
        if attribute is not None:
            found[finding.subject].append(attribute)
    return {component: tuple(attributes) for component, attributes in found.items()}


def _conflict(component_id: str, attribute: Attribute, rule: Rule, read: Callable[[BomLine], object], rows: list[BomLine]) -> Finding | None:
    """The finding for one attribute of one component, or `None` when its rows agree.

    Only readable values are compared: an unreadable one is already a counted
    `NormalizationIssue`, and calling it a second value would report one defect twice under a
    name that does not fit it. The evidence is the earliest row showing each value, as in
    `resolve`; the message says which variants carry which value, which is what a reader acts on.
    """
    variants_of: dict[object, set[str]] = defaultdict(set)
    earliest: dict[object, BomLine] = {}
    for row in rows:
        value = read(row)
        if value is None or value == "":
            continue
        variants_of[value].add(row.variant_id or _NO_VARIANT)
        earliest.setdefault(value, row)
    if len(variants_of) < 2:
        return None

    said = "; ".join(f"{_shown(attribute, value)} in {', '.join(sorted(variants))}" for value, variants in variants_of.items())
    return rule.finding(
        subject=component_id,
        message=f"{_usual_spelling(rows)!r} (component {component_id}) has {len(variants_of)} different {attribute} values: {said}.",
        source_rows=tuple(sorted(SourceRow(source_file=_BOM, row_number=row.row_number, row_id=row.line_id) for row in earliest.values())),
    )


def _usual_spelling(rows: list[BomLine]) -> str:
    """The reference as the file writes it most often: what a reader searches the export for.

    The component id is a folded key (`11GHTCAB1E`), which no one types. Ties go to the first
    spelling in sort order, so the message does not move between two runs.
    """
    counts = Counter(row.component_ref.raw.strip() for row in rows)
    return min(counts, key=lambda spelling: (-counts[spelling], spelling))


def _shown(attribute: Attribute, value: object) -> str:
    if attribute is Attribute.COST and isinstance(value, float):
        return f"{value:.2f} EUR"
    return repr(value)
