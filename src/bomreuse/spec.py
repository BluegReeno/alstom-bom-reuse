"""The dataset spec: the single loader for `data/dataset_spec.toml`.

`generate.py` and `signatures.py` both read the contract through this module; `evaluate.py`
reports against it and never moves it (docs/ARCHITECTURE.md A1).

The parsing is deliberately strict — an unknown key is as fatal as a missing one. A spec
silently missing a story case or carrying a misspelled threshold would be discovered as a
wrong score weeks later, which is exactly the failure mode DECISIONS.md 17 exists to prevent.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: Where the committed contract lives. It is a default, not a constant the pipeline hides
#: behind: every entry point takes the path as an argument.
DEFAULT_SPEC_PATH: Final[Path] = Path(__file__).resolve().parents[2] / "data" / "dataset_spec.toml"

#: The three verdicts of the A1 table. Duplicated as plain strings here rather than imported
#: from `signatures`, so the contract does not depend on the module that applies it.
VERDICTS: Final[frozenset[str]] = frozenset({"identical", "reusable", "specific"})


class SpecError(ValueError):
    """The spec file is unreadable, incomplete, or says something it must not say."""


@dataclass(frozen=True, slots=True)
class Thresholds:
    """The two numbers the reuse rule is made of, and nothing else."""

    max_abs_diff: int
    diff_ratio: float


@dataclass(frozen=True, slots=True)
class DatasetRules:
    """Constraints the generator of #2 must honour when it builds the data."""

    min_subassembly_size: int
    default_unit: str


@dataclass(frozen=True, slots=True)
class StoryCase:
    """One hand-written case of CONTEXT.md's worked example.

    `left` and `right` map a component reference to its quantity; `units` overrides
    `DatasetRules.default_unit` for the components that carry one.
    """

    id: str
    sub_assembly: str
    left_variant: str
    right_variant: str
    expected_verdict: str
    source: str
    left: Mapping[str, float]
    right: Mapping[str, float]
    units: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class TypoFamily:
    """A reference-duplication defect the generator plants.

    `within_rules_reach` is false for the families rules-only resolution cannot catch. They
    are planted on purpose: a dataset that only plants defects the tool catches proves
    nothing (docs/ARCHITECTURE.md A2).
    """

    id: str
    kind: str
    canonical: str
    variants: tuple[str, ...]
    within_rules_reach: bool
    note: str


@dataclass(frozen=True, slots=True)
class MustNotMergePair:
    """Two genuinely different products behind references the folding rules collapse."""

    id: str
    left_reference: str
    right_reference: str
    left_true_component: str
    right_true_component: str
    collapsing_rule: str
    reason: str


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    """The whole contract, parsed."""

    version: str
    thresholds: Thresholds
    dataset: DatasetRules
    story_cases: tuple[StoryCase, ...]
    typo_families: tuple[TypoFamily, ...]
    must_not_merge: tuple[MustNotMergePair, ...]

    def story_case(self, case_id: str) -> StoryCase:
        for case in self.story_cases:
            if case.id == case_id:
                return case
        raise SpecError(f"no story case {case_id!r} in the spec")


