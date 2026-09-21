"""Duplicate references to canonical components: rules only, and a verdict on the group.

`normalize` has already done the only string work there is. `reference_key` uppercases, folds
`O→0`, `I→1`, `L→1`, then drops non-alphanumerics (DECISIONS.md 27); this module **inherits that
key and never recomputes one**. Rows sharing it form one candidate group, and everything below
decides what to do with that group — never how close two strings look.

There is no string-distance matching here, and none anywhere in the pipeline
(docs/ARCHITECTURE.md A2). In a Bill of Materials two references differing by one character are
often genuinely different parts, and a false *reused* is the worst error this tool can make: it
is precisely what the tool claims to find. Rules-only cannot manufacture one. The cost is that a
transposition (`BGI-2031` → `BGI-2013`) and a missing character stay out of reach by
construction — named in the README's Known limits, not hidden.

So the verdict rates the **coherence of the group the key formed**, not the confidence of a
match that does not exist (DECISIONS.md 20):

- `auto` — the rows agree on everything; the group is one component.
- `review` — they share a key but disagree on designation, unit, supplier or cost. Still one
  component, and a finding: a part whose supplier or cost moves between variants is the same
  part, and the divergence is what the client wants told (Decision 26).
- `reject` — the designations describe different products; the group is split back apart, one
  canonical component per designation.

The only judgement in the module is that last line, and it is made without string distance: two
designations are spellings of one product when one is the other **plus words**, and name two
products as soon as each brings a word the other does not. Reading `floor rail, stainless steel`
against `mounting rail, aluminium, mark 1` needs nothing finer, and nothing finer would be
honest on free text.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final, TypeGuard

from bomreuse.model import (
    Attribute,
    BomLine,
    CandidateGroup,
    CanonicalComponent,
    Finding,
    GroupVerdict,
    NormalizedDataset,
    Resolution,
    SourceRow,
)
from bomreuse.normalize import reference_key
from bomreuse.rules import DUPLICATE_REFERENCE, GROUP_CONFLICT, GROUP_SPLIT

#: The file every row this module cites comes from. `resolve` opens no file; this is a label.
_BOM: Final[str] = "bom.csv"

#: What each attribute of the A2 table is read off a row. Both the verdict and the evidence go
#: through it, so a finding can never cite a row for an attribute the verdict did not look at.
_ATTRIBUTES: Final[dict[Attribute, Callable[[BomLine], object]]] = {
    Attribute.DESIGNATION: lambda row: row.designation.normalized,
    Attribute.UNIT: lambda row: row.quantity.unit,
    Attribute.SUPPLIER: lambda row: row.supplier.normalized,
    Attribute.COST: lambda row: row.unit_cost.normalized,
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """What a raw reference string found in the resolved catalogue.

    `components` holds more than one entry only when the group was rejected, and then the token
    is genuinely ambiguous: the caller is shown the choice rather than handed a guess.
    """

    raw_token: str
    reference_key: str
    components: tuple[CanonicalComponent, ...]


def resolve(dataset: NormalizedDataset) -> tuple[Resolution, tuple[Finding, ...]]:
    """Every candidate group of the normalized dataset, judged, plus the findings it produced.

    The groups are `dataset.components` — one per reference key, formed by `normalize`. Taking
    them rather than regrouping the lines is what makes "inherit the key" a property of the code
    and not a promise.
    """
    rows_by_key: dict[str, list[BomLine]] = defaultdict(list)
    for line in dataset.lines:
        if line.child_id:
            rows_by_key[line.child_id].append(line)

    groups = tuple(_judge(component.id, rows_by_key[component.id]) for component in dataset.components)
    findings = tuple(finding for group in groups for finding in _findings(group, rows_by_key[group.reference_key]))
    return Resolution(groups=groups), findings


def match_reference(resolution: Resolution, raw_token: str) -> Candidate | None:
    """The one way a string becomes a canonical component (docs/ARCHITECTURE.md A7).

    `link.py` resolves the raw references the notes cite through this function, and it
    is the only caller outside this module — a test asserts it, so that the day a second matcher
    is written it shows up as a failing test rather than as a quiet divergence.

    The resolution to look in is a parameter because this module holds no state: a catalogue
    hidden in a module global would be one more thing a stage could forget to rebuild.
    """
    key = reference_key(raw_token)
    if not key:
        return None
    for group in resolution.groups:
        if group.reference_key == key:
            return Candidate(raw_token=raw_token, reference_key=key, components=group.components)
    return None


# --- the verdict --------------------------------------------------------------------------------


def _judge(key: str, rows: list[BomLine]) -> CandidateGroup:
    diverging = _diverging(rows)
    designations = _distinct(row.designation.normalized for row in rows)
    if len(designations) > 1 and not _describe_one_product(designations):
        return CandidateGroup(reference_key=key, verdict=GroupVerdict.REJECT, diverging=diverging, components=_split(key, rows))
    verdict = GroupVerdict.REVIEW if diverging else GroupVerdict.AUTO
    return CandidateGroup(reference_key=key, verdict=verdict, diverging=diverging, components=(_component(key, key, rows),))


def _diverging(rows: list[BomLine]) -> tuple[Attribute, ...]:
    """Which attributes the rows disagree about.

    Only readable values are compared. A value `normalize` could not read is `None`, it is
    already counted as a `NormalizationIssue`, and calling it a disagreement would report the
    same defect twice under a name that does not fit it.
    """
    return tuple(attribute for attribute, read in _ATTRIBUTES.items() if len(_distinct(read(row) for row in rows)) > 1)


def _describe_one_product(designations: list[str]) -> bool:
    """Whether the group's designations are spellings of one product, or name several.

    One product when the word sets nest — `sidewall panel` inside `sidewall panel, extruded`:
    one designation is the other said at greater length. Two products as soon as a pair brings
    words to each other, which is what `air outlet grille, left-hand` and `wall ventilation
    grille type 11` do.

    Nesting is the only comparison made, and it is not a distance: it reads whole words, never
    characters, so it can neither measure how close two strings look nor merge on a typo.
    """
    words = [_words(designation) for designation in designations]
    return all(left <= right or right <= left for left, right in _pairs(words))


def _words(text: str) -> frozenset[str]:
    """The words of a normalized designation: `str.isalnum`, as in `normalize.reference_key`."""
    return frozenset("".join(character if character.isalnum() else " " for character in text).split())


def _pairs[T](values: list[T]) -> Iterable[tuple[T, T]]:
    return ((values[i], values[j]) for i in range(len(values)) for j in range(i + 1, len(values)))


# --- the components a group resolves to -----------------------------------------------------------


def _split(key: str, rows: list[BomLine]) -> tuple[CanonicalComponent, ...]:
    """One canonical component per designation, numbered `key#1`, `key#2` in designation order.

    A row whose designation `normalize` could not read becomes its own part: it carries no
    evidence of which product it belongs to, and attaching it to one of them would be a guess.
    """
    by_part: dict[tuple[str, int], list[BomLine]] = defaultdict(list)
    for row in rows:
        by_part[_part_of(row)].append(row)
    return tuple(_component(f"{key}#{number}", key, by_part[part]) for number, part in enumerate(sorted(by_part), start=1))


def _part_of(row: BomLine) -> tuple[str, int]:
    """Which part a row belongs to: its designation, or the row alone when it has none to read."""
    designation = row.designation.normalized
    return (designation, 0) if _readable(designation) else ("", row.row_number)


def _component(component_id: str, key: str, rows: list[BomLine]) -> CanonicalComponent:
    return CanonicalComponent(
        id=component_id,
        reference_key=key,
        raw_references=tuple(sorted({row.component_ref.raw for row in rows})),
        designations=tuple(sorted(_distinct(row.designation.normalized for row in rows))),
        rows=tuple(sorted(row.row_number for row in rows)),
    )


# --- the findings ---------------------------------------------------------------------------------


def _findings(group: CandidateGroup, rows: list[BomLine]) -> list[Finding]:
    findings = [
        DUPLICATE_REFERENCE.finding(
            subject=component.id,
            message=f"{len(component.raw_references)} spellings of one reference are one component: {_quoted(component.raw_references)}.",
            source_rows=_first_row_per(_rows_of(component, rows), lambda row: row.component_ref.raw),
        )
        for component in group.components
        if len(component.raw_references) > 1
    ]
    if group.verdict is GroupVerdict.REVIEW:
        findings.append(
            GROUP_CONFLICT.finding(
                subject=group.reference_key,
                message=f"Rows sharing the reference {_quoted(group.components[0].raw_references)} disagree on {_listed(group.diverging)}.",
                source_rows=_conflict_rows(group, rows),
            )
        )
    elif group.verdict is GroupVerdict.REJECT:
        designations = sorted({designation for part in group.components for designation in part.designations})
        findings.append(
            GROUP_SPLIT.finding(
                subject=group.reference_key,
                message=(
                    f"References {_quoted(sorted({reference for part in group.components for reference in part.raw_references}))} "
                    f"share a canonical key but designate {len(designations)} different products: "
                    f"{_quoted(designations)}. Kept apart."
                ),
                source_rows=_source_rows(_rows_of(part, rows)[0] for part in group.components),
            )
        )
    return findings


def _conflict_rows(group: CandidateGroup, rows: list[BomLine]) -> tuple[SourceRow, ...]:
    """One row per distinct value of each diverging attribute: what a reader must open to judge it."""
    component_rows = _rows_of(group.components[0], rows)
    cited = {row for attribute in group.diverging for row in _first_row_per(component_rows, _ATTRIBUTES[attribute])}
    return tuple(sorted(cited))


def _first_row_per(rows: list[BomLine], read: Callable[[BomLine], object]) -> tuple[SourceRow, ...]:
    """The earliest row showing each distinct value: the evidence, without the forty rows behind it."""
    earliest: dict[object, BomLine] = {}
    for row in rows:
        value = read(row)
        if _readable(value):
            earliest.setdefault(value, row)
    return _source_rows(earliest.values())


def _rows_of(component: CanonicalComponent, rows: list[BomLine]) -> list[BomLine]:
    belongs = set(component.rows)
    return sorted((row for row in rows if row.row_number in belongs), key=lambda row: row.row_number)


def _source_rows(rows: Iterable[BomLine]) -> tuple[SourceRow, ...]:
    return tuple(sorted(SourceRow(source_file=_BOM, row_number=row.row_number, row_id=row.line_id) for row in rows))


# --- small helpers ------------------------------------------------------------------------------


def _readable[T](value: T | None) -> TypeGuard[T]:
    """Whether `normalize` could read this value.

    `None` and `""` mean *unreadable*, not a value: `normalize` has already counted them, and
    counting an unreadable supplier as a second supplier would invent a conflict. Every read of
    a `*.normalized` field in this module goes through here.
    """
    return value is not None and value != ""


def _distinct[T](values: Iterable[T | None]) -> list[T]:
    """The distinct readable values, in the order the rows show them."""
    seen: list[T] = []
    for value in values:
        if _readable(value) and value not in seen:
            seen.append(value)
    return seen


def _quoted(values: Iterable[object]) -> str:
    return ", ".join(repr(value) for value in values)


def _listed(values: Iterable[object]) -> str:
    return ", ".join(str(value) for value in values)
