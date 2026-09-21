"""Sub-assembly signatures: what a sub-assembly contains, and what an older one it matches.

The comparison — `distance`, `budget`, `compare`, `verdict` — is the material of spike S1
(docs/ARCHITECTURE.md A1). It was written before the generator existed, because the threshold is
fixed before the data and never tuned against a score (DECISIONS.md 17), and nothing here moves
it: the two numbers are read from `data/dataset_spec.toml` through `spec.py`.

The rest of the module is the client's question. `build_signatures` reads one signature per
sub-assembly off the resolved BOM lines, and `backtest` plays the newest variant as a new tender:
given only the variants designed before it, each of its sub-assemblies comes out *reused*,
*reusable* with the exact diff, or *specific* ([A7]).

Signatures are built on every merged component group, `auto` and `review` alike; only a `reject`
splits one (Decision 26). A part whose supplier, cost or unit diverges between variants is still
that part — the divergence is a finding, not a doubt about identity — and the dataset plants such
a conflict on most of the newest variant's sub-assemblies, so reading `auto` groups only would
blind the backtest exactly where the data is dirty.

Why counting rather than a similarity score: an absolute counting rule speaks the vocabulary
the brief already uses — "differing by 1-3 parts", "same seat, different count" — so the
threshold reads as a contract in the domain's own language rather than as a float nobody may
move (docs/ARCHITECTURE.md, "Approaches considered").

The types live in `model.py`, with every other type the artifacts round-trip through; the rule
lives here.
"""

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from bomreuse.model import (
    Backtest,
    BomLine,
    NormalizedDataset,
    Prediction,
    QuantityChange,
    Resolution,
    ReuseClass,
    Signature,
    SignatureDiff,
    SignatureItem,
    SubAssemblySignature,
    Variant,
)
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


#: The client's word for each verdict, and — read in order — the order a better answer comes in.
#: `identical` describes a pair of signatures; `reused` describes the sub-assembly being asked about.
_CLASS_OF: Final[Mapping[Verdict, ReuseClass]] = {
    Verdict.IDENTICAL: ReuseClass.REUSED,
    Verdict.REUSABLE: ReuseClass.REUSABLE,
    Verdict.SPECIFIC: ReuseClass.SPECIFIC,
}
_BEST_FIRST: Final[tuple[Verdict, ...]] = tuple(_CLASS_OF)


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


# --- one signature per sub-assembly ---------------------------------------------------------


def build_signatures(dataset: NormalizedDataset, resolution: Resolution) -> tuple[SubAssemblySignature, ...]:
    """The signature of every sub-assembly of every variant, over the canonical components.

    A line contributes the component `resolve` gave its row — which is the reference key under
    `auto` and `review`, and one part of a split group under `reject` (Decision 26). Taking the
    component by row rather than by key is what makes the split real: two rows sharing a key end
    up in two different signatures when the designations say they are two products.
    """
    component_of_row = {row: component.id for component in resolution.components for row in component.rows}
    lines_by_sub_assembly: dict[str, list[BomLine]] = defaultdict(list)
    for line in sorted(dataset.lines, key=lambda line: line.row_number):
        if line.parent_id and line.row_number in component_of_row:
            lines_by_sub_assembly[line.parent_id].append(line)

    return tuple(
        SubAssemblySignature(
            sub_assembly_id=sub_assembly.id,
            variant_id=sub_assembly.variant_id,
            reference_key=sub_assembly.reference_key,
            designations=sub_assembly.designations,
            signature=_signature_of(lines_by_sub_assembly[sub_assembly.id], component_of_row),
        )
        for sub_assembly in dataset.sub_assemblies
    )


def _signature_of(lines: list[BomLine], component_of_row: Mapping[int, str]) -> Signature:
    by_component: dict[str, list[BomLine]] = defaultdict(list)
    for line in lines:
        by_component[component_of_row[line.row_number]].append(line)
    items = (_item(component, component_lines) for component, component_lines in by_component.items())
    return Signature.of(item for item in items if item is not None)


