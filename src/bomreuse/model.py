"""The project's single set of types: raw rows, entities, and the artifact they round-trip through.

Every stage passes these frozen dataclasses, and `out/normalized.json` is serialized from them
and read back into them — no schema library mirrors them (docs/ARCHITECTURE.md A4, A8).

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
(`reject`) is decided by resolution (#4), which is why the designations seen are kept on it.

The raw rows live here rather than in `ingest.py` because the naive baselines of #5 consume them
and have no reason to import a reader.

Reading back is written by hand, one small function per type: reflection over field types would
be shorter and much harder to read in five minutes.
"""

import dataclasses
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

#: The name of the artifact inside the output directory the CLI is given.
NORMALIZED_FILE: Final[str] = "normalized.json"

#: Written into the artifact and checked on load: a later issue that changes a type bumps it, so
#: a stale `out/normalized.json` is refused instead of half-read.
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
    the raw row is carried here with its exact characters, the parent's designation included.
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


# --- writing ---------------------------------------------------------------------------------


def dataset_to_dict(dataset: NormalizedDataset) -> dict[str, Any]:
    data = _jsonable(dataclasses.asdict(dataset))
    data["schema_version"] = SCHEMA_VERSION
    return data


def render_dataset(dataset: NormalizedDataset) -> str:
    """The exact text of the artifact. Keys are sorted here; tuple order is `normalize`'s job."""
    return json.dumps(dataset_to_dict(dataset), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def dump_dataset(dataset: NormalizedDataset, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_dataset(dataset))


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
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelError(f"normalized dataset not found at {path}") from exc
    except json.JSONDecodeError as exc:
        raise ModelError(f"normalized dataset at {path} is not valid JSON: {exc}") from exc
    return dataset_from_dict(data)


def dataset_from_dict(data: Any) -> NormalizedDataset:
    """Rebuild the very objects `dataset_to_dict` was given — tuples included — or raise `ModelError`."""
    sections = {"variants", "suppliers", "components", "sub_assemblies", "lines", "notes", "issues"}
    _check_keys(data, sections | {"schema_version"}, "the dataset")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ModelError(f"schema_version is {data['schema_version']!r}, this code reads {SCHEMA_VERSION!r}: run `bomreuse normalize` again")
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
        id=d["id"],
        raw_id=d["raw_id"],
        name=_raw_text(d["name"], f"{where}.name"),
        design_date=_raw_date(d["design_date"], f"{where}.design_date"),
        region=_raw_text(d["region"], f"{where}.region"),
        seats=_raw_int(d["seats"], f"{where}.seats"),
        bike_spaces=_raw_int(d["bike_spaces"], f"{where}.bike_spaces"),
        traction=_raw_text(d["traction"], f"{where}.traction"),
    )


def _supplier(d: Any, where: str) -> Supplier:
    _check_keys(d, {"id", "raw_names"}, where)
    return Supplier(id=d["id"], raw_names=tuple(d["raw_names"]))


def _component(d: Any, where: str) -> Component:
    _check_keys(d, {"id", "raw_references", "designations"}, where)
    return Component(id=d["id"], raw_references=tuple(d["raw_references"]), designations=tuple(d["designations"]))


def _sub_assembly(d: Any, where: str) -> SubAssembly:
    _check_keys(d, {"id", "variant_id", "reference_key", "raw_references", "designations"}, where)
    return SubAssembly(
        id=d["id"],
        variant_id=d["variant_id"],
        reference_key=d["reference_key"],
        raw_references=tuple(d["raw_references"]),
        designations=tuple(d["designations"]),
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
        line_id=d["line_id"],
        row_number=d["row_number"],
        variant_id=d["variant_id"],
        parent_id=d["parent_id"],
        child_id=d["child_id"],
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
        note_id=d["note_id"],
        row_number=d["row_number"],
        variant_id=d["variant_id"],
        date=_raw_date(d["date"], f"{where}.date"),
        text=d["text"],
    )


def _issue(d: Any, where: str) -> NormalizationIssue:
    _check_keys(d, {"source_file", "row_number", "row_id", "field", "raw", "reason"}, where)
    return NormalizationIssue(
        source_file=d["source_file"],
        row_number=d["row_number"],
        row_id=d["row_id"],
        field=d["field"],
        raw=d["raw"],
        reason=d["reason"],
    )


def _raw_text(d: Any, where: str) -> RawText:
    _check_keys(d, {"raw", "normalized"}, where)
    return RawText(raw=d["raw"], normalized=d["normalized"])


def _raw_number(d: Any, where: str) -> RawNumber:
    _check_keys(d, {"raw", "normalized"}, where)
    # json writes 36.0 as 36.0, so a float comes back a float; the conversion only guards a
    # hand-edited artifact.
    return RawNumber(raw=d["raw"], normalized=None if d["normalized"] is None else float(d["normalized"]))


def _raw_int(d: Any, where: str) -> RawInt:
    _check_keys(d, {"raw", "normalized"}, where)
    return RawInt(raw=d["raw"], normalized=d["normalized"])


def _raw_date(d: Any, where: str) -> RawDate:
    _check_keys(d, {"raw", "normalized"}, where)
    if d["normalized"] is None:
        return RawDate(raw=d["raw"], normalized=None)
    try:
        return RawDate(raw=d["raw"], normalized=date.fromisoformat(d["normalized"]))
    except (TypeError, ValueError) as exc:
        raise ModelError(f"{where}.normalized must be an ISO date or null, got {d['normalized']!r}") from exc


def _quantity(d: Any, where: str) -> Quantity:
    _check_keys(d, {"raw_value", "raw_unit", "value", "unit"}, where)
    return Quantity(
        raw_value=d["raw_value"],
        raw_unit=d["raw_unit"],
        value=None if d["value"] is None else float(d["value"]),
        unit=d["unit"],
    )


# --- primitives ------------------------------------------------------------------------------


def _each[T](items: Any, build: Callable[[Any, str], T], where: str) -> tuple[T, ...]:
    if not isinstance(items, list):
        raise ModelError(f"{where} must be an array, got {type(items).__name__}")
    return tuple(build(item, f"{where}[{index}]") for index, item in enumerate(items))


def _check_keys(table: Any, expected: set[str], where: str) -> None:
    if not isinstance(table, dict):
        raise ModelError(f"{where} must be an object, got {type(table).__name__}")
    missing = sorted(expected - table.keys())
    unknown = sorted(table.keys() - expected)
    if missing:
        raise ModelError(f"{where} is missing {missing}")
    if unknown:
        raise ModelError(f"{where} has unknown keys {unknown}; allowed: {sorted(expected)}")
