"""The synthetic dataset: true model first, dirt second, ground truth derived.

Identity is owned by this module and knows nothing about the rules it will be scored against
(docs/ARCHITECTURE.md A3). A **true component** (`TRUE-0042`) is invented first; the raw
reference strings that stand for it — planted typos included — are emitted second; the ground
truth records which strings were emitted for which true component. This module therefore
imports no pipeline module, and computes no canonical key: sharing the resolution logic, or
reimplementing it, would make resolution recall 1 by construction.

Two layers:

- the **story** (`build_true_model`) is seed-independent: the catalogue and the story cases of
  the spec give variants, contents, suppliers, costs, notes, and the declared backtest answers;
- the **dirt** (`render`) is seeded: spellings, units, decimal commas, case noise.

The seed moves the dirt, never the story (DECISIONS.md 17). The backtest labels are declared
in the catalogue, not computed here with the verdict rule: a test confronts the two, so a bug
in the rule cannot hide on both sides at once. The diff written next to a `reusable` label is
bookkeeping on two declared contents — it applies no budget and decides no class.
"""

import csv
import random
from collections import Counter, defaultdict
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from operator import attrgetter
from pathlib import Path
from typing import Final

from bomreuse import catalogue
from bomreuse import ground_truth as gt
from bomreuse.catalogue import ComponentDef, FactScript, NoteScript, VariantDef
from bomreuse.dirt import BASE_UNITS, render_cost, render_quantity, spelling_noise, typo
from bomreuse.spec import DatasetSpec

#: The seed of the committed dataset. A default, not a hidden constant — the CLI takes `--seed`.
DEFAULT_SEED: Final[int] = 20260920

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


class GenerationError(ValueError):
    """The catalogue and the spec cannot be turned into an honest dataset."""


# --- the true model ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Part:
    """A true component: the identity the ground truth is keyed on."""

    true_id: str
    definition: ComponentDef


@dataclass(frozen=True, slots=True)
class TrueLine:
    """One BOM line as it truly is: clean reference, base unit, true supplier and cost."""

    variant_id: str
    sub_assembly: str
    sub_assembly_ref: str
    reference: str
    true_id: str
    quantity: float
    base_unit: str
    supplier: str
    unit_cost: float


@dataclass(frozen=True, slots=True)
class TrueModel:
    """Everything the dataset says, before anyone mistyped it. Seed-independent."""

    variants: tuple[VariantDef, ...]
    newest: str
    parts: Mapping[str, Part]
    contents: Mapping[tuple[str, str], Mapping[str, float]]
    sub_assembly_refs: Mapping[tuple[str, str], str]
    lines: tuple[TrueLine, ...]
    notes: tuple[tuple[str, NoteScript], ...]

    def older_variants(self) -> tuple[VariantDef, ...]:
        return tuple(variant for variant in self.variants if variant.id != self.newest)


