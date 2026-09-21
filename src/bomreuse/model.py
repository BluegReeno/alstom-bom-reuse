"""The project's single set of types: raw rows, entities, and the artifacts they round-trip through.

Every stage passes these frozen dataclasses, and the JSON files in `out/` are serialized from
them and read back into them — no schema library mirrors them (docs/ARCHITECTURE.md A4, A8).
The types live here and the rules live in the stages: `Component` is `normalize`'s output and
`CandidateGroup` is `resolve`'s, and both are read back by whoever is handed the file.

Two ideas shape the module:

- **Raw and normalized live side by side.** A value the tool read keeps the exact characters of
  the file next to what the tool made of them, so any later finding can be traced to the export
  and nobody can "clean" away a defect before it is seen (PRD R3). `normalized is None` means
  the value could not be read; a `NormalizationIssue` says why.
- **Variability is carried by the line.** A `BomLine` is an n-ary relation (variant, parent,
  child, quantity, unit). `Component` and `Supplier` never name a variant: one entity, however
  many variants use it.

A `Component` here is a **candidate group** — everything sharing one reference key. Whether the
group is one product (`auto`), one product with diverging attributes (`review`) or two products
(`reject`) is decided by `resolve`, which is why the designations seen are kept on it; its answer
comes back as a `CandidateGroup` holding one `CanonicalComponent`, or several after a split.

A `Finding` is what the tool proposes to a human (Decision 8): it names the rule that produced
it, the confidence that rule declares, and the file rows it was read from (R11). It is built by
`rules.Rule.finding`, not here: this module imports nothing from the package and stays the leaf
every other one can depend on.

The raw rows live here rather than in `ingest.py` because the naive baselines of #5 consume them
and have no reason to import a reader.

Reading back is written by hand, one small function per type: reflection over field types would
be shorter and much harder to read in five minutes. Every leaf is checked as it is read, not
only the keys — a stage told to expect `ModelError` must not meet a `TypeError` instead.
"""

import dataclasses
import json
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

#: The names of the artifacts inside the output directory the CLI is given.
NORMALIZED_FILE: Final[str] = "normalized.json"
RESOLUTION_FILE: Final[str] = "resolution.json"
FINDINGS_FILE: Final[str] = "findings.json"
SIGNATURES_FILE: Final[str] = "signatures.json"
PREDICTIONS_FILE: Final[str] = "predictions.json"

#: Everything `bomreuse run` writes, in the order the pipeline produces it. Said once, here: the
#: CLI writes this list and checks it against the raw directory, and the tests that watch
#: determinism and the read-only inputs read it rather than a copy of it — so an artifact a later
#: issue adds is covered by all of them without a hand edit anywhere.
RUN_ARTIFACTS: Final[tuple[str, ...]] = (NORMALIZED_FILE, RESOLUTION_FILE, FINDINGS_FILE, SIGNATURES_FILE, PREDICTIONS_FILE)

#: Written into every artifact and checked on load: a later issue that changes a type bumps it,
#: so a stale file in `out/` is refused instead of half-read. One version for the whole set of
#: types, since one stage reads what the previous one wrote.
SCHEMA_VERSION: Final[str] = "1"


class ModelError(ValueError):
    """A serialized dataset does not have the shape of these types."""


# --- raw / normalized pairs ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawText:
    raw: str
    normalized: str


@dataclass(frozen=True, slots=True)
class RawNumber:
    raw: str
    normalized: float | None


@dataclass(frozen=True, slots=True)
class RawInt:
    raw: str
    normalized: int | None


@dataclass(frozen=True, slots=True)
class RawDate:
    raw: str
    normalized: date | None


@dataclass(frozen=True, slots=True)
class Quantity:
    """An amount: a number and its unit, read together or not at all.

    `value` and `unit` are both `None` as soon as either half is unreadable — a number without
    its unit is not an amount.
    """

    raw_value: str
    raw_unit: str
    value: float | None
    unit: str | None


# --- raw rows: what ingest returns, what the baselines of #5 read ----------------------------
# `row_number` is 1-based and excludes the header: row 1 is the first data row of the file.


@dataclass(frozen=True, slots=True)
class RawVariantRow:
    row_number: int
    variant_id: str
    name: str
    design_date: str
    region: str
    seats: str
    bike_spaces: str
    traction: str


@dataclass(frozen=True, slots=True)
class RawBomRow:
    row_number: int
    line_id: str
    variant_id: str
    sub_assembly_ref: str
    sub_assembly_designation: str
    component_ref: str
    designation: str
    quantity: str
    unit: str
    supplier: str
    unit_cost_eur: str


@dataclass(frozen=True, slots=True)
class RawNoteRow:
    row_number: int
    note_id: str
    variant_id: str
    date: str
    text: str


@dataclass(frozen=True, slots=True)
class RawDataset:
    variants: tuple[RawVariantRow, ...]
    bom: tuple[RawBomRow, ...]
    notes: tuple[RawNoteRow, ...]


