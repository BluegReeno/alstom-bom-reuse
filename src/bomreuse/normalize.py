"""Make sense of the raw strings: reference keys, units to SI, decimal commas, text, dates.

Everything here is a rule, and a small one. There is no string distance anywhere in this
module or in the pipeline (docs/ARCHITECTURE.md A2): two references are the same candidate
when a handful of stated foldings give them the same key, and never because they "look close".
What the rules cannot reach — a transposition, a missing character — stays out of reach, and
`evaluate` measures the shortfall instead of this module hiding it.

A value that cannot be read is not repaired and not dropped: the row is kept, the raw
characters are kept, the normalized value is `None` and a `NormalizationIssue` records why —
counted, never silently lost. Each parser below therefore returns `(value, None)` or
`(None, reason)`.

`normalize()` takes a `RawDataset` and nothing else — no path, no spec. It cannot be handed
anything but the rows `ingest` read (docs/ARCHITECTURE.md A5).
"""

import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from bomreuse.model import (
    BomLine,
    Component,
    NormalizationIssue,
    NormalizedDataset,
    Note,
    Quantity,
    RawBomRow,
    RawDataset,
    RawDate,
    RawInt,
    RawNoteRow,
    RawNumber,
    RawText,
    RawVariantRow,
    SubAssembly,
    Supplier,
    Variant,
)

#: The file names an issue cites. Declared here as plain labels: `normalize` opens no file.
_VARIANTS: Final[str] = "variants.csv"
_BOM: Final[str] = "bom.csv"
_NOTES: Final[str] = "notes.csv"

#: The homoglyph folding of the reference key: `O→0`, `I→1`, `L→1` — the pairs A2 lists, and
#: no other (`S/5`, `B/8`, `Z/2` are not folded). It is applied **after** uppercasing, and the
#: order decides the result: folding a lowercase `l` first would miss `brk-ctrl-valve` and
#: `Hvac-grille-12`, a family the spec declares within reach. Uppercasing first makes the rule
#: case-insensitive and one line long. The accepted cost: references differing only by `I`/`1`,
#: `O`/`0` or `L`/`1` share a key, and telling them apart is resolution's `reject` (#4), read in
#: resolution precision (DECISIONS.md 27).
_FOLD: Final[dict[int, str]] = str.maketrans({"O": "0", "I": "1", "L": "1"})

#: One number, written the way a French or an English export writes it: digits, and at most one
#: `.` or `,` with digits on both sides. No sign, no exponent, no thousands separator — and
#: ASCII digits only, since `\d` would otherwise accept full-width `１２`.
_NUMBER: Final[re.Pattern[str]] = re.compile(r"\d+(?:[.,]\d+)?", re.ASCII)
_INTEGER: Final[re.Pattern[str]] = re.compile(r"\d+", re.ASCII)
_ISO_DATE: Final[re.Pattern[str]] = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)

_THOUSANDTH: Final[Decimal] = Decimal("0.001")

#: raw unit (stripped, casefolded) -> (SI target, factor). Targets are `pcs`, `m`, `kg`: the
#: units `signatures.SignatureItem` compares.
UNITS: Final[Mapping[str, tuple[str, Decimal]]] = {
    "pcs": ("pcs", Decimal(1)),
    "units": ("pcs", Decimal(1)),
    "unit": ("pcs", Decimal(1)),
    "u": ("pcs", Decimal(1)),
    "m": ("m", Decimal(1)),
    "mm": ("m", _THOUSANDTH),
    "kg": ("kg", Decimal(1)),
    "g": ("kg", _THOUSANDTH),
}

#: `(field, raw value, reason)` — what a parser knows of a failure. The caller adds the file and the row.
FieldIssue = tuple[str, str, str]


# --- references and text ----------------------------------------------------------------------


