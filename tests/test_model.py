"""The entity model: frozen, n-ary where it must be, and round-tripping through JSON to equal objects."""

import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from bomreuse import model
from bomreuse.model import (
    BomLine,
    Component,
    ModelError,
    NormalizationIssue,
    NormalizedDataset,
    Note,
    Quantity,
    RawDate,
    RawInt,
    RawNumber,
    RawText,
    SubAssembly,
    Supplier,
    Variant,
    dataset_from_dict,
    dataset_to_dict,
    dump_dataset,
    load_dataset,
    render_dataset,
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


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_the_artifact_is_json_so_a_value_json_cannot_hold_is_refused_at_writing(value: float) -> None:
    """The backstop behind `normalize`'s range check: `Infinity` and `NaN` are Python's dialect, not JSON."""
    line = dataclasses.replace(a_dataset().lines[0], unit_cost=RawNumber(raw="9" * 400, normalized=value))
    with pytest.raises(ValueError, match="JSON"):
        render_dataset(dataclasses.replace(a_dataset(), lines=(line,)))


def test_a_file_that_is_missing_or_not_json_is_a_model_error(tmp_path: Path) -> None:
    with pytest.raises(ModelError, match="not found"):
        load_dataset(tmp_path / "nope.json")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    with pytest.raises(ModelError, match="not valid JSON"):
        load_dataset(tmp_path / "broken.json")


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