# --- entities --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Variant:
    id: str
    raw_id: str
    name: RawText
    design_date: RawDate
    region: RawText
    seats: RawInt
    bike_spaces: RawInt
    traction: RawText


@dataclass(frozen=True, slots=True)
class Supplier:
    """One supplier per text key, with every spelling of its name seen in the file."""

    id: str
    raw_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Component:
    """A candidate group: every raw reference sharing one reference key."""

    id: str
    raw_references: tuple[str, ...]
    designations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SubAssembly:
    """One per `(variant, reference key)`; `id` is `f"{variant_id}:{reference_key}"`."""

    id: str
    variant_id: str
    reference_key: str
    raw_references: tuple[str, ...]
    designations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BomLine:
    """The n-ary relation: `(variant_id, parent_id, child_id, quantity.value, quantity.unit)`.

    `component_ref.normalized == child_id`, `sub_assembly_ref.normalized` is the parent's
    reference key, `supplier.normalized` is the `Supplier.id`. Supplier, cost and designation
    stay on the line: they are what may differ from one variant to the next. Every column of
    the raw row is carried here with its exact characters, the parent's designation included —
    except `variant_id`, kept normalized only: when it is empty or unknown, the
    `NormalizationIssue` holds its raw characters. `parent_id` is `""` when either half of the
    sub-assembly's key, the variant or the reference, names nothing.
    """

    line_id: str
    row_number: int
    variant_id: str
    parent_id: str
    child_id: str
    quantity: Quantity
    sub_assembly_ref: RawText
    sub_assembly_designation: RawText
    component_ref: RawText
    designation: RawText
    supplier: RawText
    unit_cost: RawNumber


@dataclass(frozen=True, slots=True)
class Note:
    """A free-text note, carried through untouched. Reading it is #6's job."""

    note_id: str
    row_number: int
    variant_id: str
    date: RawDate
    text: str


@dataclass(frozen=True, slots=True)
class NormalizationIssue:
    """A value this stage could not read. The row is kept; this is a data-quality record, not a finding."""

    source_file: str
    row_number: int
    row_id: str
    field: str
    raw: str
    reason: str


@dataclass(frozen=True, slots=True)
class NormalizedDataset:
    variants: tuple[Variant, ...]
    suppliers: tuple[Supplier, ...]
    components: tuple[Component, ...]
    sub_assemblies: tuple[SubAssembly, ...]
    lines: tuple[BomLine, ...]
    notes: tuple[Note, ...]
    issues: tuple[NormalizationIssue, ...]


# --- findings ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, order=True)
class SourceRow:
    """One row of one input file, named the way `NormalizationIssue` names it."""

    source_file: str
    row_number: int
    row_id: str


@dataclass(frozen=True, slots=True)
class Finding:
    """A proposal for a human, with everything needed to check it (R11).

    `source_rows` holds the rows a reader must open to judge the finding — one per distinct
    value the rule read, not every row of the group: a reference used on forty lines would
    otherwise bury its own evidence.
    """

    rule_id: str
    confidence: float
    subject: str
    message: str
    source_rows: tuple[SourceRow, ...]


# --- resolution -------------------------------------------------------------------------------


class GroupVerdict(StrEnum):
    """What `resolve` says of the group a reference key formed (docs/ARCHITECTURE.md A2).

    It rates the coherence of that group, not the confidence of a match: rules-only resolution
    leaves no fuzzy match to rate (DECISIONS.md 20).
    """

    AUTO = "auto"
    REVIEW = "review"
    REJECT = "reject"


class Attribute(StrEnum):
    """What rows sharing a key can disagree about."""

    DESIGNATION = "designation"
    UNIT = "unit"
    SUPPLIER = "supplier"
    COST = "cost"


@dataclass(frozen=True, slots=True)
class CanonicalComponent:
    """One product, and the rows of `bom.csv` that name it.

    `id` is the reference key, and `f"{key}#{n}"` for each part of a group a `reject` split —
    a canonical id is not a reference, and nothing reads it back as one.

    `rows` holds row numbers rather than `line_id` values: a row number is unique by
    construction, where the `line_id` column is data and a dirty export may leave it empty.
    It is also the coordinate a `Finding` cites, so the two artifacts point at the same place.
    """

    id: str
    reference_key: str
    raw_references: tuple[str, ...]
    designations: tuple[str, ...]
    rows: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CandidateGroup:
    """Everything one reference key gathered, and what became of it.

    `components` holds one entry under `auto` and `review`, and one per product under `reject`
    (Decision 26: only a `reject` splits a group, and `review` feeds the signatures like `auto`).
    """

    reference_key: str
    verdict: GroupVerdict
    diverging: tuple[Attribute, ...]
    components: tuple[CanonicalComponent, ...]


@dataclass(frozen=True, slots=True)
class Resolution:
    """The resolution artifact: every candidate group, with its verdict and its components."""

    groups: tuple[CandidateGroup, ...]

    @property
    def components(self) -> tuple[CanonicalComponent, ...]:
        """Every canonical component, groups flattened: what the signatures of #16 will read."""
        return tuple(component for group in self.groups for component in group.components)