def reference_key(raw: str) -> str:
    """Uppercase, fold `O I L`, drop everything that is not a letter or a digit.

    The key is an id, not a label (`SHELL-SEAL` gives `SHE11SEA1`): nothing displays it.
    `str.isalnum` keeps accented letters; dropping them would merge more, not less. NFC comes
    first for that reason: the combining mark of a decomposed `é` is not alphanumeric, and the
    letter would lose its accent on one spelling and keep it on the other.
    """
    composed = unicodedata.normalize("NFC", raw)
    return "".join(character for character in composed.upper().translate(_FOLD) if character.isalnum())


def text_key(raw: str) -> str:
    """The same name typed by someone else: Unicode form, spacing and case aside. Accents are kept."""
    return " ".join(unicodedata.normalize("NFC", raw).split()).casefold()


# --- numbers ----------------------------------------------------------------------------------


def parse_number(raw: str) -> tuple[Decimal | None, str | None]:
    """`48200,00` and `17650.00` alike. The shape is checked before anything is replaced."""
    text = raw.strip()
    if not text:
        return None, "empty"
    if "." in text and "," in text:
        return None, "ambiguous separators"  # 1.234,56 or 1,234.56: guessing would be a repair
    if not _NUMBER.fullmatch(text):
        return None, "not a number"
    number = Decimal(text.replace(",", "."))
    # Every number ends as a float in the artifact; past the largest one it would be `inf`.
    if not math.isfinite(float(number)):
        return None, "out of range"
    return number, None


def parse_int(raw: str) -> tuple[int | None, str | None]:
    text = raw.strip()
    if not text:
        return None, "empty"
    if not _INTEGER.fullmatch(text):
        return None, "not an integer"
    try:
        return int(text), None
    except ValueError:  # Python's int-conversion limit: a digit string over 4300 characters
        return None, "out of range"


def parse_date(raw: str) -> tuple[date | None, str | None]:
    text = raw.strip()
    if not text:
        return None, "empty"
    # The shape first: `date.fromisoformat` alone also takes `20190314` and `2019-W11-4`.
    if not _ISO_DATE.fullmatch(text):
        return None, "not an ISO date"
    try:
        return date.fromisoformat(text), None
    except ValueError:
        return None, "not an ISO date"


def parse_unit(raw: str) -> tuple[tuple[str, Decimal] | None, str | None]:
    text = raw.strip().casefold()
    if not text:
        return None, "empty"
    if text not in UNITS:
        return None, "unknown unit"
    return UNITS[text], None


def normalize_quantity(raw_value: str, raw_unit: str) -> tuple[Quantity, list[FieldIssue]]:
    """An amount in `pcs`, `m` or `kg`, or no amount at all.

    The arithmetic is done in `Decimal` and turned into a float once, at the end, so that
    `36000 mm`, `36 m` and `36,0 m` are the *same* float: `36000 / 1000.0`-style division is
    what makes two spellings of one length differ in the last bit.
    """
    issues: list[FieldIssue] = []
    number, number_reason = parse_number(raw_value)
    if number is not None and number <= 0:
        number, number_reason = None, "not positive"
    if number_reason is not None:
        issues.append(("quantity", raw_value, number_reason))
    unit, unit_reason = parse_unit(raw_unit)
    if unit_reason is not None:
        issues.append(("unit", raw_unit, unit_reason))

    if number is None or unit is None:
        # A number without its unit is not an amount, and neither is a unit without its number.
        return Quantity(raw_value=raw_value, raw_unit=raw_unit, value=None, unit=None), issues
    target, factor = unit
    return Quantity(raw_value=raw_value, raw_unit=raw_unit, value=float(number * factor), unit=target), issues


# --- rows into entities -----------------------------------------------------------------------


