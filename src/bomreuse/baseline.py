"""The two naive searches the tool is measured against.

They answer the backtest's question — for each sub-assembly of the newest variant, does one
already exist in the variants designed before it? — the way a sceptic would answer it before any
of this was built: match the reference exactly, or match the name.

**Exact reference** ([A3]) is the search the client already has: two sub-assemblies are the same
one when their reference strings are identical, character for character. **Same name** is the
first objection a data engineer raises — *why not just join on the designation?* In this dataset
the designation is a near-perfect join key, which is precisely why it is worth scoring: it finds
a namesake almost everywhere and cannot tell *identical* from *changed* from *re-designed*.

Both read the **raw rows**, never the normalized ones, and a test enforces it by reading this
module's imports. A baseline reading the normalized dataset would inherit the reference key, the
SI units and the decimal commas the tool's value rests on, and the measured gap would close for
the wrong reason.

Both emit `model.Prediction` in the `ReuseClass` vocabulary, like the tool: `reused` on a match,
`specific` otherwise. Neither can say `reusable` — comparing content is exactly what they do not
do — and neither may emit a ground-truth label: one scorer, three predictors, one language, and
the translation between the two vocabularies lives in `evaluate.py` alone (Decision 30).

The chronology is given, not guessed: `evaluate` hands the same target variant and the same older
variants to all three predictors, so the three answer one question about one set of items. What a
baseline is naive about is how it *matches*, not which variants it is allowed to look at.
"""

from collections import defaultdict
from collections.abc import Callable, Collection
from typing import Final

from bomreuse.model import Prediction, RawBomRow, RawDataset, ReuseClass

#: What the two searches are, in one line each, for the reader of `evaluate`'s output.
EXACT_REFERENCE: Final[str] = "exact reference"
SAME_NAME: Final[str] = "same name"
DESCRIPTIONS: Final[dict[str, str]] = {
    EXACT_REFERENCE: "the raw reference matches an older variant's, character for character",
    SAME_NAME: "the raw designation matches an older variant's, case and spacing aside",
}


def sub_assembly_id(variant_id: str, reference: str) -> str:
    """How a baseline names a sub-assembly: the variant, and the reference as the file spells it.

    Not the tool's id, which is built on the folded reference key: borrowing it would borrow the
    normalization these searches exist to be compared against.
    """
    return f"{variant_id}:{reference}"


def sub_assembly_ids(raw: RawDataset) -> dict[tuple[str, str], str]:
    """`(variant, raw sub-assembly reference) -> the id the baselines predict under`.

    The ground truth names sub-assemblies by the raw reference the files carry, so the scorer
    needs each predictor's own way of naming the same thing. This is the baselines'.
    """
    return {(_variant(row), row.sub_assembly_ref): sub_assembly_id(_variant(row), row.sub_assembly_ref) for row in raw.bom}


def exact_reference(raw: RawDataset, target_variant_id: str, ancestor_variant_ids: Collection[str]) -> tuple[Prediction, ...]:
    """Already exists only if the raw reference string matches an older variant's exactly ([A3])."""
    return _search(raw, target_variant_id, ancestor_variant_ids, lambda row: row.sub_assembly_ref)


def same_name(raw: RawDataset, target_variant_id: str, ancestor_variant_ids: Collection[str]) -> tuple[Prediction, ...]:
    """Already exists if the raw designation matches an older variant's, case and spacing aside."""
    return _search(raw, target_variant_id, ancestor_variant_ids, _name)


def _variant(row: RawBomRow) -> str:
    """The variant a row names, read the way the chronology handed to the search names it.

    The only reading these searches do to a raw cell, and it is not the matching: a baseline that
    took `A ` for a sixth variant would answer about no sub-assembly at all, which would widen the
    gap instead of measuring it.
    """
    return row.variant_id.strip().upper()


def _name(row: RawBomRow) -> str:
    """The designation, case- and whitespace-insensitive, and nothing else."""
    return " ".join(row.sub_assembly_designation.split()).casefold()


def _search(
    raw: RawDataset,
    target_variant_id: str,
    ancestor_variant_ids: Collection[str],
    key_of: Callable[[RawBomRow], str],
) -> tuple[Prediction, ...]:
    """One prediction per sub-assembly of the target variant, matched on `key_of` and nothing else."""
    ancestors = set(ancestor_variant_ids)
    keys: dict[tuple[str, str], set[str]] = {}
    for row in raw.bom:
        variant = _variant(row)
        if (variant != target_variant_id and variant not in ancestors) or not row.sub_assembly_ref:
            continue  # another variant, or a row naming no sub-assembly
        key = key_of(row)
        found = keys.setdefault((variant, row.sub_assembly_ref), set())
        if key:
            # An empty cell is not a key: every sub-assembly missing that column would otherwise
            # be a namesake of every other, and a false *reused* is the worst error made here.
            found.add(key)

    older: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for who, found in keys.items():
        if who[0] in ancestors:
            for key in found:
                older[key].add(who)

    predictions = []
    for who in sorted(who for who in keys if who[0] == target_variant_id):
        matches = sorted({match for key in keys[who] for match in older.get(key, ())})
        predictions.append(
            Prediction(
                sub_assembly_id=sub_assembly_id(*who),
                variant_id=target_variant_id,
                reuse_class=ReuseClass.REUSED if matches else ReuseClass.SPECIFIC,
                # Several older sub-assemblies usually match, and one valid source is enough to
                # reuse from (Decision 25); the first in variant order keeps the answer still.
                ancestor_id=sub_assembly_id(*matches[0]) if matches else "",
                # A search that never reads content has nothing to diff, and says so.
                diff=None,
            )
        )
    return tuple(predictions)