# --- what the notes say ---------------------------------------------------------------------


class FactKind(StrEnum):
    """What a note can assert about a component, and the whole of what the notes layer reads.

    Three kinds, because three are what the client's data actually carries (CONTEXT.md): a part
    is replaced, a part is no longer to be used, or a part is forbidden on some configuration.
    A note that asserts none of them produces no fact.
    """

    REPLACEMENT = "replacement"
    OBSOLESCENCE = "obsolescence"
    RESTRICTION = "restriction"


@dataclass(frozen=True, slots=True)
class NoteFact:
    """One assertion of one note, in the note's own words, with the note cited.

    The references are **raw**: the characters the note writes, never a canonical id. `notes.py`
    extracts and does not match, `link.py` matches (docs/ARCHITECTURE.md A7), and keeping the raw
    string here is what lets a reader check the fact against the line of `notes.csv` it came from.

    `replacement_ref` and `scope` are `""` when the note says nothing of them — the empty-string
    convention the rest of the model uses for "no value", rather than a second optional type.
    """

    note_id: str
    row_number: int
    kind: FactKind
    component_ref: str
    replacement_ref: str
    scope: str


@dataclass(frozen=True, slots=True)
class LinkedFact:
    """A fact and the canonical components its raw reference reached.

    `components` is empty when the reference matched nothing in the BOM — a note about a part
    this export does not carry, or a string that only looked like a reference. It holds more
    than one entry when `resolve` split the group the key formed: the ambiguity is shown, never
    guessed at (`resolve.Candidate`).

    Unlinked facts stay in the artifact. Dropping them would hide, in the one place a reviewer
    looks, every note the layer read but could not place.
    """

    fact: NoteFact
    components: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NoteFacts:
    """The notes layer's artifact: which reader ran, what it read, and what it could not.

    `reader` names the reader because the same pipeline gives different facts through the keyword
    fallback and through a model, and a finding read off this file must say which one produced it.

    `invalid_outputs` counts what a reader produced and could not be used — a model answer that
    failed validation, a fact naming a reference the note does not contain. It is written into
    the artifact rather than only logged, so that "the model was wrong nine times" is a number a
    reviewer can read off the run (CLAUDE.md, LLM layer).
    """

    reader: str
    notes_read: int
    invalid_outputs: int
    facts: tuple[LinkedFact, ...]


# --- signatures and the backtest ----------------------------------------------------------------


@dataclass(frozen=True, slots=True, order=True)
class SignatureItem:
    """One line of a signature: a canonical component, its quantity, its SI unit."""

    component: str
    quantity: float
    unit: str


@dataclass(frozen=True, slots=True)
class Signature:
    """The signature of a sub-assembly.

    Formally the multiset of `(canonical component, normalized quantity, SI unit)` it
    contains. A canonical component carries its whole quantity on one line, so the multiset
    is represented as items sorted by component, one per component — which is also what
    makes the comparison in `signatures.py` a plain set difference.

    Nested sub-assemblies are out of scope ([A1] in the PRD): a signature is flat.
    """

    items: tuple[SignatureItem, ...]

    def __post_init__(self) -> None:
        components = [item.component for item in self.items]
        if len(set(components)) != len(components):
            duplicates = sorted({c for c in components if components.count(c) > 1})
            raise ValueError(f"a canonical component appears twice in one signature: {duplicates}")

    def __len__(self) -> int:
        return len(self.items)

    @property
    def by_component(self) -> dict[str, SignatureItem]:
        return {item.component: item for item in self.items}

    @classmethod
    def of(cls, items: Iterable[SignatureItem]) -> "Signature":
        return cls(items=tuple(sorted(items)))

    @classmethod
    def from_counts(
        cls,
        counts: Mapping[str, float],
        units: Mapping[str, str] | None = None,
        default_unit: str = "pcs",
    ) -> "Signature":
        """Build a signature from a component -> quantity mapping.

        This is how the story cases of `data/dataset_spec.toml` become comparable, and how
        `generate.py` states what it plants.
        """
        units = units or {}
        return cls.of(
            SignatureItem(component=component, quantity=float(quantity), unit=units.get(component, default_unit))
            for component, quantity in counts.items()
        )


@dataclass(frozen=True, slots=True)
class QuantityChange:
    """A component present on both sides, carrying a different quantity or unit."""

    component: str
    left: SignatureItem
    right: SignatureItem


@dataclass(frozen=True, slots=True)
class SignatureDiff:
    """The evidence attached to a reuse finding, produced by the comparison itself.

    `added` and `removed` are read left-to-right: what the right-hand signature adds to, and
    what it drops from, the left-hand one.
    """

    added: tuple[SignatureItem, ...]
    removed: tuple[SignatureItem, ...]
    quantity_changed: tuple[QuantityChange, ...]

    @property
    def n_parts_diff(self) -> int:
        """Canonical components added or removed."""
        return len(self.added) + len(self.removed)

    @property
    def n_qty_diff(self) -> int:
        """Components present on both sides with a different quantity."""
        return len(self.quantity_changed)

    def is_empty(self) -> bool:
        return self.n_parts_diff == 0 and self.n_qty_diff == 0