def normalize(raw: RawDataset) -> NormalizedDataset:
    """Every row kept, every raw value kept, every unreadable value counted.

    Components, sub-assemblies and suppliers are derived by grouping the lines on their keys. A
    `Component` is a candidate group — one per reference key — not yet a canonical component:
    splitting a key that covers two products is resolution's job (#4).
    """
    issues: list[NormalizationIssue] = []
    variants = [_variant(row, issues) for row in raw.variants]
    _report_duplicate_variants(variants, raw.variants, issues)
    known_variants = {variant.id for variant in variants}

    lines = [_line(row, known_variants, issues) for row in raw.bom]
    notes = [_note(row, known_variants, issues) for row in raw.notes]

    return NormalizedDataset(
        variants=tuple(sorted(variants, key=lambda variant: (variant.design_date.normalized or date.max, variant.id))),
        suppliers=_suppliers(lines),
        components=_components(lines),
        sub_assemblies=_sub_assemblies(lines),
        lines=tuple(lines),
        notes=tuple(notes),
        issues=tuple(sorted(issues, key=lambda issue: (issue.source_file, issue.row_number, issue.field))),
    )


@dataclass(frozen=True, slots=True)
class _Cells:
    """The cells of one file row, read one by one; whatever cannot be read is reported with its origin."""

    source_file: str
    row_number: int
    row_id: str
    issues: list[NormalizationIssue]

    def report(self, field: str, raw: str, reason: str) -> None:
        self.issues.append(NormalizationIssue(self.source_file, self.row_number, self.row_id, field, raw, reason))

    def text(self, field: str, raw: str) -> RawText:
        key = text_key(raw)
        if not key:
            self.report(field, raw, "empty")
        return RawText(raw=raw, normalized=key)

    def reference(self, field: str, raw: str) -> RawText:
        key = reference_key(raw)
        if not key:
            self.report(field, raw, "empty reference")
        return RawText(raw=raw, normalized=key)

    def variant_id(self, raw: str, known: set[str] | None = None) -> str:
        """`known` is given by the rows that *name* a variant, not by the rows that declare one."""
        normalized = raw.strip().upper()
        if not normalized:
            self.report("variant_id", raw, "empty")
        elif known is not None and normalized not in known:
            self.report("variant_id", raw, "unknown variant")
        return normalized

    def number(self, field: str, raw: str) -> RawNumber:
        value, reason = parse_number(raw)
        if reason is not None:
            self.report(field, raw, reason)
        return RawNumber(raw=raw, normalized=None if value is None else float(value))

    def integer(self, field: str, raw: str) -> RawInt:
        value, reason = parse_int(raw)
        if reason is not None:
            self.report(field, raw, reason)
        return RawInt(raw=raw, normalized=value)

    def iso_date(self, field: str, raw: str) -> RawDate:
        value, reason = parse_date(raw)
        if reason is not None:
            self.report(field, raw, reason)
        return RawDate(raw=raw, normalized=value)

    def quantity(self, raw_value: str, raw_unit: str) -> Quantity:
        quantity, field_issues = normalize_quantity(raw_value, raw_unit)
        for field, raw, reason in field_issues:
            self.report(field, raw, reason)
        return quantity


def _variant(row: RawVariantRow, issues: list[NormalizationIssue]) -> Variant:
    cells = _Cells(_VARIANTS, row.row_number, row.variant_id, issues)
    return Variant(
        id=cells.variant_id(row.variant_id),
        raw_id=row.variant_id,
        name=cells.text("name", row.name),
        design_date=cells.iso_date("design_date", row.design_date),
        region=cells.text("region", row.region),
        seats=cells.integer("seats", row.seats),
        bike_spaces=cells.integer("bike_spaces", row.bike_spaces),
        traction=cells.text("traction", row.traction),
    )


def _report_duplicate_variants(variants: list[Variant], rows: tuple[RawVariantRow, ...], issues: list[NormalizationIssue]) -> None:
    # `a` and `A ` are two raw ids for ingest and one variant here. Both rows are kept.
    seen: set[str] = set()
    for variant, row in zip(variants, rows, strict=True):
        if variant.id and variant.id in seen:
            issues.append(NormalizationIssue(_VARIANTS, row.row_number, row.variant_id, "variant_id", row.variant_id, "duplicate variant"))
        seen.add(variant.id)