def build_true_model(spec: DatasetSpec) -> TrueModel:
    """Resolve the catalogue against the spec. No randomness here, on purpose."""
    variants = tuple(sorted(catalogue.VARIANTS, key=lambda variant: variant.design_date))
    parts = _assign_true_ids(spec)
    contents = catalogue.contents(spec)

    suppliers = {(o.reference, o.variant_id): o.supplier for o in catalogue.SUPPLIER_OVERRIDES}
    costs = {(o.reference, o.variant_id): o.unit_cost for o in catalogue.COST_OVERRIDES}

    lines: list[TrueLine] = []
    sub_assembly_refs: dict[tuple[str, str], str] = {}
    for variant in variants:
        for definition in catalogue.SUB_ASSEMBLIES:
            if definition.variant_id != variant.id:
                continue
            key = (variant.id, definition.name)
            sub_assembly_refs[key] = definition.reference
            counts = contents[key]
            if len(counts) < spec.dataset.min_subassembly_size:
                raise GenerationError(
                    f"sub-assembly {key} holds {len(counts)} components, below dataset.min_subassembly_size "
                    f"= {spec.dataset.min_subassembly_size}"
                )
            for reference, quantity in counts.items():
                if reference not in parts:
                    raise GenerationError(f"sub-assembly {key} uses {reference!r}, which is not in the component master")
                definition_of = parts[reference].definition
                lines.append(
                    TrueLine(
                        variant_id=variant.id,
                        sub_assembly=definition.name,
                        sub_assembly_ref=definition.reference,
                        reference=reference,
                        true_id=parts[reference].true_id,
                        quantity=quantity,
                        base_unit=definition_of.base_unit,
                        supplier=suppliers.get((reference, variant.id), definition_of.supplier),
                        unit_cost=costs.get((reference, variant.id), definition_of.unit_cost),
                    )
                )

    notes = tuple((f"N{index:03d}", script) for index, script in enumerate(catalogue.NOTES, start=1))
    return TrueModel(
        variants=variants,
        newest=variants[-1].id,
        parts=parts,
        contents=contents,
        sub_assembly_refs=sub_assembly_refs,
        lines=tuple(lines),
        notes=notes,
    )


def _assign_true_ids(spec: DatasetSpec) -> dict[str, Part]:
    """`TRUE-0001`… in catalogue order, skipping the ids the spec reserves for its must-not-merge pairs."""
    reserved: dict[str, str] = {}
    for pair in spec.must_not_merge:
        reserved[pair.left_reference] = pair.left_true_component
        reserved[pair.right_reference] = pair.right_true_component
    reserved_ids = set(reserved.values())

    parts: dict[str, Part] = {}
    counter = 0
    for definition in catalogue.COMPONENTS:
        if definition.reference in parts:
            raise GenerationError(f"component {definition.reference!r} is declared twice in the master")
        if definition.reference in reserved:
            true_id = reserved[definition.reference]
        else:
            counter += 1
            while f"TRUE-{counter:04d}" in reserved_ids:
                counter += 1
            true_id = f"TRUE-{counter:04d}"
        parts[definition.reference] = Part(true_id=true_id, definition=definition)

    missing = sorted(set(reserved) - set(parts))
    if missing:
        raise GenerationError(f"the spec's must-not-merge references {missing} are not in the component master")
    for family in spec.typo_families:
        if family.canonical not in parts:
            raise GenerationError(f"typo family {family.id!r}: canonical {family.canonical!r} is not in the component master")
    return parts


# --- the dirt ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BomRow:
    """A raw BOM row, every value a string — plus, in memory only, the truth behind it."""

    line_id: str
    variant_id: str
    sub_assembly_ref: str
    sub_assembly_designation: str
    component_ref: str
    designation: str
    quantity: str
    unit: str
    supplier: str
    unit_cost_eur: str
    true: TrueLine
    dimension: str

    def raw(self) -> tuple[str, ...]:
        return tuple(getattr(self, column) for column in BOM_COLUMNS)


@dataclass(frozen=True, slots=True)
class NoteRow:
    note_id: str
    variant_id: str
    date: str
    text: str
    script: NoteScript
    cited_reference: str | None

    def raw(self) -> tuple[str, ...]:
        return (self.note_id, self.variant_id, self.date, self.text)


@dataclass(frozen=True, slots=True)
class Dataset:
    variants: tuple[VariantDef, ...]
    bom: tuple[BomRow, ...]
    notes: tuple[NoteRow, ...]


def _rng(seed: int, concern: str) -> random.Random:
    """One generator per concern, so touching the units does not reshuffle the typos.

    A string seed is hashed with SHA-512 by `random`, independently of PYTHONHASHSEED.
    """
    return random.Random(f"{seed}:{concern}")


