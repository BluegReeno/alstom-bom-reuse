"""Ingestion keeps every character of the file, and refuses a file it was not built for."""

import dataclasses
import shutil
from pathlib import Path

import pytest

from bomreuse import generate, ingest
from bomreuse.ingest import BOM_COLUMNS, BOM_FILE, NOTE_COLUMNS, NOTES_FILE, VARIANT_COLUMNS, VARIANTS_FILE, IngestError, read_raw
from bomreuse.model import RawBomRow

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"

BOM_HEADER = ";".join(BOM_COLUMNS)


def raw_dir_with(tmp_path: Path, **replaced: str | bytes) -> Path:
    """A copy of the committed raw directory, with some files replaced (`bom=...`, `notes=...`, `variants=...`)."""
    raw = tmp_path / "raw"
    shutil.copytree(COMMITTED_RAW, raw)
    for stem, content in replaced.items():
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        (raw / f"{stem}.csv").write_bytes(data)
    return raw


def bom_row(**cells: str) -> str:
    defaults = dict(zip(BOM_COLUMNS, ("L1", "A", "SA-0101", "shell", "BGI-2031", "bracket", "1", "pcs", "Acme", "1.00")))
    return ";".join({**defaults, **cells}.values())


# --- the committed dataset ---------------------------------------------------------------------


def test_the_committed_raw_directory_loads() -> None:
    raw = read_raw(COMMITTED_RAW)
    assert (len(raw.variants), len(raw.bom), len(raw.notes)) == (5, 696, 40)
    assert [row.row_number for row in raw.bom] == list(range(1, 697))


@pytest.mark.parametrize("name, attribute", [(VARIANTS_FILE, "variants"), (BOM_FILE, "bom"), (NOTES_FILE, "notes")])
def test_joining_the_ingested_cells_gives_back_the_file_line_for_line(name: str, attribute: str) -> None:
    """The committed files hold no quoted cell, so this is exact: not one character was touched."""
    lines = (COMMITTED_RAW / name).read_text(encoding="utf-8").split("\n")[1:-1]
    rows = getattr(read_raw(COMMITTED_RAW), attribute)
    assert [";".join(dataclasses.astuple(row)[1:]) for row in rows] == lines


def test_the_columns_are_those_the_generator_writes() -> None:
    """The two modules never import each other (docs/ARCHITECTURE.md A3); this test is what keeps them in step."""
    assert (ingest.VARIANTS_FILE, ingest.BOM_FILE, ingest.NOTES_FILE) == (generate.VARIANTS_FILE, generate.BOM_FILE, generate.NOTES_FILE)
    assert ingest.VARIANT_COLUMNS == generate.VARIANT_COLUMNS
    assert ingest.BOM_COLUMNS == generate.BOM_COLUMNS
    assert ingest.NOTE_COLUMNS == generate.NOTE_COLUMNS
    assert tuple(field.name for field in dataclasses.fields(RawBomRow)) == ("row_number", *BOM_COLUMNS)


# --- byte for byte -----------------------------------------------------------------------------


@pytest.mark.parametrize("reference", ["0031", " Bgi-2031", "BGI-2031 ", "bgi 2031", "BGI-2O3I", " BGI-2031", "  "])
def test_a_reference_survives_byte_for_byte(tmp_path: Path, reference: str) -> None:
    raw = raw_dir_with(tmp_path, bom=f"{BOM_HEADER}\n{bom_row(component_ref=reference)}\n")
    assert read_raw(raw).bom[0].component_ref == reference


def test_numbers_units_and_names_are_left_as_typed(tmp_path: Path) -> None:
    raw = raw_dir_with(tmp_path, bom=f"{BOM_HEADER}\n{bom_row(quantity='1,5', unit=' M ', supplier='Artois Polymères ', unit_cost_eur='048200,00')}\n")
    row = read_raw(raw).bom[0]
    assert (row.quantity, row.unit, row.supplier, row.unit_cost_eur) == ("1,5", " M ", "Artois Polymères ", "048200,00")
    assert all(isinstance(value, str) for value in dataclasses.astuple(row)[1:])


def test_a_quoted_cell_may_hold_a_delimiter_or_a_newline(tmp_path: Path) -> None:
    notes = 'note_id;variant_id;date;text\nN1;A;2020-01-01;"Ne pas monter ; voir plan"\nN2;A;2020-01-02;"line one\nline two"\nN3;A;2020-01-03;plain\n'
    rows = read_raw(raw_dir_with(tmp_path, notes=notes)).notes
    assert [row.text for row in rows] == ["Ne pas monter ; voir plan", "line one\nline two", "plain"]
    assert [row.row_number for row in rows] == [1, 2, 3], "rows are counted, not physical lines"