def _line(row: RawBomRow, known_variants: set[str], issues: list[NormalizationIssue]) -> BomLine:
    cells = _Cells(_BOM, row.row_number, row.line_id, issues)
    if not row.line_id.strip():
        cells.report("line_id", row.line_id, "empty")
    variant_id = cells.variant_id(row.variant_id, known_variants)
    sub_assembly_ref = cells.reference("sub_assembly_ref", row.sub_assembly_ref)
    component_ref = cells.reference("component_ref", row.component_ref)
    # The sub-assembly's key has two halves, and both must name something: a reference, and a
    # variant that variants.csv declares. `:SA0101` or `Q:SA0101` would be a sub-assembly of no
    # variant, and #4 compares sub-assemblies across variants.
    names_a_sub_assembly = bool(sub_assembly_ref.normalized) and bool(variant_id) and variant_id in known_variants
    return BomLine(
        line_id=row.line_id,
        row_number=row.row_number,
        variant_id=variant_id,
        # An empty key names nothing: the line is kept, and no entity is created for it.
        parent_id=f"{variant_id}:{sub_assembly_ref.normalized}" if names_a_sub_assembly else "",
        child_id=component_ref.normalized,
        quantity=cells.quantity(row.quantity, row.unit),
        sub_assembly_ref=sub_assembly_ref,
        sub_assembly_designation=cells.text("sub_assembly_designation", row.sub_assembly_designation),
        component_ref=component_ref,
        designation=cells.text("designation", row.designation),
        supplier=cells.text("supplier", row.supplier),
        unit_cost=cells.number("unit_cost_eur", row.unit_cost_eur),
    )


def _note(row: RawNoteRow, known_variants: set[str], issues: list[NormalizationIssue]) -> Note:
    cells = _Cells(_NOTES, row.row_number, row.note_id, issues)
    if not row.note_id.strip():
        cells.report("note_id", row.note_id, "empty")
    if not row.text.strip():
        cells.report("text", row.text, "empty")
    # The text is carried through untouched: reading it is the notes layer's job (#6).
    return Note(
        note_id=row.note_id,
        row_number=row.row_number,
        variant_id=cells.variant_id(row.variant_id, known_variants),
        date=cells.iso_date("date", row.date),
        text=row.text,
    )


# Sets are only ever used to collect; every tuple below is built from `sorted(...)`, so the
# artifact does not depend on the interpreter's hash seed.


def _components(lines: list[BomLine]) -> tuple[Component, ...]:
    references: dict[str, set[str]] = defaultdict(set)
    designations: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        if line.child_id:
            references[line.child_id].add(line.component_ref.raw)
            designations[line.child_id].add(line.designation.normalized)
    return tuple(
        Component(id=key, raw_references=tuple(sorted(references[key])), designations=_non_empty(designations[key]))
        for key in sorted(references)
    )


def _sub_assemblies(lines: list[BomLine]) -> tuple[SubAssembly, ...]:
    references: dict[str, set[str]] = defaultdict(set)
    designations: dict[str, set[str]] = defaultdict(set)
    owners: dict[str, tuple[str, str]] = {}
    for line in lines:
        if line.parent_id:
            references[line.parent_id].add(line.sub_assembly_ref.raw)
            designations[line.parent_id].add(line.sub_assembly_designation.normalized)
            owners[line.parent_id] = (line.variant_id, line.sub_assembly_ref.normalized)
    return tuple(
        SubAssembly(
            id=parent_id,
            variant_id=owners[parent_id][0],
            reference_key=owners[parent_id][1],
            raw_references=tuple(sorted(references[parent_id])),
            designations=_non_empty(designations[parent_id]),
        )
        for parent_id in sorted(references)
    )


def _suppliers(lines: list[BomLine]) -> tuple[Supplier, ...]:
    names: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        if line.supplier.normalized:
            names[line.supplier.normalized].add(line.supplier.raw)
    return tuple(Supplier(id=key, raw_names=tuple(sorted(names[key]))) for key in sorted(names))


def _non_empty(values: set[str]) -> tuple[str, ...]:
    return tuple(sorted(value for value in values if value))
