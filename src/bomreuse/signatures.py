"""Sub-assembly signatures, and the reuse verdict rule.

This module is the material of spike S1 (docs/ARCHITECTURE.md): it is written before the
generator exists, because the threshold is fixed before the data and never tuned against a
score (DECISIONS.md 17). The resolution issue (#4) inherits it rather than reimplementing it.

The rest of `signatures.py` — building signatures from resolved BOM lines, and matching a
variant's sub-assemblies against the older ones — arrives with #4. What is here is the
comparison, and it is complete.

Why counting rather than a similarity score: an absolute counting rule speaks the vocabulary
the brief already uses — "differing by 1-3 parts", "same seat, different count" — so the
threshold reads as a contract in the domain's own language rather than as a float nobody may
move (docs/ARCHITECTURE.md, "Approaches considered").
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from bomreuse.spec import Thresholds

#: Two normalized quantities are the same number when they are this close. Quantities are
#: floats because unit normalization produces them (1,5 m -> 1.5); an exact `==` would make
#: the verdict depend on the order of the arithmetic that produced them.
_QUANTITY_REL_TOL: Final[float] = 1e-9


class Verdict(StrEnum):
    """The A1 table, and nothing beside it."""

    IDENTICAL = "identical"
    REUSABLE = "reusable"
    SPECIFIC = "specific"


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
    makes the comparison below a plain set difference.

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
        the generator of #2 will state what it plants.
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
class Comparison:
    """Everything one comparison of two signatures produces."""

    verdict: Verdict
    diff: SignatureDiff
    budget: int


def distance(left: Signature, right: Signature) -> SignatureDiff:
    """The two counters of the A1 rule, plus the diff they are counted from.

    A component present on both sides with the same quantity but a different unit counts as a
    quantity difference: after normalization the units are SI, so a residual difference means
    the two lines do not describe the same amount. Saying *why* they differ is `checks.py`'s
    job, not this one's.
    """
    left_by_component = left.by_component
    right_by_component = right.by_component

    added = tuple(sorted(item for component, item in right_by_component.items() if component not in left_by_component))
    removed = tuple(sorted(item for component, item in left_by_component.items() if component not in right_by_component))
    quantity_changed = tuple(
        QuantityChange(component=component, left=left_item, right=right_by_component[component])
        for component, left_item in sorted(left_by_component.items())
        if component in right_by_component and not _same_amount(left_item, right_by_component[component])
    )
    return SignatureDiff(added=added, removed=removed, quantity_changed=quantity_changed)


def budget(left: Signature, right: Signature, thresholds: Thresholds) -> int:
    """`min(max_abs_diff, ceil(diff_ratio * min(len(a), len(b))))`.

    The same budget is spent by both counters, so the rule stays symmetric: three quantity
    differences out of five components are no more acceptable than three missing parts.
    """
    smaller = min(len(left), len(right))
    return min(thresholds.max_abs_diff, math.ceil(thresholds.diff_ratio * smaller))


def compare(left: Signature, right: Signature, thresholds: Thresholds) -> Comparison:
    """Classify two signatures, and hand back the evidence and the budget that decided it."""
    diff = distance(left, right)
    allowance = budget(left, right, thresholds)
    if diff.is_empty():
        decided = Verdict.IDENTICAL
    elif diff.n_parts_diff <= allowance and diff.n_qty_diff <= allowance:
        decided = Verdict.REUSABLE
    else:
        decided = Verdict.SPECIFIC
    return Comparison(verdict=decided, diff=diff, budget=allowance)


def verdict(left: Signature, right: Signature, thresholds: Thresholds) -> Verdict:
    """`identical` / `reusable` / `specific`, per the A1 table."""
    return compare(left, right, thresholds).verdict


def _same_amount(left: SignatureItem, right: SignatureItem) -> bool:
    return left.unit == right.unit and math.isclose(left.quantity, right.quantity, rel_tol=_QUANTITY_REL_TOL)
