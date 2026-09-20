"""The ground-truth schema: what the generator declares, and what the evaluation scores against.

This is one of the two places pydantic is allowed (DECISIONS.md 19): the ground truth is a file
that arrives from outside the pipeline, written by one program and read by another, so it is
validated at the boundary. Nothing internal uses these models — `generate.py` builds frozen
dataclasses and converts at the very end.

The schema depends on nothing in `bomreuse`, and it holds no path: the ground truth is written
where the command line says and read where the command line says (docs/ARCHITECTURE.md A5).

Identity is owned by the generator (docs/ARCHITECTURE.md A3). Every id here is a
`true_component_id` the generator invented, every reference a raw string as emitted; nothing
in this file is something the pipeline produces, so nothing the pipeline does can move it.
"""

import json
import re
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, model_validator

#: The version of this schema, written into every file so a reader can refuse a stale one.
SCHEMA_VERSION: Final[str] = "1"

_TRUE_ID: Final[re.Pattern[str]] = re.compile(r"^TRUE-\d{4}$")

Label = Literal["reused", "reusable", "new"]
PlantedAs = Literal["open_reuse", "hidden_reuse", "near_reuse", "ref_reused_content_changed", "new"]
DefectType = Literal["duplicate_reference", "unit_conflict", "supplier_conflict", "cost_conflict", "note_contradiction"]
FactType = Literal["replacement", "obsolescence", "restriction"]
Language = Literal["fr", "en", "mixed"]