def load_spec(path: Path = DEFAULT_SPEC_PATH) -> DatasetSpec:
    """Parse the contract, or raise `SpecError` saying precisely what is wrong with it."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpecError(f"dataset spec not found at {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SpecError(f"dataset spec at {path} is not valid TOML: {exc}") from exc

    _check_keys(
        raw,
        required={"version", "thresholds", "dataset", "story_cases", "typo_families", "must_not_merge"},
        where="the spec root",
    )

    spec = DatasetSpec(
        version=_str(raw["version"], "version"),
        thresholds=_thresholds(raw["thresholds"]),
        dataset=_dataset_rules(raw["dataset"]),
        story_cases=tuple(_story_case(entry, i) for i, entry in enumerate(_list(raw["story_cases"], "story_cases"))),
        typo_families=tuple(_typo_family(entry, i) for i, entry in enumerate(_list(raw["typo_families"], "typo_families"))),
        must_not_merge=tuple(_must_not_merge(entry, i) for i, entry in enumerate(_list(raw["must_not_merge"], "must_not_merge"))),
    )
    _check_coherence(spec)
    return spec


# --- table parsers -----------------------------------------------------------------------


def _thresholds(table: Any) -> Thresholds:
    _check_keys(table, required={"max_abs_diff", "diff_ratio"}, where="[thresholds]")
    max_abs_diff = _int(table["max_abs_diff"], "thresholds.max_abs_diff")
    diff_ratio = _float(table["diff_ratio"], "thresholds.diff_ratio")
    if max_abs_diff < 1:
        raise SpecError(f"thresholds.max_abs_diff must be at least 1, got {max_abs_diff}")
    if not 0.0 < diff_ratio <= 1.0:
        raise SpecError(f"thresholds.diff_ratio must be in (0, 1], got {diff_ratio}")
    return Thresholds(max_abs_diff=max_abs_diff, diff_ratio=diff_ratio)


def _dataset_rules(table: Any) -> DatasetRules:
    _check_keys(table, required={"min_subassembly_size", "default_unit"}, where="[dataset]")
    size = _int(table["min_subassembly_size"], "dataset.min_subassembly_size")
    if size < 1:
        raise SpecError(f"dataset.min_subassembly_size must be at least 1, got {size}")
    return DatasetRules(min_subassembly_size=size, default_unit=_str(table["default_unit"], "dataset.default_unit"))


def _story_case(table: Any, index: int) -> StoryCase:
    where = f"story_cases[{index}]"
    _check_keys(
        table,
        required={"id", "sub_assembly", "left_variant", "right_variant", "expected_verdict", "source", "left", "right"},
        optional={"units"},
        where=where,
    )
    case_id = _str(table["id"], f"{where}.id")
    verdict = _str(table["expected_verdict"], f"{where}.expected_verdict")
    if verdict not in VERDICTS:
        raise SpecError(f"{where} ({case_id}): expected_verdict {verdict!r} is not one of {sorted(VERDICTS)}")
    return StoryCase(
        id=case_id,
        sub_assembly=_str(table["sub_assembly"], f"{where}.sub_assembly"),
        left_variant=_str(table["left_variant"], f"{where}.left_variant"),
        right_variant=_str(table["right_variant"], f"{where}.right_variant"),
        expected_verdict=verdict,
        source=_str(table["source"], f"{where}.source"),
        left=_counts(table["left"], f"{where}.left"),
        right=_counts(table["right"], f"{where}.right"),
        units=_units(table.get("units", {}), f"{where}.units"),
    )


def _typo_family(table: Any, index: int) -> TypoFamily:
    where = f"typo_families[{index}]"
    _check_keys(table, required={"id", "kind", "canonical", "variants", "within_rules_reach", "note"}, where=where)
    variants = tuple(_str(v, f"{where}.variants[]") for v in _list(table["variants"], f"{where}.variants"))
    if not variants:
        raise SpecError(f"{where}: a typo family with no variant plants nothing")
    return TypoFamily(
        id=_str(table["id"], f"{where}.id"),
        kind=_str(table["kind"], f"{where}.kind"),
        canonical=_str(table["canonical"], f"{where}.canonical"),
        variants=variants,
        within_rules_reach=_bool(table["within_rules_reach"], f"{where}.within_rules_reach"),
        note=_str(table["note"], f"{where}.note"),
    )


def _must_not_merge(table: Any, index: int) -> MustNotMergePair:
    where = f"must_not_merge[{index}]"
    _check_keys(
        table,
        required={
            "id",
            "left_reference",
            "right_reference",
            "left_true_component",
            "right_true_component",
            "collapsing_rule",
            "reason",
        },
        where=where,
    )
    pair = MustNotMergePair(
        id=_str(table["id"], f"{where}.id"),
        left_reference=_str(table["left_reference"], f"{where}.left_reference"),
        right_reference=_str(table["right_reference"], f"{where}.right_reference"),
        left_true_component=_str(table["left_true_component"], f"{where}.left_true_component"),
        right_true_component=_str(table["right_true_component"], f"{where}.right_true_component"),
        collapsing_rule=_str(table["collapsing_rule"], f"{where}.collapsing_rule"),
        reason=_str(table["reason"], f"{where}.reason"),
    )
    if pair.left_true_component == pair.right_true_component:
        raise SpecError(f"{where} ({pair.id}): a must-not-merge pair whose two sides are the same true component says nothing")
    if pair.left_reference == pair.right_reference:
        raise SpecError(f"{where} ({pair.id}): the two references are identical, so no folding rule is being tested")
    return pair


# --- coherence ----------------------------------------------------------------------------


def _check_coherence(spec: DatasetSpec) -> None:
    """Cross-table rules the architecture requires the dataset to satisfy."""
    _check_unique((c.id for c in spec.story_cases), "story case")
    _check_unique((f.id for f in spec.typo_families), "typo family")
    _check_unique((p.id for p in spec.must_not_merge), "must-not-merge pair")

    minimum = spec.dataset.min_subassembly_size
    for case in spec.story_cases:
        for side, counts in (("left", case.left), ("right", case.right)):
            if len(counts) < minimum:
                raise SpecError(
                    f"story case {case.id!r} has {len(counts)} components on the {side} side, "
                    f"below dataset.min_subassembly_size = {minimum}"
                )
        unknown = set(case.units) - set(case.left) - set(case.right)
        if unknown:
            raise SpecError(f"story case {case.id!r} declares units for components it does not contain: {sorted(unknown)}")

    if not any(not family.within_rules_reach for family in spec.typo_families):
        raise SpecError(
            "the spec plants no typo family out of reach of the folding rules; resolution recall "
            "would then be 1 by construction and measure nothing (docs/ARCHITECTURE.md A2)"
        )
    if len(spec.must_not_merge) < 2:
        raise SpecError(
            "the spec declares fewer than two must-not-merge pairs; resolution precision would "
            "then be 1 by construction and measure nothing (docs/ARCHITECTURE.md A2)"
        )


def _check_unique(ids: Any, what: str) -> None:
    seen: set[str] = set()
    for value in ids:
        if value in seen:
            raise SpecError(f"duplicate {what} id {value!r}")
        seen.add(value)


# --- primitives ---------------------------------------------------------------------------


def _check_keys(table: Any, *, required: set[str], where: str, optional: set[str] | None = None) -> None:
    if not isinstance(table, dict):
        raise SpecError(f"{where} must be a table, got {type(table).__name__}")
    allowed = required | (optional or set())
    missing = sorted(required - table.keys())
    unknown = sorted(table.keys() - allowed)
    if missing:
        raise SpecError(f"{where} is missing {missing}")
    if unknown:
        raise SpecError(f"{where} has unknown keys {unknown}; allowed: {sorted(allowed)}")


def _counts(table: Any, where: str) -> Mapping[str, float]:
    if not isinstance(table, dict):
        raise SpecError(f"{where} must be a table of component -> quantity, got {type(table).__name__}")
    if not table:
        raise SpecError(f"{where} is empty")
    counts: dict[str, float] = {}
    for reference, quantity in table.items():
        if not isinstance(quantity, (int, float)) or isinstance(quantity, bool):
            raise SpecError(f"{where}[{reference!r}] must be a number, got {quantity!r}")
        if quantity <= 0:
            raise SpecError(f"{where}[{reference!r}] must be positive, got {quantity!r}")
        counts[reference] = float(quantity)
    return counts


def _units(table: Any, where: str) -> Mapping[str, str]:
    if not isinstance(table, dict):
        raise SpecError(f"{where} must be a table of component -> unit, got {type(table).__name__}")
    return {reference: _str(unit, f"{where}[{reference!r}]") for reference, unit in table.items()}


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise SpecError(f"{where} must be an array, got {type(value).__name__}")
    return value


def _str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{where} must be a non-empty string, got {value!r}")
    return value


def _int(value: Any, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SpecError(f"{where} must be an integer, got {value!r}")
    return value


def _float(value: Any, where: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SpecError(f"{where} must be a number, got {value!r}")
    return float(value)


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise SpecError(f"{where} must be a boolean, got {value!r}")
    return value