def render(model: TrueModel, spec: DatasetSpec, seed: int) -> Dataset:
    """Apply the dirt. Same model, same seed: same rows."""
    spellings = _place_spellings(model, spec, seed)
    unit_conflicts = {(c.variant_id, c.sub_assembly, c.reference): c for c in catalogue.UNIT_CONFLICTS}
    for conflict in unit_conflicts.values():
        if conflict.raw_unit not in BASE_UNITS:
            raise GenerationError(f"unit conflict on {conflict.reference!r}: {conflict.raw_unit!r} is not a base unit")

    units, costs, text = _rng(seed, "units"), _rng(seed, "costs"), _rng(seed, "text")
    sub_assembly_designations: dict[tuple[str, str], str] = {}
    rows: list[BomRow] = []
    for index, line in enumerate(model.lines):
        key = (line.variant_id, line.sub_assembly)
        if key not in sub_assembly_designations:
            sub_assembly_designations[key] = spelling_noise(line.sub_assembly, text)
        conflict = unit_conflicts.get((line.variant_id, line.sub_assembly, line.reference))
        if conflict is not None:
            quantity, unit, dimension = conflict.raw_quantity, conflict.raw_unit, conflict.raw_unit
        else:
            quantity, unit = render_quantity(line.quantity, line.base_unit, units)
            dimension = line.base_unit
        rows.append(
            BomRow(
                line_id=f"L{index + 1:05d}",
                variant_id=line.variant_id,
                sub_assembly_ref=line.sub_assembly_ref,
                sub_assembly_designation=sub_assembly_designations[key],
                component_ref=spellings.get(index, line.reference),
                designation=spelling_noise(model.parts[line.reference].definition.designation, text),
                quantity=quantity,
                unit=unit,
                supplier=spelling_noise(line.supplier, text),
                unit_cost_eur=render_cost(line.unit_cost, costs),
                true=line,
                dimension=dimension,
            )
        )
    return Dataset(variants=model.variants, bom=tuple(rows), notes=_render_notes(model, seed))


def _place_spellings(model: TrueModel, spec: DatasetSpec, seed: int) -> dict[int, str]:
    """Which line is misspelled, and how. Every spelling the spec declares is placed — by force.

    The seed only picks *which* eligible line gets which spelling. Out-of-reach spellings go to
    an older variant unless the catalogue forces a place: the newest variant is allowed exactly
    one of them.
    """
    rng = _rng(seed, "typos")
    lines_of: dict[str, list[int]] = defaultdict(list)
    for index, line in enumerate(model.lines):
        lines_of[line.reference].append(index)
    placed: dict[int, str] = {}

    literals = [(family, spelling) for family in spec.typo_families for spelling in family.variants]
    literals.sort(key=lambda item: item[1] not in catalogue.FORCED_SPELLINGS)  # forced places first; stable
    for family, spelling in literals:
        pool = [index for index in lines_of[family.canonical] if index not in placed]
        if spelling in catalogue.FORCED_SPELLINGS:
            place = catalogue.FORCED_SPELLINGS[spelling]
            pool = [i for i in pool if (model.lines[i].variant_id, model.lines[i].sub_assembly) == place]
        elif not family.within_rules_reach:
            pool = [i for i in pool if model.lines[i].variant_id != model.newest]
        if not pool:
            raise GenerationError(f"typo family {family.id!r}: no line left to carry the spelling {spelling!r}")
        placed[rng.choice(pool)] = spelling

    for family in spec.typo_families:
        if all(index in placed for index in lines_of[family.canonical]):
            raise GenerationError(f"typo family {family.id!r}: the clean reference {family.canonical!r} is emitted nowhere")

    for plan in catalogue.TYPO_PLANS:
        pool = [index for index in lines_of[plan.reference] if index not in placed]
        if plan.places:
            chosen = [i for i in pool if (model.lines[i].variant_id, model.lines[i].sub_assembly) in plan.places]
            if len(chosen) != len(plan.places):
                raise GenerationError(f"typo plan for {plan.reference!r}: the places {plan.places} are not all available")
        else:
            if len(pool) < 2:
                raise GenerationError(f"typo plan for {plan.reference!r}: fewer than two lines, no duplicate can be planted")
            chosen = rng.sample(pool, min(rng.choice((1, 2)), len(pool) - 1))
        for index in chosen:
            placed[index] = typo(plan.reference, plan.kind, rng)
    return placed