@dataclass(frozen=True, slots=True)
class SubAssemblySignature:
    """One sub-assembly and the signature `signatures.build_signatures` read off its lines.

    The designations travel with it because a reviewer opening `signatures.json` reads
    `carbody shell`, not `C:SA0101`.

    `lines_left_out` counts the sub-assembly's BOM lines that reached no item of the signature,
    and is what keeps a short signature from reading as a small sub-assembly: two signatures
    are compared as the *content* of what they describe, so a reader — and the backtest — must
    be able to tell a complete one from a truncated one. A false *reused* is the worst error
    this tool can make (`resolve.py`), and absence of readable evidence is not evidence of
    identity.
    """

    sub_assembly_id: str
    variant_id: str
    reference_key: str
    designations: tuple[str, ...]
    signature: Signature
    lines_left_out: int


class ReuseClass(StrEnum):
    """What the backtest says of one sub-assembly of the newest variant.

    `signatures.Verdict` classifies a *pair* of signatures, and `identical` is a property of two.
    These are the words the client's question is asked in (README, PRD R6): the sub-assembly is
    already there, it is there with a known diff, or it is this variant's own.
    """

    REUSED = "reused"
    REUSABLE = "reusable"
    SPECIFIC = "specific"


@dataclass(frozen=True, slots=True)
class Prediction:
    """The backtest's answer for one sub-assembly of the newest variant.

    `ancestor_id` names one older sub-assembly the answer rests on, and is `""` under
    `specific` — the empty-key convention `BomLine.parent_id` already uses. Several older
    sub-assemblies usually reach the same verdict and one valid source is enough to reuse
    from, so the set is not carried (Decision 25).

    `diff` is `None` unless the class is `reusable`: a `reused` answer's diff is empty by
    definition, and a `specific` one has nothing to diff against. The ground truth of #2 says
    the same of its own labels.
    """

    sub_assembly_id: str
    variant_id: str
    reuse_class: ReuseClass
    ancestor_id: str
    diff: SignatureDiff | None


@dataclass(frozen=True, slots=True)
class Backtest:
    """The newest variant's answers, and what they were computed against.

    The variants it saw are part of the claim — a backtest that quietly compared the newest
    variant with itself would print the same table ([A7]) — so they are written into the
    artifact rather than left to be inferred from it.
    """

    target_variant_id: str
    ancestor_variant_ids: tuple[str, ...]
    predictions: tuple[Prediction, ...]


# --- writing ---------------------------------------------------------------------------------


def dataset_to_dict(dataset: NormalizedDataset) -> dict[str, Any]:
    data = _jsonable(dataclasses.asdict(dataset))
    data["schema_version"] = SCHEMA_VERSION
    return data


def render_dataset(dataset: NormalizedDataset) -> str:
    return _render(_jsonable(dataclasses.asdict(dataset)))


def dump_dataset(dataset: NormalizedDataset, path: Path) -> None:
    _write(render_dataset(dataset), path)


def render_resolution(resolution: Resolution) -> str:
    return _render({"groups": _jsonable([dataclasses.asdict(group) for group in resolution.groups])})


def dump_resolution(resolution: Resolution, path: Path) -> None:
    _write(render_resolution(resolution), path)


def render_findings(findings: tuple[Finding, ...]) -> str:
    return _render({"findings": _jsonable([dataclasses.asdict(finding) for finding in findings])})


def dump_findings(findings: tuple[Finding, ...], path: Path) -> None:
    _write(render_findings(findings), path)


def render_note_facts(note_facts: NoteFacts) -> str:
    return _render({"note_facts": _jsonable(dataclasses.asdict(note_facts))})


def dump_note_facts(note_facts: NoteFacts, path: Path) -> None:
    _write(render_note_facts(note_facts), path)


def render_signatures(signatures: tuple[SubAssemblySignature, ...]) -> str:
    return _render({"signatures": _jsonable([dataclasses.asdict(signature) for signature in signatures])})


def dump_signatures(signatures: tuple[SubAssemblySignature, ...], path: Path) -> None:
    _write(render_signatures(signatures), path)


def render_backtest(backtest: Backtest) -> str:
    return _render({"backtest": _jsonable(dataclasses.asdict(backtest))})


def dump_backtest(backtest: Backtest, path: Path) -> None:
    _write(render_backtest(backtest), path)


