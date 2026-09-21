"""The entity model: frozen, n-ary where it must be, and round-tripping through JSON to equal objects."""

import dataclasses
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from bomreuse import model
from bomreuse.model import (
    RUN_ARTIFACTS,
    Attribute,
    Backtest,
    BomLine,
    CandidateGroup,
    CanonicalComponent,
    Component,
    Finding,
    GroupVerdict,
    ModelError,
    NormalizationIssue,
    NormalizedDataset,
    Note,
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
    backtest_from_dict,
    dataset_from_dict,
    dataset_to_dict,
    dump_backtest,
    dump_dataset,
    dump_findings,
    dump_resolution,
    dump_signatures,
    findings_from_dict,
    load_backtest,
    load_dataset,
    load_findings,
    load_resolution,
    load_signatures,
    render_backtest,
    render_dataset,
    render_findings,
    render_resolution,
    render_signatures,
    resolution_from_dict,
    signatures_from_dict,
)


def a_dataset() -> NormalizedDataset:
    """Small, but with every awkward value: an unreadable quantity, an accent, a date, a missing date."""
    readable = BomLine(
        line_id="L00001",
        row_number=1,
        variant_id="A",
        parent_id="A:SA0107",
        child_id="BG12031",
        quantity=Quantity(raw_value="36000", raw_unit="mm", value=36.0, unit="m"),
        sub_assembly_ref=RawText(raw="SA-O107", normalized="SA0107"),
        sub_assembly_designation=RawText(raw="TRAILER BOGIE ", normalized="trailer bogie"),
        component_ref=RawText(raw=" Bgi-2031", normalized="BG12031"),
        designation=RawText(raw="Bogie interface bracket ", normalized="bogie interface bracket"),
        supplier=RawText(raw="Artois Polymères ", normalized="artois polymères"),
        unit_cost=RawNumber(raw="48200,00", normalized=48200.0),
    )
    unreadable = dataclasses.replace(
        readable,
        line_id="L00002",
        row_number=2,
        quantity=Quantity(raw_value="abc", raw_unit="pcs", value=None, unit=None),
        unit_cost=RawNumber(raw="", normalized=None),
    )
    return NormalizedDataset(
        variants=(
            Variant(
                id="A",
                raw_id="a ",
                name=RawText(raw="Standard intermediate car", normalized="standard intermediate car"),
                design_date=RawDate(raw="2019-03-14", normalized=date(2019, 3, 14)),
                region=RawText(raw="Hauts-de-France", normalized="hauts-de-france"),
                seats=RawInt(raw="48", normalized=48),
                bike_spaces=RawInt(raw="none", normalized=None),
                traction=RawText(raw="electric", normalized="electric"),
            ),
        ),
        suppliers=(Supplier(id="artois polymères", raw_names=("Artois Polymères", "Artois Polymères ")),),
        components=(Component(id="BG12031", raw_references=(" Bgi-2031", "BGI-2031"), designations=("bogie interface bracket",)),),
        sub_assemblies=(SubAssembly(id="A:SA0107", variant_id="A", reference_key="SA0107", raw_references=("SA-O107",), designations=("trailer bogie",)),),
        lines=(readable, unreadable),
        notes=(Note(note_id="N001", row_number=1, variant_id="A", date=RawDate(raw="someday", normalized=None), text="Ne pas monter ; voir plan."),),
        issues=(NormalizationIssue(source_file="bom.csv", row_number=2, row_id="L00002", field="quantity", raw="abc", reason="not a number"),),
    )


ALL_TYPES = [value for value in vars(model).values() if dataclasses.is_dataclass(value) and isinstance(value, type)]


# --- the round-trip --------------------------------------------------------------------------