def _render_notes(model: TrueModel, seed: int) -> tuple[NoteRow, ...]:
    """Wordings are shuffled by the seed, then dealt in turn inside each (fact type, language) group."""
    rng = _rng(seed, "notes")
    wordings: dict[tuple[str, str], list[str]] = {}
    for group in sorted(catalogue.NOTE_TEMPLATES):
        templates = list(catalogue.NOTE_TEMPLATES[group])
        rng.shuffle(templates)
        wordings[group] = templates
    dealt: Counter[tuple[str, str]] = Counter()

    rows: list[NoteRow] = []
    for note_id, script in model.notes:
        if script.fact is None:
            if script.text is None:
                raise GenerationError(f"note {note_id} states no fact and has no text")
            rows.append(NoteRow(note_id, script.variant_id, script.date, script.text, script, None))
            continue
        group = (script.fact.fact_type, script.language)
        template = wordings[group][dealt[group] % len(wordings[group])]
        dealt[group] += 1
        cited = script.fact.cited_as or script.fact.reference
        rows.append(NoteRow(note_id, script.variant_id, script.date, _word(template, script.fact, cited), script, cited))
    return tuple(rows)


def _word(template: str, fact: FactScript, cited: str) -> str:
    scope_en, scope_fr = catalogue.SCOPE_WORDING[fact.scope] if fact.scope else ("", "")
    date_iso = fact.effective_date or ""
    date_fr = "/".join(reversed(date_iso.split("-"))) if date_iso else ""
    return template.format(
        ref=cited, new=fact.replaced_by or "", date_iso=date_iso, date_fr=date_fr, scope_en=scope_en, scope_fr=scope_fr
    )


# --- the ground truth ----------------------------------------------------------------------


def derive_ground_truth(model: TrueModel, dataset: Dataset, spec: DatasetSpec, seed: int) -> gt.GroundTruth:
    """Everything the evaluation will need, derived mechanically from the model and the emitted strings."""
    references = _raw_references(model, dataset)
    contradictions = _note_contradictions(model, dataset)
    try:
        return gt.GroundTruth(
            schema_version=gt.SCHEMA_VERSION,
            spec_version=spec.version,
            seed=seed,
            newest_variant=model.newest,
            components=tuple(
                gt.TrueComponent(
                    true_component_id=part.true_id,
                    designation=part.definition.designation,
                    base_unit=part.definition.base_unit,
                    raw_references=tuple(sorted(references[part.true_id])),
                )
                for part in sorted(model.parts.values(), key=lambda part: part.true_id)
            ),
            typo_families=_planted_families(model, spec, references),
            must_not_merge=tuple(
                gt.MustNotMerge(
                    id=pair.id,
                    left_reference=pair.left_reference,
                    right_reference=pair.right_reference,
                    left_true_component=pair.left_true_component,
                    right_true_component=pair.right_true_component,
                )
                for pair in sorted(spec.must_not_merge, key=lambda pair: pair.id)
            ),
            backtest=_backtest(model, contradictions),
            defects=_defects(model, dataset, contradictions),
            notes=_note_truths(model, dataset),
        )
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise GenerationError(f"the generated ground truth does not hold together: {exc}") from exc