def _item(component: str, lines: list[BomLine]) -> SignatureItem | None:
    """What one canonical component contributes to a signature: its total in the sub-assembly.

    A bill of materials names a part once per position, so several lines of one sub-assembly can
    carry the same canonical component and the signature is a multiset of parts, not of lines.
    The unit is the one of the earliest row carrying a readable amount — the representative
    `resolve` already uses when it cites evidence — and a line carrying another unit is left out
    of the total rather than added to it: after normalization the units are SI, so two units for
    one part inside one sub-assembly is a defect for `checks.py` to report, not an amount.

    `None` when no line carries a readable amount: `normalize` has already counted each of them
    as an issue, and `bomreuse run` prints that count.
    """
    amounts = [(line.quantity.value, line.quantity.unit) for line in lines if line.quantity.value is not None and line.quantity.unit]
    if not amounts:
        return None
    unit = amounts[0][1]
    return SignatureItem(component=component, quantity=sum(value for value, carried in amounts if carried == unit), unit=unit)


# --- the backtest ------------------------------------------------------------------------------


def newest_variant(variants: tuple[Variant, ...]) -> Variant | None:
    """The variant that plays the new tender: the latest design date the files declare.

    `None` when no variant carries a readable one — a chronology cannot be invented, and a date
    `normalize` could not read is already a counted issue.
    """
    dated = _dated(variants)
    return _latest(dated)[1] if dated else None


def _dated(variants: tuple[Variant, ...]) -> list[tuple[date, Variant]]:
    """The variants that can be placed in the chronology, with the date that places them."""
    return [(variant.design_date.normalized, variant) for variant in variants if variant.design_date.normalized is not None]


def _latest(dated: list[tuple[date, Variant]]) -> tuple[date, Variant]:
    """The last one designed; the id breaks a tie, so two variants of one day do not swap places."""
    return max(dated, key=lambda entry: (entry[0], entry[1].id))


def backtest(signatures: tuple[SubAssemblySignature, ...], variants: tuple[Variant, ...], thresholds: Thresholds) -> Backtest:
    """The newest variant, classified against the variants designed before it ([A7]).

    Only strictly older variants are candidates. The newest one is not among them — comparing it
    with itself would answer *reused* everywhere — and neither is a variant whose design date is
    unreadable: it cannot be placed in the chronology, and a backtest that took it as an ancestor
    would be claiming the tool knew of a design it may not have known of.
    """
    dated = _dated(variants)
    if not dated:
        return Backtest(target_variant_id="", ancestor_variant_ids=(), predictions=())

    designed_last, newest = _latest(dated)
    older = {variant.id for design_date, variant in dated if design_date < designed_last}
    ancestors = tuple(signature for signature in signatures if signature.variant_id in older)
    return Backtest(
        target_variant_id=newest.id,
        ancestor_variant_ids=tuple(sorted(older)),
        predictions=tuple(_predict(signature, ancestors, thresholds) for signature in signatures if signature.variant_id == newest.id),
    )


def _predict(target: SubAssemblySignature, ancestors: tuple[SubAssemblySignature, ...], thresholds: Thresholds) -> Prediction:
    """The best answer the older variants support, and the one ancestor it is read off.

    Best is the verdict first, then the smallest diff, then the sub-assembly id — a total order,
    so the answer does not move with the order the ancestors happen to arrive in. Several
    ancestors usually reach it and any of them is a valid source (Decision 25): the tool names
    one, and the report of #7 is where the others would belong.
    """
    compared = [(ancestor, compare(ancestor.signature, target.signature, thresholds)) for ancestor in ancestors]
    best = min(compared, key=lambda pair: (_BEST_FIRST.index(pair[1].verdict), pair[1].diff.n_parts_diff + pair[1].diff.n_qty_diff, pair[0].sub_assembly_id), default=None)
    if best is None:
        return _prediction(target, ReuseClass.SPECIFIC, ancestor_id="", diff=None)

    ancestor, comparison = best
    reuse_class = _CLASS_OF[comparison.verdict]
    if reuse_class is ReuseClass.SPECIFIC:
        return _prediction(target, reuse_class, ancestor_id="", diff=None)
    diff = comparison.diff if reuse_class is ReuseClass.REUSABLE else None
    return _prediction(target, reuse_class, ancestor_id=ancestor.sub_assembly_id, diff=diff)


def _prediction(target: SubAssemblySignature, reuse_class: ReuseClass, ancestor_id: str, diff: SignatureDiff | None) -> Prediction:
    return Prediction(
        sub_assembly_id=target.sub_assembly_id,
        variant_id=target.variant_id,
        reuse_class=reuse_class,
        ancestor_id=ancestor_id,
        diff=diff,
    )
