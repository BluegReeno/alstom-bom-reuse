"""The dirt: pure, seeded operators that turn a true value into a raw string.

This is defect *planting*, not resolution. Nothing here computes a canonical key, compares two
references or decides whether two strings are the same part — `generate.py` must share no
logic with the `resolve.py` it will be scored against (docs/ARCHITECTURE.md A3). An operator
takes a clean value and a `random.Random`, and returns what a tired human or a legacy export
would have typed instead.

Only the typo kinds the spec declares *within reach* of the folding rules are generated here.
The out-of-reach spellings (transposition, missing character) are literals of
`data/dataset_spec.toml`, placed by hand: generating them would mean inventing defects the
contract never declared.
"""

import random
from decimal import Decimal
from typing import Final

#: The typo kinds this module can generate — the within-reach kinds of the spec.
GENERATED_KINDS: Final[tuple[str, ...]] = ("case_and_whitespace", "separator", "homoglyph")

#: Characters a hurried reader confuses, and what they are mistaken for.
_LOOKALIKES: Final[dict[str, tuple[str, ...]]] = {
    "0": ("O",),
    "O": ("0",),
    "1": ("I", "l"),
    "I": ("1", "l"),
    "l": ("1", "I"),
}

#: Raw spellings of a count. "pcs" is also the base unit of the true model.
_COUNT_UNITS: Final[tuple[str, ...]] = ("pcs", "pcs", "units", "u")

#: base unit -> (sub-unit, how many sub-units make one base unit)
_SUB_UNITS: Final[dict[str, tuple[str, int]]] = {"m": ("mm", 1000), "kg": ("g", 1000)}

BASE_UNITS: Final[frozenset[str]] = frozenset({"pcs", "m", "kg"})


# --- references ---------------------------------------------------------------------------


def can_apply(reference: str, kind: str) -> bool:
    """Whether `typo(reference, kind, ...)` can produce a string different from its input."""
    if kind == "case_and_whitespace":
        return True
    if kind == "separator":
        return "-" in reference
    if kind == "homoglyph":
        return any(character in _LOOKALIKES for character in reference)
    return False


def typo(reference: str, kind: str, rng: random.Random) -> str:
    """One misspelling of `reference`, of the given kind. Never returns its input.

    A no-op typo would silently un-plant a defect, so an inapplicable kind is an error rather
    than a shrug: the caller filters with `can_apply` first.
    """
    if kind not in GENERATED_KINDS:
        raise ValueError(f"typo kind {kind!r} is not generated; only {GENERATED_KINDS} are (out-of-reach spellings are spec literals)")
    if not can_apply(reference, kind):
        raise ValueError(f"a {kind!r} typo cannot change {reference!r}")

    if kind == "case_and_whitespace":
        candidates = [reference.lower(), reference + " ", " " + reference, reference.capitalize(), reference.lower() + " "]
    elif kind == "separator":
        head, _, tail = reference.rpartition("-")
        candidates = [reference.replace("-", ""), reference.replace("-", " "), reference.replace("-", "_"), head + tail]
    else:
        candidates = _lookalike_swaps(reference, rng)

    distinct = [candidate for candidate in dict.fromkeys(candidates) if candidate != reference]
    return rng.choice(distinct)


def _lookalike_swaps(reference: str, rng: random.Random) -> list[str]:
    positions = [index for index, character in enumerate(reference) if character in _LOOKALIKES]
    swapped: list[str] = []
    for index in positions:
        for replacement in _LOOKALIKES[reference[index]]:
            swapped.append(reference[:index] + replacement + reference[index + 1 :])
    # One double swap, so "BGI-2O3I"-like spellings occur too.
    if len(positions) >= 2:
        first, second = sorted(rng.sample(positions, 2))
        characters = list(reference)
        characters[first] = _LOOKALIKES[characters[first]][0]
        characters[second] = _LOOKALIKES[characters[second]][0]
        swapped.append("".join(characters))
    return swapped


# --- numbers ------------------------------------------------------------------------------


def render_quantity(value: float, base_unit: str, rng: random.Random) -> tuple[str, str]:
    """`(quantity, unit)` as raw strings: mixed units, and a decimal comma now and then.

    Whatever comes out converts back to exactly `value` in `base_unit` — the dirt changes the
    spelling of an amount, never the amount.
    """
    if base_unit not in BASE_UNITS:
        raise ValueError(f"unknown base unit {base_unit!r}; the true model uses {sorted(BASE_UNITS)}")
    amount = _decimal(value)

    if base_unit == "pcs":
        return _render_number(amount, rng, pad_chance=0.0), rng.choice(_COUNT_UNITS)

    sub_unit, factor = _SUB_UNITS[base_unit]
    in_sub_unit = amount * factor
    if in_sub_unit == in_sub_unit.to_integral_value() and rng.random() < 0.35:
        return _plain(in_sub_unit), sub_unit
    return _render_number(amount, rng, pad_chance=0.2), base_unit


def render_cost(value: float, rng: random.Random) -> str:
    """A unit cost in euros, two decimals, with a comma about half the time."""
    text = f"{_decimal(value):.2f}"
    return text.replace(".", ",") if rng.random() < 0.5 else text


def _render_number(amount: Decimal, rng: random.Random, *, pad_chance: float) -> str:
    text = _plain(amount)
    if "." not in text and rng.random() < pad_chance:
        text += ".0"
    if "." in text and rng.random() < 0.6:
        text = text.replace(".", ",")
    return text


def _decimal(value: float) -> Decimal:
    # Through str(), never Decimal(float): 0.1 must stay 0.1, not its binary expansion.
    return Decimal(str(value))


def _plain(amount: Decimal) -> str:
    """No exponent, no trailing zeros: 36.0 -> "36", 36000 -> "36000", 1.50 -> "1.5"."""
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


# --- text ---------------------------------------------------------------------------------


def spelling_noise(text: str, rng: random.Random) -> str:
    """Case and trailing-space noise only — the same name, typed by someone else."""
    roll = rng.random()
    if roll < 0.70:
        return text
    if roll < 0.80:
        return text.upper()
    if roll < 0.88:
        return text.lower()
    return text + " "
