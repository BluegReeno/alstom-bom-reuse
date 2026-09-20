"""Read the three raw CSV files exactly as they are.

Every value stays the `str` the file holds: nothing is stripped, cast or repaired here
(docs/ARCHITECTURE.md A4). `0031` keeps its zero, `" Bgi-2031"` its space, `1,5` its comma —
those are the defects the tool exists to detect, and a reader that coerced them away would hide
them before anyone saw them. Making sense of the values is `normalize.py`'s job.

The *structure*, on the other hand, is checked strictly: a missing file, a header that is not
the expected one, a row with a cell too many or too few, a duplicate id. Those are not dirty
data, they are a file this tool was not built for, and guessing would shift every column
silently. They stop the run with an `IngestError` naming the file and the row.

The file names and columns are declared here rather than imported from the generator: the
pipeline shares nothing with the code that plants the defects (A3). A test compares the two.
"""

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from bomreuse.model import RawBomRow, RawDataset, RawNoteRow, RawVariantRow

#: `;` is what a French ERP exports, and it lets a decimal comma live unquoted (DECISIONS.md 24).
DELIMITER: Final[str] = ";"

VARIANTS_FILE: Final[str] = "variants.csv"
BOM_FILE: Final[str] = "bom.csv"
NOTES_FILE: Final[str] = "notes.csv"

VARIANT_COLUMNS: Final[tuple[str, ...]] = ("variant_id", "name", "design_date", "region", "seats", "bike_spaces", "traction")
BOM_COLUMNS: Final[tuple[str, ...]] = (
    "line_id",
    "variant_id",
    "sub_assembly_ref",
    "sub_assembly_designation",
    "component_ref",
    "designation",
    "quantity",
    "unit",
    "supplier",
    "unit_cost_eur",
)
NOTE_COLUMNS: Final[tuple[str, ...]] = ("note_id", "variant_id", "date", "text")


class IngestError(ValueError):
    """A raw file is missing, or does not have the structure this tool reads."""


def read_raw(raw_dir: Path) -> RawDataset:
    """The three files of `raw_dir` as typed rows of strings, or an `IngestError`."""
    variants = tuple(RawVariantRow(number, *cells) for number, cells in _read_rows(raw_dir, VARIANTS_FILE, VARIANT_COLUMNS))
    bom = tuple(RawBomRow(number, *cells) for number, cells in _read_rows(raw_dir, BOM_FILE, BOM_COLUMNS))
    notes = tuple(RawNoteRow(number, *cells) for number, cells in _read_rows(raw_dir, NOTES_FILE, NOTE_COLUMNS))

    _check_unique(((row.row_number, row.variant_id) for row in variants), VARIANTS_FILE, "variant_id")
    _check_unique(((row.row_number, row.line_id) for row in bom), BOM_FILE, "line_id")
    _check_unique(((row.row_number, row.note_id) for row in notes), NOTES_FILE, "note_id")
    return RawDataset(variants=variants, bom=bom, notes=notes)


def _read_rows(raw_dir: Path, name: str, columns: tuple[str, ...]) -> list[tuple[int, list[str]]]:
    """`(row number, cells)` for every data row; row 1 is the first row after the header."""
    path = raw_dir / name
    rows: list[tuple[int, list[str]]] = []
    try:
        # newline="" hands line endings to the csv module, so a quoted cell may hold a newline.
        # No `utf-8-sig`, no `skipinitialspace`, no DictReader: the first would repair an input,
        # the second would eat a leading space, the third pads short rows without a word.
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter=DELIMITER)
            header = next(reader, None)
            if header is None:
                raise IngestError(f"{name} is empty: expected the header {DELIMITER.join(columns)}")
            if tuple(header) != columns:
                raise IngestError(f"{name} does not have the expected header.\n  expected: {list(columns)}\n  found:    {header}")
            for number, cells in enumerate(reader, start=1):
                if len(cells) != len(columns):
                    raise IngestError(f"{name} row {number} has {len(cells)} cells, expected {len(columns)}: {cells}")
                rows.append((number, cells))
    except FileNotFoundError as exc:
        raise IngestError(f"{name} not found in {raw_dir}") from exc
    except UnicodeDecodeError as exc:
        raise IngestError(f"{name} is not UTF-8 ({exc.reason} at byte {exc.start}): the raw files are UTF-8 without BOM") from exc
    except csv.Error as exc:
        raise IngestError(f"{name} row {len(rows) + 1} cannot be parsed as CSV: {exc}") from exc
    return rows


def _check_unique(ids: Iterable[tuple[int, str]], name: str, column: str) -> None:
    # Compared as raw strings, exactly: two ids differing by a space are two ids at this stage.
    first_seen: dict[str, int] = {}
    for number, value in ids:
        if value in first_seen:
            raise IngestError(f"{name} row {number} repeats {column} {value!r}, already used by row {first_seen[value]}")
        first_seen[value] = number