def _raw_references(model: TrueModel, dataset: Dataset) -> dict[str, set[str]]:
    """`true id -> raw strings`, BOM and notes together. One string never stands for two components."""
    owner: dict[str, str] = {}
    references: dict[str, set[str]] = {part.true_id: set() for part in model.parts.values()}

    def record(raw: str, true_id: str) -> None:
        if owner.setdefault(raw, true_id) != true_id:
            raise GenerationError(
                f"the raw reference {raw!r} stands for both {owner[raw]} and {true_id}; "
                f"a finding citing it could not be scored (try another seed, or fix the catalogue)"
            )
        references[true_id].add(raw)

    for row in dataset.bom:
        record(row.component_ref, row.true.true_id)
    for note in dataset.notes:
        fact = note.script.fact
        if fact is not None and note.cited_reference is not None:
            record(note.cited_reference, model.parts[fact.reference].true_id)
            if fact.replaced_by is not None:
                record(fact.replaced_by, model.parts[fact.replaced_by].true_id)

    never = sorted(true_id for true_id, raws in references.items() if not raws)
    if never:
        raise GenerationError(f"components {never} are in the master but are neither emitted nor cited")
    return references


def _planted_families(model: TrueModel, spec: DatasetSpec, references: Mapping[str, set[str]]) -> tuple[gt.PlantedFamily, ...]:
    families: list[gt.PlantedFamily] = []
    for family in sorted(spec.typo_families, key=lambda family: family.id):
        true_id = model.parts[family.canonical].true_id
        missing = sorted(set(family.variants) - references[true_id])
        if missing:
            raise GenerationError(f"typo family {family.id!r}: the spellings {missing} were not emitted")
        families.append(
            gt.PlantedFamily(
                family_id=family.id,
                true_component_id=true_id,
                within_rules_reach=family.within_rules_reach,
                emitted=tuple(sorted(family.variants)),
            )
        )
    return tuple(families)


@dataclass(frozen=True, slots=True)
class _Contradiction:
    """A note filed on one variant, a variant whose BOM violates it, and the part in question."""

    note_id: str
    fact: FactScript
    filed_on: str
    offender: str
    true_id: str


def _note_contradictions(model: TrueModel, dataset: Dataset) -> tuple[_Contradiction, ...]:
    """Obsolete or replaced on date d, and a variant designed after d still carries the part;
    or restricted for a scope, and a variant in that scope carries the part."""
    carriers: dict[str, set[str]] = defaultdict(set)
    for line in model.lines:
        carriers[line.reference].add(line.variant_id)

    found: list[_Contradiction] = []
    for note in dataset.notes:
        fact = note.script.fact
        if fact is None:
            continue
        if fact.fact_type == "restriction":
            if fact.scope not in catalogue.SCOPES:
                raise GenerationError(f"note {note.note_id}: unknown restriction scope {fact.scope!r}")
            concerned = [v for v in model.variants if v.id in catalogue.SCOPES[fact.scope]]
        else:
            if fact.effective_date is None:
                raise GenerationError(f"note {note.note_id}: a {fact.fact_type} needs an effective date")
            concerned = [v for v in model.variants if v.design_date > fact.effective_date]
        for variant in concerned:
            if variant.id in carriers[fact.reference]:
                found.append(_Contradiction(note.note_id, fact, note.variant_id, variant.id, model.parts[fact.reference].true_id))
    return tuple(found)


