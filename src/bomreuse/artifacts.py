"""The artifacts in `out/`: their names, and the JSON round-trip of every type in `model.py`.

One JSON file per stage, serialized from the frozen dataclasses of `model.py` and read back into
them — no schema library mirrors them (docs/ARCHITECTURE.md A4, A8). `bomreuse run` reads each
stage's artifact back rather than the object still in memory, so what is written here is what
the next stage works on.

Reading back is written by hand, one small function per type: reflection over field types would
be shorter and much harder to read in five minutes. Every leaf is checked as it is read, not
only the keys — a stage told to expect `ModelError` must not meet a `TypeError` instead.

This module imports `model` and nothing else from the package.
"""

import dataclasses
import json
import math
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from bomreuse.model import (
    Attribute,
    Backtest,
    BomLine,
    CandidateGroup,
    CanonicalComponent,
    Component,
    FactKind,
    Finding,
    GroupVerdict,
    LinkedFact,
    NormalizationIssue,
    NormalizedDataset,
    Note,
    NoteFact,
    NoteFacts,
    Prediction,
    Quantity,
    QuantityChange,
    RawDate,
    RawInt,
    RawNumber,
    RawText,
    Resolution,
    ReuseClass,
    Signature,
    SignatureDiff,
    SignatureItem,
    SourceRow,
    SubAssembly,
    SubAssemblySignature,
    Supplier,
    Variant,
)

#: The names of the artifacts inside the output directory the CLI is given.
NORMALIZED_FILE: Final[str] = "normalized.json"
RESOLUTION_FILE: Final[str] = "resolution.json"
FINDINGS_FILE: Final[str] = "findings.json"
NOTE_FACTS_FILE: Final[str] = "note_facts.json"
SIGNATURES_FILE: Final[str] = "signatures.json"
PREDICTIONS_FILE: Final[str] = "predictions.json"
#: The one artifact that is not serialized from these types: the report `report.py` renders off
#: them, for a reader who opens a browser rather than a JSON file ([A6]).
REPORT_FILE: Final[str] = "report.html"

#: Everything `bomreuse run` writes, in the order the pipeline produces it. Said once, here: the
#: CLI writes this list and checks it against the raw directory, and the tests that watch
#: determinism and the read-only inputs read it rather than a copy of it — so an artifact a later
#: issue adds is covered by all of them without a hand edit anywhere.
RUN_ARTIFACTS: Final[tuple[str, ...]] = (NORMALIZED_FILE, RESOLUTION_FILE, NOTE_FACTS_FILE, FINDINGS_FILE, SIGNATURES_FILE, PREDICTIONS_FILE, REPORT_FILE)

#: Written into every artifact and checked on load: a later issue that changes a type bumps it,
#: so a stale file in `out/` is refused instead of half-read. One version for the whole set of
#: types, since one stage reads what the previous one wrote.
SCHEMA_VERSION: Final[str] = "1"


class ModelError(ValueError):
    """A serialized dataset does not have the shape of these types."""


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