@pytest.mark.parametrize(
    "designation",
    ['"Premium" seat', '"Premium seat'],
    ids=["text after the closing quote", "a quote that never closes"],
)
def test_malformed_quoting_is_refused_not_rewritten(tmp_path: Path, designation: str) -> None:
    """A lenient reader turns `"Premium" seat` into `Premium seat`: a repair, and a silent one."""
    raw = raw_dir_with(tmp_path, bom=f"{BOM_HEADER}\n{bom_row(designation=designation)}\n")
    with pytest.raises(IngestError, match=r"bom\.csv row 1 cannot be parsed as CSV"):
        read_raw(raw)


def test_a_quote_inside_an_unquoted_cell_is_a_character_like_any_other(tmp_path: Path) -> None:
    raw = raw_dir_with(tmp_path, bom=f"{BOM_HEADER}\n{bom_row(designation='Pipe 5\" steel')}\n")
    assert read_raw(raw).bom[0].designation == 'Pipe 5" steel'


def test_an_empty_cell_is_an_empty_string(tmp_path: Path) -> None:
    raw = raw_dir_with(tmp_path, bom=f"{BOM_HEADER}\n{bom_row(supplier='', unit_cost_eur='')}\n")
    row = read_raw(raw).bom[0]
    assert (row.supplier, row.unit_cost_eur) == ("", "")


def test_a_file_with_a_header_and_no_row_is_an_empty_table(tmp_path: Path) -> None:
    assert read_raw(raw_dir_with(tmp_path, notes=";".join(NOTE_COLUMNS) + "\n")).notes == ()


# --- a structure this tool was not built for ---------------------------------------------------


def test_a_missing_file_is_named(tmp_path: Path) -> None:
    raw = raw_dir_with(tmp_path)
    (raw / NOTES_FILE).unlink()
    with pytest.raises(IngestError, match=r"notes\.csv not found in"):
        read_raw(raw)


def test_a_missing_directory_is_reported_the_same_way(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="not found"):
        read_raw(tmp_path / "nowhere")


def test_an_empty_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match=r"bom\.csv is empty"):
        read_raw(raw_dir_with(tmp_path, bom=""))


@pytest.mark.parametrize(
    "header",
    [
        BOM_HEADER.replace("component_ref", "part_number"),
        BOM_HEADER.replace(";", ","),
        BOM_HEADER + ";comment",
        BOM_HEADER.upper(),
        "﻿" + BOM_HEADER,  # a byte-order mark: the contract says UTF-8 without one, and inputs are not repaired
    ],
)
def test_a_header_that_is_not_the_expected_one_is_refused(tmp_path: Path, header: str) -> None:
    with pytest.raises(IngestError, match=r"bom\.csv does not have the expected header") as caught:
        read_raw(raw_dir_with(tmp_path, bom=f"{header}\n{bom_row()}\n"))
    assert "expected:" in str(caught.value) and "found:" in str(caught.value)


@pytest.mark.parametrize(
    "bad_row, cells",
    [("L2;A;SA-0101;shell;BGI-2031;bracket;1;pcs;Acme", 9), (bom_row(line_id="L2") + ";extra", 11), ("", 0)],
    ids=["short", "long", "blank line"],
)
def test_a_row_with_the_wrong_number_of_cells_is_refused_with_its_number(tmp_path: Path, bad_row: str, cells: int) -> None:
    raw = raw_dir_with(tmp_path, bom=f"{BOM_HEADER}\n{bom_row()}\n{bad_row}\n{bom_row(line_id='L3')}\n")
    with pytest.raises(IngestError, match=rf"bom\.csv row 2 has {cells} cells, expected 10"):
        read_raw(raw)


@pytest.mark.parametrize(
    "stem, content, message",
    [
        ("bom", f"{BOM_HEADER}\n{bom_row()}\n{bom_row(line_id='L2')}\n{bom_row()}\n", r"bom\.csv row 3 repeats line_id 'L1', already used by row 1"),
        ("notes", ";".join(NOTE_COLUMNS) + "\nN1;A;2020-01-01;a\nN1;B;2020-01-02;b\n", r"notes\.csv row 2 repeats note_id 'N1'"),
        ("variants", ";".join(VARIANT_COLUMNS) + "\nA;x;2020-01-01;r;1;0;electric\nA;y;2021-01-01;r;1;0;electric\n", r"variants\.csv row 2 repeats variant_id 'A'"),
    ],
)
def test_a_duplicate_id_is_refused(tmp_path: Path, stem: str, content: str, message: str) -> None:
    with pytest.raises(IngestError, match=message):
        read_raw(raw_dir_with(tmp_path, **{stem: content}))


def test_ids_are_compared_exactly_at_this_stage(tmp_path: Path) -> None:
    raw = raw_dir_with(tmp_path, bom=f"{BOM_HEADER}\n{bom_row(line_id='L1')}\n{bom_row(line_id='L1 ')}\n")
    assert [row.line_id for row in read_raw(raw).bom] == ["L1", "L1 "]


def test_a_file_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    latin1 = f"{BOM_HEADER}\n{bom_row(supplier='Artois Polymères')}\n".encode("latin-1")
    with pytest.raises(IngestError, match=r"bom\.csv is not UTF-8"):
        read_raw(raw_dir_with(tmp_path, bom=latin1))