def _backtest(model: TrueModel, contradictions: Sequence[_Contradiction]) -> tuple[gt.BacktestLabel, ...]:
    older = [variant.id for variant in model.older_variants()]
    labels: list[gt.BacktestLabel] = []
    for declaration in catalogue.LABELS:
        key = (model.newest, declaration.name)
        if key not in model.contents:
            raise GenerationError(f"a label is declared for {declaration.name!r}, which the newest variant does not carry")
        content = model.contents[key]

        ancestors: list[gt.Ancestor] = []
        if declaration.label == "reused":
            for (variant_id, name), other in model.contents.items():
                if variant_id in older and other == content:
                    ancestors.append(gt.Ancestor(variant_id=variant_id, sub_assembly_ref=model.sub_assembly_refs[(variant_id, name)], diff=None))
        elif declaration.label == "reusable":
            for variant_id in declaration.reusable_from:
                ancestor_key = (variant_id, declaration.name)
                if variant_id not in older or ancestor_key not in model.contents:
                    raise GenerationError(f"{declaration.name!r}: {variant_id!r} is declared as an ancestor but does not carry it")
                ancestors.append(
                    gt.Ancestor(
                        variant_id=variant_id,
                        sub_assembly_ref=model.sub_assembly_refs[ancestor_key],
                        diff=_diff(model, model.contents[ancestor_key], content),
                    )
                )

        unsafe = sorted(
            {
                (c.true_id, c.note_id)
                for c in contradictions
                if c.offender == model.newest
                and c.fact.fact_type != "restriction"
                and c.fact.reference in content
                and declaration.label != "new"
            }
        )
        labels.append(
            gt.BacktestLabel(
                variant_id=model.newest,
                sub_assembly_ref=model.sub_assembly_refs[key],
                sub_assembly_designation=declaration.name,
                label=declaration.label,
                planted_as=declaration.planted_as,
                story_case_id=declaration.story_case_id,
                ancestors=tuple(sorted(ancestors, key=lambda a: (a.variant_id, a.sub_assembly_ref))),
                unsafe=tuple(gt.UnsafePart(true_component_id=true_id, note_id=note_id) for true_id, note_id in unsafe),
            )
        )
    return tuple(sorted(labels, key=lambda label: label.sub_assembly_ref))


def _diff(model: TrueModel, ancestor: Mapping[str, float], newest: Mapping[str, float]) -> gt.Diff:
    """What the newest content adds to, drops from and changes in the ancestor's. Bookkeeping, not a verdict."""

    def item(reference: str, quantity: float) -> gt.DiffItem:
        part = model.parts[reference]
        return gt.DiffItem(true_component_id=part.true_id, quantity=quantity, unit=part.definition.base_unit)

    added = [item(reference, quantity) for reference, quantity in newest.items() if reference not in ancestor]
    removed = [item(reference, quantity) for reference, quantity in ancestor.items() if reference not in newest]
    changed = [
        gt.QuantityChange(
            true_component_id=model.parts[reference].true_id,
            left=quantity,
            right=newest[reference],
            unit=model.parts[reference].definition.base_unit,
        )
        for reference, quantity in ancestor.items()
        if reference in newest and newest[reference] != quantity
    ]
    by_id = attrgetter("true_component_id")
    return gt.Diff(
        added=tuple(sorted(added, key=by_id)),
        removed=tuple(sorted(removed, key=by_id)),
        quantity_changed=tuple(sorted(changed, key=by_id)),
    )


def _defects(model: TrueModel, dataset: Dataset, contradictions: Sequence[_Contradiction]) -> tuple[gt.DefectRecord, ...]:
    """One record per `(defect type, true component, variant pair)` whose two sides truly differ."""
    rows_of: dict[str, dict[str, list[BomRow]]] = defaultdict(lambda: defaultdict(list))
    for row in dataset.bom:
        rows_of[row.true.true_id][row.variant_id].append(row)

    records: list[gt.DefectRecord] = []
    for true_id in sorted(rows_of):
        by_variant = rows_of[true_id]
        observed: dict[str, dict[str, set[Hashable]]] = {
            "duplicate_reference": {v: {row.component_ref for row in rows} for v, rows in by_variant.items()},
            "unit_conflict": {v: {row.dimension for row in rows} for v, rows in by_variant.items()},
            "supplier_conflict": {v: {row.true.supplier for row in rows} for v, rows in by_variant.items()},
            "cost_conflict": {v: {row.true.unit_cost for row in rows} for v, rows in by_variant.items()},
        }
        for defect_type, values in observed.items():
            for pair in _pairs_that_differ(values):
                line_ids = sorted({row.line_id for variant_id in set(pair) for row in by_variant[variant_id]})
                records.append(
                    gt.DefectRecord(
                        defect_type=defect_type,  # type: ignore[arg-type]
                        true_component_id=true_id,
                        variant_pair=pair,
                        evidence_line_ids=tuple(line_ids),
                        note_id=None,
                    )
                )

    for contradiction in contradictions:
        offending = rows_of[contradiction.true_id][contradiction.offender]
        first, second = sorted((contradiction.filed_on, contradiction.offender))
        records.append(
            gt.DefectRecord(
                defect_type="note_contradiction",
                true_component_id=contradiction.true_id,
                variant_pair=(first, second),
                evidence_line_ids=tuple(sorted(row.line_id for row in offending)),
                note_id=contradiction.note_id,
            )
        )
    return tuple(sorted(records, key=lambda record: record.key))