def test_a_dataset_written_and_read_back_is_the_same_dataset(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "normalized.json"
    dump_dataset(a_dataset(), path)
    assert load_dataset(path) == a_dataset()


def test_reading_back_rebuilds_tuples_not_lists() -> None:
    restored = dataset_from_dict(json.loads(render_dataset(a_dataset())))
    assert isinstance(restored.lines, tuple)
    assert isinstance(restored.components[0].raw_references, tuple)
    assert isinstance(restored.suppliers[0].raw_names, tuple)


def test_an_unreadable_value_survives_as_null_and_a_float_as_the_same_float() -> None:
    restored = dataset_from_dict(json.loads(render_dataset(a_dataset())))
    assert restored.lines[1].quantity.value is None and restored.lines[1].quantity.unit is None
    assert restored.lines[0].quantity.value == 36.0 and isinstance(restored.lines[0].quantity.value, float)
    assert restored.notes[0].date.normalized is None
    assert restored.variants[0].design_date.normalized == date(2019, 3, 14)


def test_the_artifact_text_is_stable_readable_and_ends_with_one_newline() -> None:
    text = render_dataset(a_dataset())
    assert text == render_dataset(a_dataset())
    assert text.endswith("}\n") and not text.endswith("\n\n")
    assert "Artois Polymères " in text, "accents are written as they are, not escaped"
    assert json.loads(text) == dataset_to_dict(a_dataset())


def test_the_written_file_has_unix_newlines_and_no_byte_order_mark(tmp_path: Path) -> None:
    path = tmp_path / "normalized.json"
    dump_dataset(a_dataset(), path)
    content = path.read_bytes()
    assert b"\r" not in content and not content.startswith(b"\xef\xbb\xbf")
    assert content == render_dataset(a_dataset()).encode("utf-8")


# --- a wrong artifact is refused, by name ----------------------------------------------------


def test_an_unknown_key_is_refused_and_named() -> None:
    data = dataset_to_dict(a_dataset())
    data["lines"][0]["colour"] = "blue"
    with pytest.raises(ModelError, match=r"lines\[0\].*unknown keys \['colour'\]"):
        dataset_from_dict(data)


def test_a_missing_key_is_refused_and_named() -> None:
    data = dataset_to_dict(a_dataset())
    del data["components"][0]["designations"]
    with pytest.raises(ModelError, match=r"components\[0\] is missing \['designations'\]"):
        dataset_from_dict(data)


def test_a_missing_section_is_refused() -> None:
    data = dataset_to_dict(a_dataset())
    del data["issues"]
    with pytest.raises(ModelError, match="issues"):
        dataset_from_dict(data)


@pytest.mark.parametrize("version", ["0", "2", 1, None])
def test_another_schema_version_is_refused(version: object) -> None:
    data = dataset_to_dict(a_dataset())
    data["schema_version"] = version
    with pytest.raises(ModelError, match="schema_version"):
        dataset_from_dict(data)


def test_a_date_that_is_not_a_date_is_refused() -> None:
    data = dataset_to_dict(a_dataset())
    data["variants"][0]["design_date"]["normalized"] = "14/03/2019"
    with pytest.raises(ModelError, match=r"variants\[0\]\.design_date"):
        dataset_from_dict(data)


def _with(data: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """The artifact dict with one leaf replaced, `lines.0.quantity.value` style."""
    table: Any = data
    *steps, leaf = path.split(".")
    for step in steps:
        table = table[int(step)] if step.isdigit() else table[step]
    table[leaf] = value
    return data


@pytest.mark.parametrize(
    "path, value, message",
    [
        ("suppliers.0.raw_names", None, r"suppliers\[0\]\.raw_names must be an array of strings, got NoneType"),
        ("suppliers.0.raw_names", "abc", r"suppliers\[0\]\.raw_names must be an array of strings, got str"),
        ("components.0.raw_references", [5], r"components\[0\]\.raw_references\[0\] must be a string, got int"),
        ("suppliers.0.id", 5, r"suppliers\[0\]\.id must be a string, got int"),
        ("lines.0.row_number", "x", r"lines\[0\]\.row_number must be an integer, got str"),
        ("lines.0.row_number", True, r"lines\[0\]\.row_number must be an integer, got bool"),
        ("lines.0.quantity.value", "abc", r"lines\[0\]\.quantity\.value must be a number or null, got str"),
        ("lines.0.quantity.value", True, r"lines\[0\]\.quantity\.value must be a number or null, got bool"),
        ("lines.0.quantity.unit", 3, r"lines\[0\]\.quantity\.unit must be a string or null, got int"),
        ("variants.0.seats.normalized", "48", r"variants\[0\]\.seats\.normalized must be an integer or null, got str"),
        # An integer passes the type test and then overflows the conversion; both float leaves are fed one.
        pytest.param("lines.0.quantity.value", 10**400, r"lines\[0\]\.quantity\.value is out of range for a float", id="quantity.value-10**400"),
        pytest.param("lines.0.unit_cost.normalized", 10**400, r"lines\[0\]\.unit_cost\.normalized is out of range for a float", id="unit_cost.normalized-10**400"),
    ],
)
def test_a_leaf_of_the_wrong_type_is_refused_and_named(path: str, value: Any, message: str) -> None:
    """The docstring promises `ModelError`, so a wrong leaf may not be a `TypeError`, a bare `ValueError`, or accepted."""
    with pytest.raises(ModelError, match=message):
        dataset_from_dict(_with(dataset_to_dict(a_dataset()), path, value))


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_the_artifact_is_json_so_a_value_json_cannot_hold_is_refused_at_writing(value: float) -> None:
    """The backstop behind `normalize`'s range check: `Infinity` and `NaN` are Python's dialect, not JSON."""
    line = dataclasses.replace(a_dataset().lines[0], unit_cost=RawNumber(raw="9" * 400, normalized=value))
    with pytest.raises(ValueError, match="JSON"):
        render_dataset(dataclasses.replace(a_dataset(), lines=(line,)))


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_a_number_json_cannot_hold_is_refused_at_reading_too(literal: str) -> None:
    """`json.loads` reads Python's dialect, so a dataset can be loaded that `render_dataset` could never write."""
    text = json.dumps(_with(dataset_to_dict(a_dataset()), "lines.0.quantity.value", "@")).replace('"@"', literal)
    with pytest.raises(ModelError, match=r"lines\[0\]\.quantity\.value must be a finite number or null"):
        dataset_from_dict(json.loads(text))


def test_a_file_that_is_missing_or_not_json_is_a_model_error(tmp_path: Path) -> None:
    with pytest.raises(ModelError, match="not found"):
        load_dataset(tmp_path / "nope.json")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    with pytest.raises(ModelError, match="not valid JSON"):
        load_dataset(tmp_path / "broken.json")


def test_a_path_that_is_not_readable_utf8_text_is_a_model_error(tmp_path: Path) -> None:
    """A directory and a file in another encoding: two `load_dataset` callers would meet a traceback."""
    with pytest.raises(ModelError, match="cannot be read"):
        load_dataset(tmp_path)
    latin1 = tmp_path / "latin1.json"
    latin1.write_bytes('{"supplier": "Artois Polymères"}'.encode("latin-1"))
    with pytest.raises(ModelError, match="cannot be read"):
        load_dataset(latin1)


def test_a_json_file_python_itself_refuses_to_parse_is_a_model_error(tmp_path: Path) -> None:
    """Past the integer-digit limit and past the recursion limit, `json.loads` raises neither `JSONDecodeError`."""
    huge = tmp_path / "huge.json"
    huge.write_text(f'{{"row_number": {"9" * 5000}}}', encoding="utf-8")
    with pytest.raises(ModelError, match="not valid JSON"):
        load_dataset(huge)
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    with pytest.raises(ModelError, match="not valid JSON"):
        load_dataset(deep)


# --- the shape of the types ------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_TYPES, ids=lambda cls: cls.__name__)
def test_every_type_is_frozen(cls: type) -> None:
    assert cls.__dataclass_params__.frozen, f"{cls.__name__} is mutable"  # type: ignore[attr-defined]


def test_a_frozen_instance_really_refuses_assignment() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        a_dataset().lines[0].child_id = "OTHER"  # type: ignore[misc]


def test_a_bom_line_is_the_n_ary_relation() -> None:
    names = {field.name for field in dataclasses.fields(BomLine)}
    assert {"variant_id", "parent_id", "child_id", "quantity"} <= names
    assert {field.name for field in dataclasses.fields(Quantity)} == {"raw_value", "raw_unit", "value", "unit"}


@pytest.mark.parametrize("cls", [Component, Supplier])
def test_a_component_and_a_supplier_never_name_a_variant(cls: type) -> None:
    """Variability is carried by the line: one entity, however many variants use it."""
    assert not [field.name for field in dataclasses.fields(cls) if "variant" in field.name]


def test_the_model_imports_nothing_from_the_package() -> None:
    source = Path(model.__file__).read_text(encoding="utf-8")
    assert "from bomreuse" not in source and "import bomreuse" not in source


# --- the resolution and findings artifacts -----------------------------------------------------


def a_resolution() -> Resolution:
    """One group kept whole and one split in two: every shape the artifact can hold."""
    return Resolution(
        groups=(
            CandidateGroup(
                reference_key="BG12031",
                verdict=GroupVerdict.REVIEW,
                diverging=(Attribute.COST, Attribute.SUPPLIER),
                components=(
                    CanonicalComponent(
                        id="BG12031",
                        reference_key="BG12031",
                        raw_references=(" Bgi-2031", "BGI-2O31"),
                        designations=("bolt set m8, zinc-nickel",),
                        rows=(1, 2),
                    ),
                ),
            ),
            CandidateGroup(
                reference_key="SEATRA111",
                verdict=GroupVerdict.REJECT,
                diverging=(Attribute.DESIGNATION,),
                components=(
                    CanonicalComponent(
                        id="SEATRA111#1",
                        reference_key="SEATRA111",
                        raw_references=("SEAT-RAIL-I",),
                        designations=("floor rail, stainless steel",),
                        rows=(90,),
                    ),
                    CanonicalComponent(
                        id="SEATRA111#2",
                        reference_key="SEATRA111",
                        raw_references=("SEAT-RAIL-1",),
                        designations=("mounting rail, aluminium, mark 1",),
                        rows=(134,),
                    ),
                ),
            ),
        )
    )


def some_findings() -> tuple[Finding, ...]:
    return (
        Finding(
            rule_id="resolution.duplicate_reference",
            confidence=0.95,
            subject="BG12031",
            message="2 spellings of one reference: ' Bgi-2031', 'BGI-2O31'",
            source_rows=(SourceRow(source_file="bom.csv", row_number=1, row_id="L00001"),),
        ),
    )


def test_a_resolution_written_and_read_back_is_the_same_resolution(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "resolution.json"
    dump_resolution(a_resolution(), path)
    restored = load_resolution(path)
    assert restored == a_resolution()
    assert isinstance(restored.groups[0].components[0].rows, tuple)
    assert restored.groups[0].verdict is GroupVerdict.REVIEW


def test_findings_written_and_read_back_are_the_same_findings(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "findings.json"
    dump_findings(some_findings(), path)
    assert load_findings(path) == some_findings()


def test_the_new_artifacts_carry_the_schema_version_and_one_trailing_newline() -> None:
    for text in (render_resolution(a_resolution()), render_findings(some_findings())):
        assert json.loads(text)["schema_version"] == "1"
        assert text.endswith("}\n") and not text.endswith("\n\n")


def test_a_split_group_shows_every_part_among_the_canonical_components() -> None:
    resolution = a_resolution()
    assert [component.id for component in resolution.components] == ["BG12031", "SEATRA111#1", "SEATRA111#2"]
    assert [component.rows for component in resolution.components] == [(1, 2), (90,), (134,)]


@pytest.mark.parametrize(
    "path, value, message",
    [
        ("groups.0.verdict", "maybe", r"groups\[0\]\.verdict is 'maybe', not one of \['auto', 'review', 'reject'\]"),
        ("groups.0.verdict", 1, r"groups\[0\]\.verdict must be a string, got int"),
        ("groups.0.diverging", "cost", r"groups\[0\]\.diverging must be an array, got str"),
        ("groups.0.diverging", ["colour"], r"groups\[0\]\.diverging\[0\] is 'colour'"),
        ("groups.0.components.0.rows", ["1"], r"groups\[0\]\.components\[0\]\.rows\[0\] must be an integer, got str"),
        ("groups.0.components.0.rows", "12", r"groups\[0\]\.components\[0\]\.rows must be an array, got str"),
    ],
)
def test_a_wrong_leaf_of_the_resolution_is_refused_and_named(path: str, value: Any, message: str) -> None:
    data = _with(json.loads(render_resolution(a_resolution())), path, value)
    with pytest.raises(ModelError, match=message):
        resolution_from_dict(data)


@pytest.mark.parametrize(
    "path, value, message",
    [
        ("findings.0.confidence", None, r"findings\[0\]\.confidence must be a number, got null"),
        ("findings.0.confidence", "0.9", r"findings\[0\]\.confidence must be a number or null, got str"),
        ("findings.0.source_rows.0.row_number", "1", r"findings\[0\]\.source_rows\[0\]\.row_number must be an integer, got str"),
    ],
)
def test_a_wrong_leaf_of_the_findings_is_refused_and_named(path: str, value: Any, message: str) -> None:
    data = _with(json.loads(render_findings(some_findings())), path, value)
    with pytest.raises(ModelError, match=message):
        findings_from_dict(data)


@pytest.mark.parametrize("version", ["0", 1, None])
def test_the_new_artifacts_refuse_another_schema_version(version: object) -> None:
    for text, read in ((render_resolution(a_resolution()), resolution_from_dict), (render_findings(some_findings()), findings_from_dict)):
        with pytest.raises(ModelError, match="schema_version"):
            read({**json.loads(text), "schema_version": version})


def test_a_missing_or_unreadable_artifact_is_a_model_error(tmp_path: Path) -> None:
    with pytest.raises(ModelError, match="resolution not found"):
        load_resolution(tmp_path / "nope.json")
    with pytest.raises(ModelError, match="findings not found"):
        load_findings(tmp_path / "nope.json")


# --- the signature and backtest artifacts --------------------------------------------------------


def some_signatures() -> tuple[SubAssemblySignature, ...]:
    return (
        SubAssemblySignature(
            sub_assembly_id="A:SA0101",
            variant_id="A",
            reference_key="SA0101",
            designations=("carbody shell",),
            signature=Signature.from_counts({"SHE11R00F": 1.0, "SHE11SEA1": 1.5}, {"SHE11SEA1": "m"}),
            lines_left_out=0,
        ),
        SubAssemblySignature(
            sub_assembly_id="C:0CCSA0101",
            variant_id="C",
            reference_key="0CCSA0101",
            designations=("carbody shell", "carbody shell, welded"),
            signature=Signature.from_counts({"SHE11R00F": 1.0}),
            lines_left_out=2,
        ),
    )


def a_backtest() -> Backtest:
    """Every shape a prediction can hold: reused, reusable with its diff, and specific."""
    return Backtest(
        target_variant_id="C",
        ancestor_variant_ids=("A", "B"),
        predictions=(
            Prediction(sub_assembly_id="C:SA0101", variant_id="C", reuse_class=ReuseClass.REUSED, ancestor_id="A:SA0101", diff=None),
            Prediction(
                sub_assembly_id="C:0CCSA0315",
                variant_id="C",
                reuse_class=ReuseClass.REUSABLE,
                ancestor_id="B:SA0215",
                diff=SignatureDiff(
                    added=(SignatureItem(component="B1KEH00K", quantity=2.0, unit="pcs"),),
                    removed=(SignatureItem(component="B1KERA11", quantity=1.0, unit="pcs"),),
                    quantity_changed=(
                        QuantityChange(
                            component="SEATF1X",
                            left=SignatureItem(component="SEATF1X", quantity=18.0, unit="pcs"),
                            right=SignatureItem(component="SEATF1X", quantity=16.0, unit="pcs"),
                        ),
                    ),
                ),
            ),
            Prediction(sub_assembly_id="C:0CCSA0314", variant_id="C", reuse_class=ReuseClass.SPECIFIC, ancestor_id="", diff=None),
        ),
    )


def test_signatures_written_and_read_back_are_the_same_signatures(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "signatures.json"
    dump_signatures(some_signatures(), path)
    restored = load_signatures(path)
    assert restored == some_signatures()
    assert isinstance(restored[0].signature.items, tuple)
    assert (restored[0].lines_left_out, restored[1].lines_left_out) == (0, 2)


def test_a_backtest_written_and_read_back_is_the_same_backtest(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "predictions.json"
    dump_backtest(a_backtest(), path)
    restored = load_backtest(path)
    assert restored == a_backtest()
    assert restored.predictions[0].reuse_class is ReuseClass.REUSED
    assert restored.predictions[1].diff is not None and restored.predictions[1].diff.n_qty_diff == 1


def test_the_reuse_artifacts_carry_the_schema_version_and_one_trailing_newline() -> None:
    for text in (render_signatures(some_signatures()), render_backtest(a_backtest())):
        assert json.loads(text)["schema_version"] == "1"
        assert text.endswith("}\n") and not text.endswith("\n\n")


def test_a_signature_naming_one_component_twice_is_refused_at_reading() -> None:
    data = json.loads(render_signatures(some_signatures()))
    items = data["signatures"][0]["signature"]["items"]
    data["signatures"][0]["signature"]["items"] = [items[0], items[0]]
    with pytest.raises(ModelError, match="appears twice"):
        signatures_from_dict(data)


@pytest.mark.parametrize(
    "path, value, message",
    [
        ("signatures.0.signature.items.0.quantity", None, r"signatures\[0\]\.signature\.items\[0\]\.quantity must be a number, got null"),
        ("signatures.0.signature.items.0.unit", 1, r"signatures\[0\]\.signature\.items\[0\]\.unit must be a string, got int"),
        ("signatures.0.designations", "carbody shell", r"signatures\[0\]\.designations must be an array of strings, got str"),
        ("signatures.0.lines_left_out", None, r"signatures\[0\]\.lines_left_out must be an integer, got NoneType"),
    ],
)
def test_a_wrong_leaf_of_the_signatures_is_refused_and_named(path: str, value: Any, message: str) -> None:
    data = _with(json.loads(render_signatures(some_signatures())), path, value)
    with pytest.raises(ModelError, match=message):
        signatures_from_dict(data)


@pytest.mark.parametrize(
    "path, value, message",
    [
        ("backtest.predictions.0.reuse_class", "new", r"backtest\.predictions\[0\]\.reuse_class is 'new', not one of \['reused', 'reusable', 'specific'\]"),
        ("backtest.predictions.0.ancestor_id", None, r"backtest\.predictions\[0\]\.ancestor_id must be a string, got NoneType"),
        ("backtest.predictions.1.diff.quantity_changed", {}, r"backtest\.predictions\[1\]\.diff\.quantity_changed must be an array, got dict"),
        ("backtest.ancestor_variant_ids", "A", r"backtest\.ancestor_variant_ids must be an array of strings, got str"),
    ],
)
def test_a_wrong_leaf_of_the_backtest_is_refused_and_named(path: str, value: Any, message: str) -> None:
    data = _with(json.loads(render_backtest(a_backtest())), path, value)
    with pytest.raises(ModelError, match=message):
        backtest_from_dict(data)


def test_the_reuse_artifacts_refuse_another_schema_version() -> None:
    for text, read in ((render_signatures(some_signatures()), signatures_from_dict), (render_backtest(a_backtest()), backtest_from_dict)):
        with pytest.raises(ModelError, match="schema_version"):
            read({**json.loads(text), "schema_version": "0"})


def test_a_missing_reuse_artifact_is_a_model_error(tmp_path: Path) -> None:
    with pytest.raises(ModelError, match="signatures not found"):
        load_signatures(tmp_path / "nope.json")
    with pytest.raises(ModelError, match="backtest not found"):
        load_backtest(tmp_path / "nope.json")


def test_the_artifacts_a_run_writes_are_named_once() -> None:
    """Five files, said in one place: every test site that lists them derives its list from here."""
    assert RUN_ARTIFACTS == ("normalized.json", "resolution.json", "findings.json", "signatures.json", "predictions.json")
    assert len(set(RUN_ARTIFACTS)) == len(RUN_ARTIFACTS)
