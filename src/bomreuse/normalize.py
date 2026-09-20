"""Make sense of the raw strings: reference keys, units to SI, decimal commas, text, dates.

Everything here is a rule, and a small one. There is no string distance anywhere in this
module or in the pipeline (docs/ARCHITECTURE.md A2): two references are the same candidate
when a handful of stated foldings give them the same key, and never because they "look close".
What the rules cannot reach — a transposition, a missing character — stays out of reach, and
`evaluate` measures the shortfall instead of this module hiding it.

A value that cannot be read is not repaired and not dropped: the caller keeps the row, keeps
the raw characters, stores `None` as the normalized value and records why. Each parser below
therefore returns `(value, None)` or `(None, reason)`.
"""

import re
import unicodedata
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Final

from bomreuse.model import Quantity

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
    `str.isalnum` keeps accented letters; dropping them would merge more, not less.
    """
    return "".join(character for character in raw.upper().translate(_FOLD) if character.isalnum())


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
    return Decimal(text.replace(",", ".")), None


def parse_int(raw: str) -> tuple[int | None, str | None]:
    text = raw.strip()
    if not text:
        return None, "empty"
    if not _INTEGER.fullmatch(text):
        return None, "not an integer"
    return int(text), None


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
