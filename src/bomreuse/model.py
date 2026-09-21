"""The project's single set of types: raw rows, entities, and what each stage makes of them.

Every stage passes these frozen dataclasses, and the JSON files in `out/` are serialized from
them and read back into them — no schema library mirrors them (docs/ARCHITECTURE.md A4, A8).
The types live here and the rules live in the stages: `Component` is `normalize`'s output and
`CandidateGroup` is `resolve`'s, and both are read back by whoever is handed the file. The
round-trip itself — file names, writers, loaders — is `artifacts.py`, which imports this module
and nothing else.

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
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

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