class _Strict(BaseModel):
    """An unknown key is as fatal as a missing one — the strictness of `spec.py`."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_true_id(value: str, where: str) -> None:
    if not _TRUE_ID.match(value):
        raise ValueError(f"{where}: {value!r} is not a true component id (expected TRUE-dddd)")


# --- identity ------------------------------------------------------------------------------


class TrueComponent(_Strict):
    """One real product, and every raw string that stands for it in the emitted files."""

    true_component_id: str
    designation: str
    base_unit: str
    raw_references: tuple[str, ...]

    @model_validator(mode="after")
    def _check(self) -> "TrueComponent":
        _check_true_id(self.true_component_id, "components[].true_component_id")
        if not self.raw_references:
            raise ValueError(f"component {self.true_component_id} has no raw reference: it was never emitted")
        if len(set(self.raw_references)) != len(self.raw_references):
            raise ValueError(f"component {self.true_component_id} lists a raw reference twice")
        return self


class PlantedFamily(_Strict):
    """A typo family of the spec, with the strings that were actually emitted for it."""

    family_id: str
    true_component_id: str
    within_rules_reach: bool
    emitted: tuple[str, ...]


class MustNotMerge(_Strict):
    """Two different products behind references the folding rules collapse."""

    id: str
    left_reference: str
    right_reference: str
    left_true_component: str
    right_true_component: str


# --- the backtest --------------------------------------------------------------------------


class DiffItem(_Strict):
    true_component_id: str
    quantity: float
    unit: str


class QuantityChange(_Strict):
    true_component_id: str
    left: float
    right: float
    unit: str


class Diff(_Strict):
    """Read ancestor -> newest, like `signatures.SignatureDiff`: what the newest adds and drops."""

    added: tuple[DiffItem, ...]
    removed: tuple[DiffItem, ...]
    quantity_changed: tuple[QuantityChange, ...]


class Ancestor(_Strict):
    """An older sub-assembly, named by the raw reference it was emitted under."""

    variant_id: str
    sub_assembly_ref: str
    diff: Diff | None


class UnsafePart(_Strict):
    """A part of the reused content that a note declares obsolete or replaced."""

    true_component_id: str
    note_id: str


class BacktestLabel(_Strict):
    """The expected answer for one sub-assembly of the newest variant."""

    variant_id: str
    sub_assembly_ref: str
    sub_assembly_designation: str
    label: Label
    planted_as: PlantedAs
    story_case_id: str | None
    ancestors: tuple[Ancestor, ...]
    unsafe: tuple[UnsafePart, ...]

    @model_validator(mode="after")
    def _check(self) -> "BacktestLabel":
        where = f"backtest[{self.sub_assembly_ref!r}]"
        if self.label == "new" and self.ancestors:
            raise ValueError(f"{where}: labelled 'new' but lists {len(self.ancestors)} ancestor(s)")
        if self.label != "new" and not self.ancestors:
            raise ValueError(f"{where}: labelled {self.label!r} but lists no ancestor")
        for ancestor in self.ancestors:
            if self.label == "reusable" and ancestor.diff is None:
                raise ValueError(f"{where}: 'reusable' against {ancestor.sub_assembly_ref!r} carries no diff")
            if self.label == "reused" and ancestor.diff is not None:
                raise ValueError(f"{where}: 'reused' against {ancestor.sub_assembly_ref!r} must not carry a diff")
        return self


# --- defects and notes ---------------------------------------------------------------------


class DefectRecord(_Strict):
    """One planted inconsistency, keyed `(defect_type, true_component_id, variant_pair)`."""

    defect_type: DefectType
    true_component_id: str
    variant_pair: tuple[str, str]
    evidence_line_ids: tuple[str, ...]
    note_id: str | None

    @property
    def key(self) -> tuple[str, str, tuple[str, str]]:
        return (self.defect_type, self.true_component_id, self.variant_pair)

    @model_validator(mode="after")
    def _check(self) -> "DefectRecord":
        if tuple(sorted(self.variant_pair)) != self.variant_pair:
            raise ValueError(f"defect {self.key}: variant_pair {self.variant_pair} is not sorted")
        if self.defect_type == "note_contradiction" and self.note_id is None:
            raise ValueError(f"defect {self.key}: a note contradiction must name its note")
        return self


class NoteFact(_Strict):
    fact_type: FactType
    true_component_id: str
    cited_reference: str
    replaced_by_true_component_id: str | None
    effective_date: str | None
    scope: str | None


class NoteTruth(_Strict):
    """What one note really says. `facts` is empty for the notes that state nothing."""

    note_id: str
    language: Language
    facts: tuple[NoteFact, ...]


# --- the file ------------------------------------------------------------------------------


class GroundTruth(_Strict):
    """The whole ground truth, cross-checked."""

    schema_version: str
    spec_version: str
    seed: int
    newest_variant: str
    components: tuple[TrueComponent, ...]
    typo_families: tuple[PlantedFamily, ...]
    must_not_merge: tuple[MustNotMerge, ...]
    backtest: tuple[BacktestLabel, ...]
    defects: tuple[DefectRecord, ...]
    notes: tuple[NoteTruth, ...]

    @model_validator(mode="after")
    def _check(self) -> "GroundTruth":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version {self.schema_version!r} is not {SCHEMA_VERSION!r}")
        known = self._check_identity()
        note_ids = self._check_notes(known)
        self._check_planted(known)
        self._check_backtest(known, note_ids)
        self._check_defects(known, note_ids)
        return self

    def _check_identity(self) -> dict[str, TrueComponent]:
        known: dict[str, TrueComponent] = {}
        owner: dict[str, str] = {}
        for component in self.components:
            if component.true_component_id in known:
                raise ValueError(f"component {component.true_component_id} is declared twice")
            known[component.true_component_id] = component
            for reference in component.raw_references:
                if reference in owner:
                    raise ValueError(
                        f"raw reference {reference!r} stands for both {owner[reference]} and "
                        f"{component.true_component_id}: the mapping must be injective, or a finding "
                        f"citing that string cannot be scored"
                    )
                owner[reference] = component.true_component_id
        return known

    def _check_notes(self, known: dict[str, TrueComponent]) -> set[str]:
        note_ids: set[str] = set()
        for note in self.notes:
            if note.note_id in note_ids:
                raise ValueError(f"note {note.note_id} is declared twice")
            note_ids.add(note.note_id)
            for fact in note.facts:
                _require(known, fact.true_component_id, f"note {note.note_id}")
                if fact.cited_reference not in known[fact.true_component_id].raw_references:
                    raise ValueError(
                        f"note {note.note_id} cites {fact.cited_reference!r}, which is not a raw reference "
                        f"of {fact.true_component_id}"
                    )
                if fact.replaced_by_true_component_id is not None:
                    _require(known, fact.replaced_by_true_component_id, f"note {note.note_id}")
        return note_ids

    def _check_planted(self, known: dict[str, TrueComponent]) -> None:
        for family in self.typo_families:
            _require(known, family.true_component_id, f"typo family {family.family_id}")
            missing = sorted(set(family.emitted) - set(known[family.true_component_id].raw_references))
            if missing:
                raise ValueError(f"typo family {family.family_id}: {missing} are not raw references of its component")
        for pair in self.must_not_merge:
            for reference, true_id in (
                (pair.left_reference, pair.left_true_component),
                (pair.right_reference, pair.right_true_component),
            ):
                _require(known, true_id, f"must-not-merge pair {pair.id}")
                if reference not in known[true_id].raw_references:
                    raise ValueError(f"must-not-merge pair {pair.id}: {reference!r} was not emitted for {true_id}")
            if pair.left_true_component == pair.right_true_component:
                raise ValueError(f"must-not-merge pair {pair.id}: both sides are {pair.left_true_component}")

    def _check_backtest(self, known: dict[str, TrueComponent], note_ids: set[str]) -> None:
        seen: set[str] = set()
        for label in self.backtest:
            where = f"backtest[{label.sub_assembly_ref!r}]"
            if label.variant_id != self.newest_variant:
                raise ValueError(f"{where}: variant {label.variant_id!r} is not the newest ({self.newest_variant!r})")
            if label.sub_assembly_ref in seen:
                raise ValueError(f"{where}: labelled twice")
            seen.add(label.sub_assembly_ref)
            for ancestor in label.ancestors:
                if ancestor.variant_id == self.newest_variant:
                    raise ValueError(f"{where}: an ancestor cannot belong to the newest variant")
                if ancestor.diff is not None:
                    for item in (*ancestor.diff.added, *ancestor.diff.removed, *ancestor.diff.quantity_changed):
                        _require(known, item.true_component_id, where)
            for unsafe in label.unsafe:
                _require(known, unsafe.true_component_id, where)
                if unsafe.note_id not in note_ids:
                    raise ValueError(f"{where}: unsafe part cites unknown note {unsafe.note_id!r}")

    def _check_defects(self, known: dict[str, TrueComponent], note_ids: set[str]) -> None:
        keys: set[tuple[str, str, tuple[str, str]]] = set()
        for defect in self.defects:
            if defect.key in keys:
                raise ValueError(f"defect key {defect.key} appears twice: the key must identify one record")
            keys.add(defect.key)
            _require(known, defect.true_component_id, f"defect {defect.key}")
            if defect.note_id is not None and defect.note_id not in note_ids:
                raise ValueError(f"defect {defect.key} cites unknown note {defect.note_id!r}")


def _require(known: dict[str, TrueComponent], true_id: str, where: str) -> None:
    if true_id not in known:
        raise ValueError(f"{where} refers to {true_id!r}, which is not a declared component")


# --- reading and writing -------------------------------------------------------------------


def render_ground_truth(truth: GroundTruth) -> str:
    """The exact text of the file. Keys are sorted here; list order is the writer's job."""
    return json.dumps(truth.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def dump_ground_truth(truth: GroundTruth, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_ground_truth(truth))


def load_ground_truth(path: Path) -> GroundTruth:
    return GroundTruth.model_validate_json(path.read_text(encoding="utf-8"))
