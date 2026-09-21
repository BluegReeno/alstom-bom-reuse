"""Inconsistencies: rows of one component that disagree, and notes that contradict the BOM.

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

The second half of the module reads the other input the client sent: the notes. A fact the notes
layer extracted and `link` placed on a canonical component becomes a finding when the BOM still
carries that component — a part declared obsolete, a part said to have been replaced, a part
forbidden on some configuration, and the export listing it anyway. The contradiction is with the
BOM as a whole, not with a date or a variant: a note's scope is free text (`ne pas utiliser sur
les rames 4 caisses`), and deciding which variants it names would be inference, not a check.
So the finding says what the note asserts, quotes the scope as written, lists the variants the
BOM carries the part on, and leaves the judgement to the human it is a proposal for (Decision 8).

These findings sit on the bottom rung of the confidence ladder whichever reader produced the
fact, and each one names that reader: a claim read out of free text is not a claim read off two
rows sharing a key.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from typing import Final

from bomreuse.model import (
    Attribute,
    BomLine,
    FactKind,
    Finding,
    NormalizedDataset,
    NoteFact,
    NoteFacts,
    Resolution,
    SourceRow,
)
from bomreuse.rules import (
    COST_CONFLICT,
    NOTE_OBSOLESCENCE,
    NOTE_REPLACEMENT,
    NOTE_RESTRICTION,
    SUPPLIER_CONFLICT,
    UNIT_CONFLICT,
    Rule,
)

#: The files the rows this module cites come from. `checks` opens neither; these are labels.
_BOM: Final[str] = "bom.csv"
_NOTES: Final[str] = "notes.csv"

#: How a variant is named in a message when the row carries none (Decision 28 keeps the row).
_NO_VARIANT: Final[str] = "(no variant)"

#: One check per attribute: the rule it emits, and what it reads off a row. The order is the
#: order findings are emitted in, so the artifact does not move between two runs.
_CHECKS: Final[dict[Attribute, tuple[Rule, Callable[[BomLine], object]]]] = {
    Attribute.UNIT: (UNIT_CONFLICT, lambda row: row.quantity.unit),
    Attribute.SUPPLIER: (SUPPLIER_CONFLICT, lambda row: row.supplier.normalized),
    Attribute.COST: (COST_CONFLICT, lambda row: row.unit_cost.normalized),
}

#: The rules this module emits on the BOM alone, for a reader that needs to tell them apart.
CONFLICT_RULES: Final[dict[str, Attribute]] = {rule.id: attribute for attribute, (rule, _) in _CHECKS.items()}

#: One rule per kind of fact a note can assert, and the same mapping read backwards by
#: `notes_by_component`. A kind without a rule would be a fact extracted and never reported.
_NOTE_RULES: Final[dict[FactKind, Rule]] = {
    FactKind.OBSOLESCENCE: NOTE_OBSOLESCENCE,
    FactKind.REPLACEMENT: NOTE_REPLACEMENT,
    FactKind.RESTRICTION: NOTE_RESTRICTION,
}

NOTE_RULES: Final[dict[str, FactKind]] = {rule.id: kind for kind, rule in _NOTE_RULES.items()}


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


# --- what the notes contradict ----------------------------------------------------------------


def check_notes(dataset: NormalizedDataset, resolution: Resolution, note_facts: NoteFacts) -> tuple[Finding, ...]:
    """One finding per linked fact and per component it reached.

    A fact the notes layer could not place reaches nothing and produces nothing here: it stays in
    the note-facts artifact, where it is counted, rather than becoming a finding about a part the
    BOM does not carry. A fact on an ambiguous reference — one `resolve` split into two products
    — produces one finding per part, because the note applies to whichever of them it meant.
    """
    line_of_row = {line.row_number: line for line in dataset.lines}
    rows_of = {
        component.id: sorted((line_of_row[number] for number in component.rows if number in line_of_row), key=lambda row: row.row_number)
        for component in resolution.components
    }
    return tuple(
        _contradiction(note_facts.reader, linked.fact, component_id, rows_of.get(component_id, []))
        for linked in note_facts.facts
        for component_id in linked.components
    )


def notes_by_component(findings: Iterable[Finding]) -> dict[str, tuple[FactKind, ...]]:
    """What the notes say about each component, read back from the findings this module wrote."""
    found: dict[str, list[FactKind]] = defaultdict(list)
    for finding in findings:
        kind = NOTE_RULES.get(finding.rule_id)
        if kind is not None and kind not in found[finding.subject]:
            found[finding.subject].append(kind)
    return {component: tuple(kinds) for component, kinds in found.items()}


def _contradiction(reader: str, fact: NoteFact, component_id: str, rows: list[BomLine]) -> Finding:
    """The finding for one fact on one component: what the note asserts, against what the BOM lists.

    The evidence is the note's row and the earliest BOM row of each variant carrying the part —
    the rows a reader opens to judge it, not the forty lines behind them, as everywhere else here.
    """
    variants = sorted({row.variant_id or _NO_VARIANT for row in rows})
    carried = f"the BOM carries component {component_id} on {', '.join(variants)}" if variants else f"component {component_id} is in the BOM"
    return _NOTE_RULES[fact.kind].finding(
        subject=component_id,
        message=f"note {fact.note_id} {_asserts(fact)}, and {carried}. Read by {reader}.",
        source_rows=(SourceRow(source_file=_NOTES, row_number=fact.row_number, row_id=fact.note_id), *_first_row_per_variant(rows)),
    )


def _asserts(fact: NoteFact) -> str:
    """What the note says, in the words of the fact rather than of the rule it triggered."""
    if fact.kind is FactKind.REPLACEMENT:
        replaced_by = f" by {fact.replacement_ref!r}" if fact.replacement_ref else ""
        return f"says {fact.component_ref!r} has been replaced{replaced_by}"
    if fact.kind is FactKind.OBSOLESCENCE:
        return f"declares {fact.component_ref!r} obsolete"
    restriction = f": {fact.scope!r}" if fact.scope else ""
    return f"restricts the use of {fact.component_ref!r}{restriction}"


def _first_row_per_variant(rows: list[BomLine]) -> tuple[SourceRow, ...]:
    earliest: dict[str, BomLine] = {}
    for row in rows:
        earliest.setdefault(row.variant_id or _NO_VARIANT, row)
    return tuple(sorted(SourceRow(source_file=_BOM, row_number=row.row_number, row_id=row.line_id) for row in earliest.values()))