def _render(data: dict[str, Any]) -> str:
    """The exact text of an artifact. Keys are sorted here; tuple order is the stage's job."""
    # allow_nan=False: `Infinity` and `NaN` are not JSON. No stage lets either through; this is the backstop.
    return json.dumps({**data, "schema_version": SCHEMA_VERSION}, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _write(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _jsonable(value: Any) -> Any:
    # `asdict` keeps dates, which `json` refuses, and tuples, which `json` writes as arrays.
    # Turning both here makes this dict equal to what `json.loads` gives back from the artifact.
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


# --- reading ---------------------------------------------------------------------------------


def load_dataset(path: Path) -> NormalizedDataset:
    return dataset_from_dict(_read_json(path, "normalized dataset"))


def load_resolution(path: Path) -> Resolution:
    return resolution_from_dict(_read_json(path, "resolution"))


def load_findings(path: Path) -> tuple[Finding, ...]:
    return findings_from_dict(_read_json(path, "findings"))


def load_note_facts(path: Path) -> NoteFacts:
    return note_facts_from_dict(_read_json(path, "note facts"))


def load_signatures(path: Path) -> tuple[SubAssemblySignature, ...]:
    return signatures_from_dict(_read_json(path, "signatures"))


def load_backtest(path: Path) -> Backtest:
    return backtest_from_dict(_read_json(path, "backtest"))


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelError(f"{what} not found at {path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        # A directory, an unreadable file, a file written in another encoding: the caller asked
        # for an artifact and gets the one error type this module promises.
        raise ModelError(f"{what} at {path} cannot be read: {exc}") from exc
    except (ValueError, RecursionError) as exc:
        # `JSONDecodeError` is a `ValueError`, and so is the integer-digit limit `json.loads` hits
        # on a huge number literal; deep nesting gives a `RecursionError`. None of the three is an
        # artifact, and the caller was promised one error type.
        raise ModelError(f"{what} at {path} is not valid JSON: {exc}") from exc


def resolution_from_dict(data: Any) -> Resolution:
    _check_keys(data, {"groups", "schema_version"}, "the resolution")
    _check_schema_version(data, "bomreuse run")
    return Resolution(groups=_each(data["groups"], _group, "groups"))


def findings_from_dict(data: Any) -> tuple[Finding, ...]:
    _check_keys(data, {"findings", "schema_version"}, "the findings")
    _check_schema_version(data, "bomreuse run")
    return _each(data["findings"], _finding, "findings")


def _group(d: Any, where: str) -> CandidateGroup:
    _check_keys(d, {"reference_key", "verdict", "diverging", "components"}, where)
    return CandidateGroup(
        reference_key=_str(d["reference_key"], f"{where}.reference_key"),
        verdict=_member(GroupVerdict, d["verdict"], f"{where}.verdict"),
        diverging=tuple(_member(Attribute, value, f"{where}.diverging[{i}]") for i, value in enumerate(_list(d["diverging"], f"{where}.diverging"))),
        components=_each(d["components"], _canonical_component, f"{where}.components"),
    )


def _canonical_component(d: Any, where: str) -> CanonicalComponent:
    _check_keys(d, {"id", "reference_key", "raw_references", "designations", "rows"}, where)
    return CanonicalComponent(
        id=_str(d["id"], f"{where}.id"),
        reference_key=_str(d["reference_key"], f"{where}.reference_key"),
        raw_references=_str_tuple(d["raw_references"], f"{where}.raw_references"),
        designations=_str_tuple(d["designations"], f"{where}.designations"),
        rows=tuple(_int(value, f"{where}.rows[{index}]") for index, value in enumerate(_list(d["rows"], f"{where}.rows"))),
    )


def _finding(d: Any, where: str) -> Finding:
    _check_keys(d, {"rule_id", "confidence", "subject", "message", "source_rows"}, where)
    return Finding(
        rule_id=_str(d["rule_id"], f"{where}.rule_id"),
        confidence=_finite_float(d["confidence"], f"{where}.confidence"),
        subject=_str(d["subject"], f"{where}.subject"),
        message=_str(d["message"], f"{where}.message"),
        source_rows=_each(d["source_rows"], _source_row, f"{where}.source_rows"),
    )


def _source_row(d: Any, where: str) -> SourceRow:
    _check_keys(d, {"source_file", "row_number", "row_id"}, where)
    return SourceRow(
        source_file=_str(d["source_file"], f"{where}.source_file"),
        row_number=_int(d["row_number"], f"{where}.row_number"),
        row_id=_str(d["row_id"], f"{where}.row_id"),
    )


def note_facts_from_dict(data: Any) -> NoteFacts:
    _check_keys(data, {"note_facts", "schema_version"}, "the note facts")
    _check_schema_version(data, "bomreuse run")
    table = data["note_facts"]
    _check_keys(table, {"reader", "notes_read", "invalid_outputs", "facts"}, "note_facts")
    return NoteFacts(
        reader=_str(table["reader"], "note_facts.reader"),
        notes_read=_int(table["notes_read"], "note_facts.notes_read"),
        invalid_outputs=_int(table["invalid_outputs"], "note_facts.invalid_outputs"),
        facts=_each(table["facts"], _linked_fact, "note_facts.facts"),
    )


def _linked_fact(d: Any, where: str) -> LinkedFact:
    _check_keys(d, {"fact", "components"}, where)
    return LinkedFact(fact=_note_fact(d["fact"], f"{where}.fact"), components=_str_tuple(d["components"], f"{where}.components"))


def _note_fact(d: Any, where: str) -> NoteFact:
    _check_keys(d, {"note_id", "row_number", "kind", "component_ref", "replacement_ref", "scope"}, where)
    return NoteFact(
        note_id=_str(d["note_id"], f"{where}.note_id"),
        row_number=_int(d["row_number"], f"{where}.row_number"),
        kind=_member(FactKind, d["kind"], f"{where}.kind"),
        component_ref=_str(d["component_ref"], f"{where}.component_ref"),
        replacement_ref=_str(d["replacement_ref"], f"{where}.replacement_ref"),
        scope=_str(d["scope"], f"{where}.scope"),
    )


def signatures_from_dict(data: Any) -> tuple[SubAssemblySignature, ...]:
    _check_keys(data, {"signatures", "schema_version"}, "the signatures")
    _check_schema_version(data, "bomreuse run")
    return _each(data["signatures"], _sub_assembly_signature, "signatures")


def backtest_from_dict(data: Any) -> Backtest:
    _check_keys(data, {"backtest", "schema_version"}, "the backtest")
    _check_schema_version(data, "bomreuse run")
    table = data["backtest"]
    _check_keys(table, {"target_variant_id", "ancestor_variant_ids", "predictions"}, "backtest")
    return Backtest(
        target_variant_id=_str(table["target_variant_id"], "backtest.target_variant_id"),
        ancestor_variant_ids=_str_tuple(table["ancestor_variant_ids"], "backtest.ancestor_variant_ids"),
        predictions=_each(table["predictions"], _prediction, "backtest.predictions"),
    )


def _sub_assembly_signature(d: Any, where: str) -> SubAssemblySignature:
    _check_keys(d, {"sub_assembly_id", "variant_id", "reference_key", "designations", "signature", "lines_left_out"}, where)
    return SubAssemblySignature(
        sub_assembly_id=_str(d["sub_assembly_id"], f"{where}.sub_assembly_id"),
        variant_id=_str(d["variant_id"], f"{where}.variant_id"),
        reference_key=_str(d["reference_key"], f"{where}.reference_key"),
        designations=_str_tuple(d["designations"], f"{where}.designations"),
        signature=_signature(d["signature"], f"{where}.signature"),
        lines_left_out=_int(d["lines_left_out"], f"{where}.lines_left_out"),
    )


def _prediction(d: Any, where: str) -> Prediction:
    _check_keys(d, {"sub_assembly_id", "variant_id", "reuse_class", "ancestor_id", "diff"}, where)
    return Prediction(
        sub_assembly_id=_str(d["sub_assembly_id"], f"{where}.sub_assembly_id"),
        variant_id=_str(d["variant_id"], f"{where}.variant_id"),
        reuse_class=_member(ReuseClass, d["reuse_class"], f"{where}.reuse_class"),
        ancestor_id=_str(d["ancestor_id"], f"{where}.ancestor_id"),
        diff=None if d["diff"] is None else _signature_diff(d["diff"], f"{where}.diff"),
    )


def _signature(d: Any, where: str) -> Signature:
    _check_keys(d, {"items"}, where)
    items = _each(d["items"], _signature_item, f"{where}.items")
    try:
        return Signature(items=items)
    except ValueError as exc:  # a hand-edited artifact naming one component twice
        raise ModelError(f"{where}: {exc}") from exc


def _signature_item(d: Any, where: str) -> SignatureItem:
    _check_keys(d, {"component", "quantity", "unit"}, where)
    return SignatureItem(
        component=_str(d["component"], f"{where}.component"),
        quantity=_finite_float(d["quantity"], f"{where}.quantity"),
        unit=_str(d["unit"], f"{where}.unit"),
    )


def _signature_diff(d: Any, where: str) -> SignatureDiff:
    _check_keys(d, {"added", "removed", "quantity_changed"}, where)
    return SignatureDiff(
        added=_each(d["added"], _signature_item, f"{where}.added"),
        removed=_each(d["removed"], _signature_item, f"{where}.removed"),
        quantity_changed=_each(d["quantity_changed"], _quantity_change, f"{where}.quantity_changed"),
    )


def _quantity_change(d: Any, where: str) -> QuantityChange:
    _check_keys(d, {"component", "left", "right"}, where)
    return QuantityChange(
        component=_str(d["component"], f"{where}.component"),
        left=_signature_item(d["left"], f"{where}.left"),
        right=_signature_item(d["right"], f"{where}.right"),
    )


def dataset_from_dict(data: Any) -> NormalizedDataset:
    """Rebuild the very objects `dataset_to_dict` was given — tuples included — or raise `ModelError`."""
    sections = {"variants", "suppliers", "components", "sub_assemblies", "lines", "notes", "issues"}
    _check_keys(data, sections | {"schema_version"}, "the dataset")
    _check_schema_version(data, "bomreuse normalize")
    return NormalizedDataset(
        variants=_each(data["variants"], _variant, "variants"),
        suppliers=_each(data["suppliers"], _supplier, "suppliers"),
        components=_each(data["components"], _component, "components"),
        sub_assemblies=_each(data["sub_assemblies"], _sub_assembly, "sub_assemblies"),
        lines=_each(data["lines"], _line, "lines"),
        notes=_each(data["notes"], _note, "notes"),
        issues=_each(data["issues"], _issue, "issues"),
    )


def _variant(d: Any, where: str) -> Variant:
    _check_keys(d, {"id", "raw_id", "name", "design_date", "region", "seats", "bike_spaces", "traction"}, where)
    return Variant(
        id=_str(d["id"], f"{where}.id"),
        raw_id=_str(d["raw_id"], f"{where}.raw_id"),
        name=_raw_text(d["name"], f"{where}.name"),
        design_date=_raw_date(d["design_date"], f"{where}.design_date"),
        region=_raw_text(d["region"], f"{where}.region"),
        seats=_raw_int(d["seats"], f"{where}.seats"),
        bike_spaces=_raw_int(d["bike_spaces"], f"{where}.bike_spaces"),
        traction=_raw_text(d["traction"], f"{where}.traction"),
    )


def _supplier(d: Any, where: str) -> Supplier:
    _check_keys(d, {"id", "raw_names"}, where)
    return Supplier(id=_str(d["id"], f"{where}.id"), raw_names=_str_tuple(d["raw_names"], f"{where}.raw_names"))


def _component(d: Any, where: str) -> Component:
    _check_keys(d, {"id", "raw_references", "designations"}, where)
    return Component(
        id=_str(d["id"], f"{where}.id"),
        raw_references=_str_tuple(d["raw_references"], f"{where}.raw_references"),
        designations=_str_tuple(d["designations"], f"{where}.designations"),
    )


def _sub_assembly(d: Any, where: str) -> SubAssembly:
    _check_keys(d, {"id", "variant_id", "reference_key", "raw_references", "designations"}, where)
    return SubAssembly(
        id=_str(d["id"], f"{where}.id"),
        variant_id=_str(d["variant_id"], f"{where}.variant_id"),
        reference_key=_str(d["reference_key"], f"{where}.reference_key"),
        raw_references=_str_tuple(d["raw_references"], f"{where}.raw_references"),
        designations=_str_tuple(d["designations"], f"{where}.designations"),
    )


def _line(d: Any, where: str) -> BomLine:
    _check_keys(
        d,
        {
            "line_id",
            "row_number",
            "variant_id",
            "parent_id",
            "child_id",
            "quantity",
            "sub_assembly_ref",
            "sub_assembly_designation",
            "component_ref",
            "designation",
            "supplier",
            "unit_cost",
        },
        where,
    )
    return BomLine(
        line_id=_str(d["line_id"], f"{where}.line_id"),
        row_number=_int(d["row_number"], f"{where}.row_number"),
        variant_id=_str(d["variant_id"], f"{where}.variant_id"),
        parent_id=_str(d["parent_id"], f"{where}.parent_id"),
        child_id=_str(d["child_id"], f"{where}.child_id"),
        quantity=_quantity(d["quantity"], f"{where}.quantity"),
        sub_assembly_ref=_raw_text(d["sub_assembly_ref"], f"{where}.sub_assembly_ref"),
        sub_assembly_designation=_raw_text(d["sub_assembly_designation"], f"{where}.sub_assembly_designation"),
        component_ref=_raw_text(d["component_ref"], f"{where}.component_ref"),
        designation=_raw_text(d["designation"], f"{where}.designation"),
        supplier=_raw_text(d["supplier"], f"{where}.supplier"),
        unit_cost=_raw_number(d["unit_cost"], f"{where}.unit_cost"),
    )


def _note(d: Any, where: str) -> Note:
    _check_keys(d, {"note_id", "row_number", "variant_id", "date", "text"}, where)
    return Note(
        note_id=_str(d["note_id"], f"{where}.note_id"),
        row_number=_int(d["row_number"], f"{where}.row_number"),
        variant_id=_str(d["variant_id"], f"{where}.variant_id"),
        date=_raw_date(d["date"], f"{where}.date"),
        text=_str(d["text"], f"{where}.text"),
    )


def _issue(d: Any, where: str) -> NormalizationIssue:
    _check_keys(d, {"source_file", "row_number", "row_id", "field", "raw", "reason"}, where)
    return NormalizationIssue(
        source_file=_str(d["source_file"], f"{where}.source_file"),
        row_number=_int(d["row_number"], f"{where}.row_number"),
        row_id=_str(d["row_id"], f"{where}.row_id"),
        field=_str(d["field"], f"{where}.field"),
        raw=_str(d["raw"], f"{where}.raw"),
        reason=_str(d["reason"], f"{where}.reason"),
    )


def _raw_text(d: Any, where: str) -> RawText:
    _check_keys(d, {"raw", "normalized"}, where)
    return RawText(raw=_str(d["raw"], f"{where}.raw"), normalized=_str(d["normalized"], f"{where}.normalized"))


def _raw_number(d: Any, where: str) -> RawNumber:
    _check_keys(d, {"raw", "normalized"}, where)
    return RawNumber(raw=_str(d["raw"], f"{where}.raw"), normalized=_opt_float(d["normalized"], f"{where}.normalized"))


def _raw_int(d: Any, where: str) -> RawInt:
    _check_keys(d, {"raw", "normalized"}, where)
    return RawInt(raw=_str(d["raw"], f"{where}.raw"), normalized=_opt_int(d["normalized"], f"{where}.normalized"))


def _raw_date(d: Any, where: str) -> RawDate:
    _check_keys(d, {"raw", "normalized"}, where)
    raw = _str(d["raw"], f"{where}.raw")
    if d["normalized"] is None:
        return RawDate(raw=raw, normalized=None)
    try:
        return RawDate(raw=raw, normalized=date.fromisoformat(d["normalized"]))
    except (TypeError, ValueError) as exc:
        raise ModelError(f"{where}.normalized must be an ISO date or null, got {d['normalized']!r}") from exc


def _quantity(d: Any, where: str) -> Quantity:
    _check_keys(d, {"raw_value", "raw_unit", "value", "unit"}, where)
    return Quantity(
        raw_value=_str(d["raw_value"], f"{where}.raw_value"),
        raw_unit=_str(d["raw_unit"], f"{where}.raw_unit"),
        value=_opt_float(d["value"], f"{where}.value"),
        unit=_opt_str(d["unit"], f"{where}.unit"),
    )


# --- primitives ------------------------------------------------------------------------------


def _each[T](items: Any, build: Callable[[Any, str], T], where: str) -> tuple[T, ...]:
    if not isinstance(items, list):
        raise ModelError(f"{where} must be an array, got {type(items).__name__}")
    return tuple(build(item, f"{where}[{index}]") for index, item in enumerate(items))


def _str(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise ModelError(f"{where} must be a string, got {type(value).__name__}")
    return value


def _opt_str(value: Any, where: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ModelError(f"{where} must be a string or null, got {type(value).__name__}")
    return value


def _int(value: Any, where: str) -> int:
    # `isinstance(True, int)` is true in Python, so a JSON boolean would pass for 1 and 0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelError(f"{where} must be an integer, got {type(value).__name__}")
    return value


def _opt_int(value: Any, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelError(f"{where} must be an integer or null, got {type(value).__name__}")
    return value


def _opt_float(value: Any, where: str) -> float | None:
    # json writes 36.0 as 36.0, so a float comes back a float; an integer is taken too, because
    # only a hand-edited artifact can hold one. A boolean is not a number.
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelError(f"{where} must be a number or null, got {type(value).__name__}")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ModelError(f"{where} is out of range for a float: {exc}") from exc
    # `render_dataset` refuses to write these (`allow_nan=False`) but `json.loads` reads the bare
    # `NaN` / `Infinity` literals, and turns `1e400` into `inf`: without this the reader would
    # hand back a dataset the writer cannot save, and `None` is the only way to say "unreadable".
    if not math.isfinite(number):
        raise ModelError(f"{where} must be a finite number or null, got {number!r}")
    return number


def _finite_float(value: Any, where: str) -> float:
    number = _opt_float(value, where)
    if number is None:
        raise ModelError(f"{where} must be a number, got null")
    return number


def _member[E: StrEnum](enum: type[E], value: Any, where: str) -> E:
    if not isinstance(value, str):
        raise ModelError(f"{where} must be a string, got {type(value).__name__}")
    try:
        return enum(value)
    except ValueError as exc:
        raise ModelError(f"{where} is {value!r}, not one of {[member.value for member in enum]}") from exc


def _list(values: Any, where: str) -> list[Any]:
    if not isinstance(values, list):
        raise ModelError(f"{where} must be an array, got {type(values).__name__}")
    return values


def _str_tuple(values: Any, where: str) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise ModelError(f"{where} must be an array of strings, got {type(values).__name__}")
    return tuple(_str(value, f"{where}[{index}]") for index, value in enumerate(values))


def _check_schema_version(data: dict[str, Any], command: str) -> None:
    if data["schema_version"] != SCHEMA_VERSION:
        raise ModelError(f"schema_version is {data['schema_version']!r}, this code reads {SCHEMA_VERSION!r}: run `{command}` again")


def _check_keys(table: Any, expected: set[str], where: str) -> None:
    if not isinstance(table, dict):
        raise ModelError(f"{where} must be an object, got {type(table).__name__}")
    missing = sorted(expected - table.keys())
    unknown = sorted(table.keys() - expected)
    if missing:
        raise ModelError(f"{where} is missing {missing}")
    if unknown:
        raise ModelError(f"{where} has unknown keys {unknown}; allowed: {sorted(expected)}")