def _pairs_that_differ(values: Mapping[str, set[Hashable]]) -> Iterable[tuple[str, str]]:
    """Sorted variant pairs whose lines do not all say the same thing; `(X, X)` when X disagrees with itself."""
    variants = sorted(values)
    for position, first in enumerate(variants):
        for second in variants[position:]:
            if len(values[first] | values[second]) > 1:
                yield (first, second)


def _note_truths(model: TrueModel, dataset: Dataset) -> tuple[gt.NoteTruth, ...]:
    truths: list[gt.NoteTruth] = []
    for note in dataset.notes:
        fact = note.script.fact
        facts: tuple[gt.NoteFact, ...] = ()
        if fact is not None and note.cited_reference is not None:
            facts = (
                gt.NoteFact(
                    fact_type=fact.fact_type,
                    true_component_id=model.parts[fact.reference].true_id,
                    cited_reference=note.cited_reference,
                    replaced_by_true_component_id=model.parts[fact.replaced_by].true_id if fact.replaced_by else None,
                    effective_date=fact.effective_date,
                    scope=fact.scope,
                ),
            )
        truths.append(gt.NoteTruth(note_id=note.note_id, language=note.script.language, facts=facts))
    return tuple(sorted(truths, key=lambda truth: truth.note_id))


# --- files ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GenerationSummary:
    seed: int
    raw_dir: Path
    ground_truth_path: Path
    lines_per_variant: Mapping[str, int]
    notes: int
    components: int
    defects: Mapping[str, int]

    @property
    def bom_lines(self) -> int:
        return sum(self.lines_per_variant.values())


def write_raw(dataset: Dataset, out_dir: Path) -> None:
    """The pipeline's only input: three `;`-separated UTF-8 files, every value a string."""
    out_dir.mkdir(parents=True, exist_ok=True)
    variants = [(v.id, v.name, v.design_date, v.region, str(v.seats), str(v.bike_spaces), v.traction) for v in dataset.variants]
    _write_csv(out_dir / VARIANTS_FILE, VARIANT_COLUMNS, variants)
    _write_csv(out_dir / BOM_FILE, BOM_COLUMNS, (row.raw() for row in dataset.bom))
    _write_csv(out_dir / NOTES_FILE, NOTE_COLUMNS, (note.raw() for note in dataset.notes))


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[str]]) -> None:
    # `;` is what a French ERP exports, and it lets a decimal comma live unquoted. The csv
    # module's default terminator is \r\n: byte-identity wants one we control.
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def generate(spec: DatasetSpec, seed: int, out_dir: Path, ground_truth_path: Path) -> GenerationSummary:
    """Build, render, derive, write. Both destinations are given by the caller (docs/ARCHITECTURE.md A5)."""
    model = build_true_model(spec)
    dataset = render(model, spec, seed)
    truth = derive_ground_truth(model, dataset, spec, seed)
    write_raw(dataset, out_dir)
    gt.dump_ground_truth(truth, ground_truth_path)
    return GenerationSummary(
        seed=seed,
        raw_dir=out_dir,
        ground_truth_path=ground_truth_path,
        lines_per_variant=dict(Counter(row.variant_id for row in dataset.bom)),
        notes=len(dataset.notes),
        components=len(truth.components),
        defects=dict(sorted(Counter(defect.defect_type for defect in truth.defects).items())),
    )
