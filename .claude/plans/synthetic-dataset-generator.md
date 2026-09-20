# Feature: Synthetic dataset generator, planted defects and ground truth (#2)

The following plan should be complete, but it is important that you validate documentation and
codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types and models. Import from the right files.
In particular: the contract is read through `bomreuse.spec.load_spec()` and nothing else, and
`generate.py` imports **no pipeline module at all**.

## Feature Description

`bomreuse generate` produces, from a fixed seed, the synthetic dataset the whole build is measured
on: three raw CSV files (the pipeline's only input) and one ground-truth JSON file (read by the
evaluation only, from #5 on). The generator invents **true components** (`TRUE-0042`) first, then
emits the dirty raw reference strings that stand for them — so the ground truth owns identity and
knows nothing about the resolution rules that #4 will be scored on.

## User Story

As the lead data engineer reviewing this prototype (Thomas Lindqvist)
I want a reproducible dataset whose planted defects and expected answers are recorded apart from
the inputs, by code that shares nothing with the pipeline it will score
So that every precision / recall figure `evaluate` prints later is a measurement and not an
artefact of how the data was made.

## Problem Statement

Nothing can be built or measured until data exists, and the data must be able to *show* the
problem (DECISIONS.md 14): hidden reuse an exact-reference search misses, near-reuse, genuinely new
sub-assemblies, unsafe reuse, and dirt (typos, units, decimal commas, supplier / cost conflicts,
contradicting notes). The easy way to build it — derive the ground truth with the pipeline's own
key function or verdict rule — makes every later score circular (docs/ARCHITECTURE.md A3).

## Solution Statement

A two-layer generator. **Layer 1 (the story, seed-independent):** a hand-written catalogue plus the
story cases of `data/dataset_spec.toml` define a *true model* — variants, sub-assemblies, true
components, true quantities in base units, true suppliers and costs, notes and the facts they
state. Labels (reused / reusable / new, acceptable ancestors, diffs) are **declared** there.
**Layer 2 (the dirt, seeded):** pure rendering operators turn the true model into raw CSV strings —
typo'd references, mixed units, decimal commas, spelling noise. The ground truth is then derived
mechanically from the true model and the strings actually emitted, validated by a pydantic schema,
and written to the path given on the command line. A bridge *test* (not the generator) checks the
declared labels against `signatures.compare`, the same way spike S1 checked the spec.

**The seed moves the dirt, never the story** (DECISIONS.md 17): any seed yields the same backtest
labels and the same planted cases.

## Out of Scope / Non-Goals

- Not included: `ingest.py`, `normalize.py`, `model.py`, and the two ground-truth isolation tests
  (runtime copy + AST "no module mentions the ground truth") — those are #3.
- Not included: `resolve.py`'s key function, in any form. `generate.py` must not import it **and
  must not reimplement it** (no "canonical key" helper, no collision check based on folding).
- Not included: `bomreuse evaluate`, scoring, the naive baseline (#5). The ground truth only has to
  carry what they will need.
- Not included: LLM anything. Notes are rendered from templates; no model is called.
- Not changing: `data/dataset_spec.toml`, `src/bomreuse/spec.py`, `src/bomreuse/signatures.py`.
  If a story case appears impossible to honour, **stop and report** — do not edit the contract.
- Not changing: `DECISIONS.md`. Agents never write there. DECISIONS.md 19 is the line that covers
  pydantic; if the human wants a dated "pydantic landed" line, they write it.
- Not included: randomized planted cases, a second seed split, threshold tuning (DECISIONS.md 17).
- Not included: a component master file in `data/raw/` (it would hand the deduplication to the
  tool), a `language` column on notes, nested sub-assemblies ([A1]).

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High (little algorithmic risk; large hand-authored catalogue, and several
honesty invariants that are easy to break silently)
**Primary Systems Affected**: `src/bomreuse/` (4 new modules + CLI), `data/raw/`,
`data/ground_truth/`, `pyproject.toml`, `uv.lock`, `CLAUDE.md`, `README.md`, `.claude/STATUS.md`
**Dependencies**: `pydantic>=2.13,<3` (first runtime dependency; DECISIONS.md 19). Everything else
is standard library: `csv`, `json`, `random`, `argparse`, `decimal`, `dataclasses`.

## Related Work

**Implements**: https://github.com/BluegReeno/alstom-bom-reuse/issues/2   ·   **Epic**:
`docs/ARCHITECTURE.md` (A1, A2, A3, A4, A5, A8 inherited as decided), `docs/PRD.md` (R1, R2, R12)

**Back-references** (plans / work this builds on):

- Issue #1 (no plan file was kept): `data/dataset_spec.toml`, `src/bomreuse/spec.py`,
  `src/bomreuse/signatures.py`, `tests/test_verdict_story_cases.py` — the contract and the verdict
  rule this generator must reproduce and must not re-decide.
- DECISIONS.md 14, 15, 17, 19, 23.

**Forward-references** (append as follow-ups get created):

- #3 — consumes `data/raw/*.csv` (layout fixed here: `;` delimiter, UTF-8, the columns below). Its
  AST test "no module other than `evaluate.py` mentions the ground truth" **must exempt
  `generate.py`, `ground_truth.py` and `cli.py`**; the pipeline modules are the ones it guards.
- #5 — consumes `ground_truth.json`. It translates a finding's raw reference strings into
  `true_component_id` through the `components[].raw_references` mapping (guaranteed injective
  here), accepts **any** listed ancestor, and runs its end-to-end test on a test seed.
- #6 — scores note extraction against `notes[].facts`, written here so the generator is not
  reopened (which would break byte-identity of the committed data).

---

## CONTEXT REFERENCES

### Relevant Codebase Files — YOU MUST READ THESE BEFORE IMPLEMENTING

- `data/dataset_spec.toml` (whole file) — the 8 story cases with exact component counts, the 6 typo
  families (2 out of the rules' reach), the 3 must-not-merge pairs with reserved ids
  `TRUE-0101`..`TRUE-0106`, `min_subassembly_size = 4`, `default_unit = "pcs"`.
- `src/bomreuse/spec.py` (lines 30-137) — `DatasetSpec`, `StoryCase` (`left`/`right` are
  `Mapping[str, float]`, `units` overrides `default_unit`), `TypoFamily`, `MustNotMergePair`,
  `load_spec(path)`. Lines 17-19: the "default, not a hidden constant" idiom for a path. Lines
  26-27 and 113-120: the error-class idiom (`SpecError(ValueError)`, precise messages).
- `src/bomreuse/signatures.py` (lines 39-96, 142-188) — `Signature.from_counts`, `compare`, and the
  **diff direction convention**: `added` / `removed` are read left-to-right; in the ground truth,
  left = ancestor, right = the newest variant's sub-assembly. Used by the bridge *test* only.
- `tests/test_verdict_story_cases.py` (whole file) — the test style to mirror: module-level
  `SPEC = load_spec()`, parametrized by case id, sentence-like test names, assertion messages that
  say what to fix and cite the decision.
- `tests/test_spec.py` (lines 1-75) — `tmp_path` helper style, section comment banners.
- `docs/ARCHITECTURE.md` (lines 137-199) — A3 (identity owned by the generator, stable defect key),
  A4 (stdlib `csv`, why no pandas), A5 (ground-truth path is an argument, never a constant).
- `CONTEXT.md` (lines 17-85) — what is planted and the worked example A / B / C.
- `CLAUDE.md` — non-negotiable rules 1-8, module block (to update), commit rules, 30 s test budget.
- `pyproject.toml` — comments on lines 6-8 and 10-11 announce exactly the two edits made here.
- `.claude/skills/piv-validate/SKILL.md` — the validation the loop will run after implementation.

### New Files to Create

- `src/bomreuse/ground_truth.py` — pydantic v2 schema of the ground truth + `dump` / `load`.
- `src/bomreuse/dirt.py` — pure, seeded rendering operators: reference typos by kind, unit and
  decimal-comma rendering, supplier spelling noise.
- `src/bomreuse/catalogue.py` — the hand-written, seed-independent content: variants, component
  master, sub-assembly definitions per variant, note scripts. Data and tiny frozen dataclasses only.
- `src/bomreuse/generate.py` — builds the true model (catalogue + spec), applies the dirt, derives
  the ground truth, writes the files.
- `src/bomreuse/cli.py` — `argparse` entry point, `generate` subcommand.
- `tests/test_ground_truth_schema.py`, `tests/test_dirt.py`, `tests/test_catalogue.py`,
  `tests/test_generate.py`, `tests/test_generate_invariants.py`, `tests/test_cli_generate.py`.
- `data/raw/variants.csv`, `data/raw/bom.csv`, `data/raw/notes.csv`,
  `data/ground_truth/ground_truth.json` — generated with the default seed, committed.

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [pydantic — Models](https://docs.pydantic.dev/latest/concepts/models/) and
  [Configuration](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.extra)
  - `ConfigDict(extra="forbid", frozen=True)` — mirrors the strictness of `spec.py`.
- [pydantic — Model validators](https://docs.pydantic.dev/latest/concepts/validators/#model-validators)
  - `@model_validator(mode="after")` for the cross-field rules (injective mapping, label ↔ ancestors).
- [pydantic — Serialization](https://docs.pydantic.dev/latest/concepts/serialization/#python-mode)
  - Use `model_dump(mode="json")` then `json.dumps(..., sort_keys=True)`; `model_dump_json` has no
    `sort_keys`, and byte-identity wants an order we control.
- [csv.writer](https://docs.python.org/3.12/library/csv.html#csv.writer) and
  [Dialect.lineterminator](https://docs.python.org/3.12/library/csv.html#csv.Dialect.lineterminator)
  - The default terminator is `\r\n`; open with `newline=""` and set `lineterminator="\n"`.
- [random — Notes on reproducibility](https://docs.python.org/3.12/library/random.html#notes-on-reproducibility)
  - Same seed + same Python minor → same sequence. `uv.lock` / `requires-python` pin 3.12.
- [PYTHONHASHSEED](https://docs.python.org/3.12/using/cmdline.html#envvar-PYTHONHASHSEED)
  - Why iterating a `set[str]` is the classic way to lose byte-identity between two processes.
- [argparse — Sub-commands](https://docs.python.org/3.12/library/argparse.html#sub-commands)
- [pyproject — Creating executable scripts](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#creating-executable-scripts)

### Patterns to Follow

**Module docstring states the *why* and cites the decision** (`spec.py:1-9`, `signatures.py:1-15`).
Every new module opens the same way; `generate.py`'s must state the A3 rule in its first paragraph.

**Frozen, slotted dataclasses for everything internal** (`spec.py:30`):

```python
@dataclass(frozen=True, slots=True)
class Thresholds:
    """The two numbers the reuse rule is made of, and nothing else."""
```

pydantic appears in `ground_truth.py` **only** (DECISIONS.md 19, ARCHITECTURE A8). `generate.py`
builds dataclasses, and converts to the pydantic models at the very end.

**Constants**: `#:` doc-comment + `Final[...]` (`spec.py:17-23`, `signatures.py:25-28`).

**Errors**: one exception class per module, subclassing `ValueError`, with messages that name the
offending item and the rule it broke (`spec.py:26-27`, `spec.py:246-250`). Here:
`GenerationError(ValueError)` in `generate.py`.

**Section banners inside modules and tests**: `# --- table parsers ------…` (`spec.py:140`).

**Tests**: sentence-like names (`test_the_rule_agrees_with_the_story`), docstring when the *why* is
not obvious, assertion messages that tell the reader what to fix. Type hints on tests too
(`-> None`). No network, no live model, whole suite under 30 s (currently 68 tests, 0.06 s).

**No logging framework yet** in the codebase; the CLI prints a short summary to stdout and errors
to stderr. Do not introduce `logging` configuration here.

---

## DESIGN — what the generator must produce

This section is the content contract of the plan. Where it fixes a number, it was checked against
the A1 rule (`budget = min(3, ceil(0.25 * min(len)))`).

### D1 — Raw files (the pipeline's only input)

All three: UTF-8, no BOM, delimiter `;` (a French ERP export, and it lets a decimal comma live
unquoted), `quoting=csv.QUOTE_MINIMAL`, `lineterminator="\n"`, header row, every value a string.

| File | Columns |
| --- | --- |
| `variants.csv` | `variant_id`; `name`; `design_date` (ISO); `region`; `seats`; `bike_spaces`; `traction` |
| `bom.csv` | `line_id`; `variant_id`; `sub_assembly_ref`; `sub_assembly_designation`; `component_ref`; `designation`; `quantity`; `unit`; `supplier`; `unit_cost_eur` |
| `notes.csv` | `note_id`; `variant_id`; `date` (ISO); `text` |

- `line_id` (`L00001`…, in emission order) exists so every later finding can cite its source rows.
- Nothing in `data/raw/` may contain the substring `TRUE-`, a label, a language tag or a defect tag.
- Supplier and cost sit on the BOM line: that is what makes cross-variant conflicts possible.

### D2 — Variants (5)

| id | name | design_date | region | seats | bike_spaces | traction |
| --- | --- | --- | --- | --- | --- | --- |
| A | Standard intermediate car | 2019-03-14 | Hauts-de-France | 48 | 0 | electric |
| B | Bike / multi-purpose car | 2021-06-02 | Hauts-de-France | 36 | 8 | electric |
| D | Bi-mode intermediate car | 2022-09-20 | Normandie | 48 | 0 | bi-mode |
| E | Standard car, other region | 2023-11-08 | Grand Est | 44 | 0 | electric |
| C | Bike car, new region (**newest — the backtest target**) | 2025-02-17 | Occitanie | 32 | 6 | electric |

`seats` = 2 × `SEAT-FIX-DBL`; `bike_spaces` = `BIKE-HOOK`. "Newest" is decided by `design_date`,
never by the letter. All names (suppliers included) are **fictional**.

### D3 — Sub-assemblies (15 names; A, D, E carry 14 — no bike module)

Story cases come from the spec **verbatim** (true content = the spec's counts and units). "same as"
means the very same content object, so identity is by construction, not by a threshold.

| Sub-assembly | A | B | D | E | C (label → planted_as) |
| --- | --- | --- | --- | --- | --- |
| Carbody shell | story L | story R (= A) | same as A | same as A | same content, **same SA ref** → `reused` / `open_reuse` |
| HVAC unit | own | same | same | same | same content, same SA ref → `reused` / `open_reuse` |
| Braking unit | own | same | same | same | same, same ref → `reused` / `open_reuse` |
| Gangway and couplers | own | same | same | same | same, same ref → `reused` / `open_reuse` |
| Trailer bogie | story L | same as A | same as A | same as A | story R (= A), **new SA ref** → `reused` / `hidden_reuse` |
| Traction package | story L | same as A | story R (bi-mode) | same as A | same as A, new SA ref → `reused` / `hidden_reuse` |
| Auxiliary converter | own | same | same | same | same, **typo'd SA ref** → `reused` / `hidden_reuse` (+ unsafe, see D6) |
| Interior lighting | own | same | same | same (but carries the planted unit conflict, D5) | same as A, new SA ref, component refs typo'd within reach → `reused` / `hidden_reuse` |
| Floor and wall panels | own | same | same | same | same as A, new SA ref, **holds the one out-of-reach typo allowed in C** (`SEAT-FIX-KIT-447`) → truth stays `reused` / `hidden_reuse` |
| Bike module | — | story L | — | — | story R → `reusable` (ancestor B) / `near_reuse` |
| Passenger door set | story L | same as A | same as A | same as A | story R → `reusable` / `near_reuse` |
| Passenger information system | story L | story R | same as A | same as A | B's content + `PIS-SIGN-REGION` = 2 → `reusable` (vs B: 1 part; vs A: 2 parts + 1 qty, budget 2) / `near_reuse` |
| Seating module | story L | story R | same as A | own (`SEAT-FIX-DBL` 22, `SEAT-FIX-KIT` 22) | B's content with `SEAT-FIX-DBL` 16, `SEAT-FIX-KIT` 16, **B's SA ref kept** → `reusable` / `ref_reused_content_changed` (the baseline's false positive) |
| Floor and wall anchorage | story L | own: `ANCH-SEAT-RAIL` 10, `ANCH-RAIL-BOLT` 80, `ANCH-FLOOR-PLATE` 10, `ANCH-SHIM` 20, `ANCH-HOOK-POINT` 8 | same as A | same as A | story R → `new` (specific vs A **and** vs B: 7 parts differ) |
| Toilet module | own | same | same | same | entirely new components (PRM universal toilet) → `new` |

C therefore holds: 4 open reuse, 5 hidden reuse, 3 near-reuse, 1 reference-reused-content-changed,
2 new = 15. The 4 open-reuse items are what keeps the naive baseline above zero; the seating module
is what gives it a false positive.

Non-story sub-assemblies: 8–12 components each, never fewer than `min_subassembly_size`. Expected
volume: ~135–150 lines per variant, ~700 in total (inside 100–250 and 500–1,500).

Sub-assembly references: `SA-` + 4 digits for the older variants (shared when content is shared, a
new one when content differs, e.g. B's seating). C's new references use a visibly different scheme
(e.g. `OCC-SA-0312`); its one typo'd reference is a within-reach deformation of A's.

### D4 — True components and raw references

- Every component of the catalogue and of the spec's story cases gets a `TRUE-dddd` id, assigned
  sequentially **in catalogue order** starting at `TRUE-0001`, **skipping `TRUE-0101`..`TRUE-0106`**
  which the spec reserves for the must-not-merge pairs.
- A story-case key (`BIKE-HOOK`) is the clean reference of its true component.
- The typo families' canonicals are extra true components living in **non-story** sub-assemblies:
  `BGI-2031` is a generic part used in ≥ 3 non-story sub-assemblies (≥ 12 lines across the variants,
  because 10 distinct spellings must be placed); `HVAC-GRILLE-12` in the HVAC unit;
  `SEAT-FIX-KIT-4471` in Floor and wall panels.
- **Every string of every family is emitted at least once — placement is forced, not left to
  chance.** The seed picks *which* eligible line gets which spelling.
- Out-of-reach placement: `BGI-2013` on an **older** variant, in a non-story sub-assembly;
  `SEAT-FIX-KIT-447` on C's Floor and wall panels. No other out-of-reach spelling anywhere.
- The must-not-merge pairs are emitted with their literal references and reserved ids; the two
  members of a pair go in **different sub-assemblies** (a false merge by #4 then costs precision
  without also crashing `Signature`'s duplicate-component check), present in ≥ 2 variants.
  No typo operator is ever applied to a must-not-merge reference.
- Beyond the spec's literal strings, ~10–14 further true components receive **generated**
  within-reach spellings (kinds `case_and_whitespace`, `separator`, `homoglyph` — the kinds the spec
  declares as within reach), on seeded eligible lines. Within-reach spellings may appear anywhere,
  C and story sub-assemblies included: they change strings, never true content.
- **Injectivity**: one raw string never stands for two true components. The ground-truth validator
  enforces it and generation fails loudly on a collision.

### D5 — Dirt that is noise, and defects that are recorded

Noise (normalizable, **not** a defect record): `mm`/`m`, `g`/`kg`, `pcs`/`units`/`u`, decimal
commas on quantities and costs (`1,5`, `12,50`), case / trailing-space noise on supplier names and
designations. Base units of the true model: `pcs`, `m`, `kg`. A few non-story components are
measured in `m` (cables, trunking) and `kg` (adhesive, sealant) so the noise has somewhere to live.

Defect records, all keyed `(defect_type, true_component_id, variant_pair)` with `variant_pair` a
**sorted** 2-tuple (it may repeat a variant), derived **mechanically** from the true model and the
emitted strings:

| `defect_type` | A record exists for `(X, Y)` when… | Planting rule |
| --- | --- | --- |
| `duplicate_reference` | a line in X and a line in Y (two lines of one variant when X = Y) spell the same true component differently | follows from D4 |
| `unit_conflict` | the same true component is carried in **incompatible dimensions** in X and Y (e.g. `45 m` vs `2 pcs` of cable) | 2–3 planted; **never in C, never in a story sub-assembly** |
| `supplier_conflict` | the true supplier differs between X and Y | 4–6 components; anywhere, C included |
| `cost_conflict` | the true unit cost differs between X and Y | 4–6 components; **outside these, a component's cost is strictly identical everywhere**; planted gaps are blunt (≥ +15 %) — the spec holds no cost tolerance and the generator must not invent one |
| `note_contradiction` | a note filed on X states a fact the BOM of Y violates | see D6 |

Within one variant a true component has one true supplier and one true cost.

### D6 — Notes (~40, FR / EN / mixed)

Rendered from scripts in the catalogue (fixed story) with seeded template wording. Mix: ~12
replacement, ~8 obsolescence, ~8 restriction, **~12 carrying no fact at all** (negatives). Roughly
45 % French, 35 % English, 20 % switching language inside the note. Patterns of CONTEXT.md must
appear literally somewhere: `remplacé par`, `obsolete since`, `do not use on`, `ne pas utiliser sur`.

- A note cites parts by **raw reference string**, sometimes a dirty spelling — those strings count
  in the `raw_references` mapping too.
- About half of the fact-bearing notes are **respected** by the BOM (no defect record): precision
  needs those negatives.
- A `note_contradiction` exists when: *obsolescence / replacement* effective on date `d` and a
  variant with `design_date > d` still carries the part; or a *restriction* ("do not use on bike
  car", "ne pas monter sur bi-mode") and a variant in that scope carries the part.
  `variant_pair = sorted((note.variant_id, offending_variant))`.
- **Unsafe reuse (2 planted):** one in C's Auxiliary converter (`reused`, hidden) and one in C's
  Bike module (`reusable`): a part of the matched ancestor — hence of C — is declared obsolete or
  replaced by a note dated before C's design date. Recorded twice: as a `note_contradiction` defect,
  and as an `unsafe` entry on the backtest label.

### D7 — Ground-truth file (one JSON, written where the CLI says)

```
GroundTruth
  schema_version: "1"          spec_version: str          seed: int
  newest_variant: str
  components:      [TrueComponent { true_component_id, designation, base_unit, raw_references: [str] }]
  typo_families:   [PlantedFamily { family_id, true_component_id, within_rules_reach, emitted: [str] }]
  must_not_merge:  [MustNotMerge  { id, left_reference, right_reference,
                                    left_true_component, right_true_component }]
  backtest:        [BacktestLabel { variant_id, sub_assembly_ref, sub_assembly_designation,
                                    label: "reused" | "reusable" | "new",
                                    planted_as: "open_reuse" | "hidden_reuse" | "near_reuse"
                                              | "ref_reused_content_changed" | "new",
                                    story_case_id: str | None,
                                    ancestors: [Ancestor { variant_id, sub_assembly_ref, diff: Diff | None }],
                                    unsafe:    [UnsafePart { true_component_id, note_id }] }]
  defects:         [DefectRecord  { defect_type, true_component_id, variant_pair: (str, str),
                                    evidence_line_ids: [str], note_id: str | None }]
  notes:           [NoteTruth     { note_id, language: "fr" | "en" | "mixed",
                                    facts: [NoteFact { fact_type: "replacement" | "obsolescence" | "restriction",
                                                       true_component_id, cited_reference,
                                                       replaced_by_true_component_id: str | None,
                                                       effective_date: str | None, scope: str | None }] }]
Diff { added: [DiffItem], removed: [DiffItem], quantity_changed: [QuantityChange] }
DiffItem { true_component_id, quantity: float, unit }      QuantityChange { true_component_id, left: float, right: float, unit }
```

- `sub_assembly_ref` values are the **raw strings as emitted** — an ancestor id must contain nothing
  the pipeline produces (A3).
- Label rule: the label is the **best** class any older sub-assembly reaches; `ancestors` lists
  **every** older `(variant, sub_assembly_ref)` reaching that class (identical content for `reused`;
  the hand-declared list for `reusable`, each with its own diff, left = ancestor). `new` ⇒ empty.
- Validators (`mode="after"`): ids match `^TRUE-\d{4}$`; `raw_references` injective across
  components; `ancestors` empty iff `label == "new"`; `diff` present iff `label == "reusable"`;
  `variant_pair` sorted; defect keys unique; every referenced id / note id exists; every
  must-not-merge id is a declared component whose `raw_references` contains its reference.
- Serialization: every list sorted by a stable key before model construction;
  `json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False) + "\n"`.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — dependency and the ground-truth schema

pydantic lands, and the schema of D7 is written and tested on hand-built instances, before any
generator exists to feed it.

### Phase 2: The dirt operators

**Independent of:** Phase 1 (pure string functions; could run in parallel).

Pure functions `(value, rng) -> str`, unit-tested in isolation.

### Phase 3: The catalogue and the true model

**Depends on:** nothing but `spec.py`. The bulk of the authoring. Tested for coverage of the spec
and for D3's structure before any dirt is applied.

### Phase 4: The generator

**Depends on:** Phases 1–3. True model → dirty rows → derived ground truth → files.

### Phase 5: CLI, generated data, invariants

**Depends on:** Phase 4. `bomreuse generate`, the committed dataset, and the invariant tests
(byte-identity across processes, freshness, no leaked id, import isolation, the bridge test).

### Phase 6: Paperwork

`CLAUDE.md` module block, `README.md` "How to run", `CONTEXT.md` status, `.claude/STATUS.md`.

---

## STEP-BY-STEP TASKS

Execute in order. Each task ends with a commit referencing `#2`; tests ride in the same commit as
the code they test (CLAUDE.md). Never touch another issue's scope in these commits.

### 1. UPDATE `pyproject.toml` + `uv.lock` — pydantic

- **IMPLEMENT**: `uv add "pydantic>=2.13,<3"`. Replace the comment on lines 6-8 by one line saying
  pydantic guards the two untrusted boundaries only (DECISIONS.md 19). Leave `[project.scripts]`
  for task 6.
- **GOTCHA**: needs the network once; everything after runs offline. Do **not** write in
  `DECISIONS.md` — decision 19 already covers this dependency; say so in the commit body.
- **VALIDATE**: `uv run python -c "import pydantic; print(pydantic.VERSION)"` and `uv run pytest`
- **SATISFIES**: DoD "no new dependency without a line in DECISIONS.md"
- **COMMIT**: `chore: pydantic, scoped to the ground-truth schema (#2)`

### 2. CREATE `src/bomreuse/ground_truth.py` + `tests/test_ground_truth_schema.py`

- **IMPLEMENT**: the models of D7, all `ConfigDict(extra="forbid", frozen=True)`; `Literal[...]`
  for the enumerations; the `model_validator(mode="after")` rules listed in D7;
  `dump_ground_truth(truth: GroundTruth, path: Path) -> None` (creates parent dirs, writes the
  sorted JSON + trailing newline, `encoding="utf-8"`, `newline="\n"`);
  `load_ground_truth(path: Path) -> GroundTruth` via `model_validate_json`.
- **PATTERN**: strictness and error wording of `spec.py:237-264`; module docstring style of
  `spec.py:1-9`. State in the docstring that this is one of the two pydantic boundaries.
- **IMPORTS**: `pydantic.BaseModel, ConfigDict, Field, model_validator`; stdlib `json`, `pathlib`.
  **No `bomreuse` import at all** — the schema depends on nothing.
- **GOTCHA**: no default path constant in this module, nor anywhere in `src/` (A5). `variant_pair`
  as `tuple[str, str]` round-trips through JSON as a list — pydantic coerces it back; assert it.
- **TESTS**: a minimal valid instance round-trips dump → load → equal, and dumps byte-identically
  twice; each validator rejects its violation with a message naming the offender (parametrized):
  duplicated raw string across two components, `new` with an ancestor, `reusable` without diff,
  `reused` with a diff, unsorted `variant_pair`, duplicate defect key, unknown id in a defect, bad
  id format, unknown extra key.
- **VALIDATE**: `uv run pytest tests/test_ground_truth_schema.py`
- **SATISFIES**: "Ground-truth schema" section; AC "must-not-merge … declared as such"
- **COMMIT**: `feat: ground-truth schema — identity, labels, defects, note facts (#2)`

### 3. CREATE `src/bomreuse/dirt.py` + `tests/test_dirt.py`

- **IMPLEMENT**: pure functions taking a `random.Random`:
  `typo(reference, kind, rng) -> str` for kinds `case_and_whitespace`, `separator`, `homoglyph`
  (raises `ValueError` on any other kind — out-of-reach spellings are spec literals, never
  generated); `render_quantity(value, base_unit, rng) -> tuple[str, str]` (unit spelling among
  `pcs`/`units`/`u`, `m`↔`mm`, `kg`↔`g`, optional decimal comma); `render_cost(value, rng) -> str`;
  `spelling_noise(text, rng) -> str` (case / trailing space only).
- **GOTCHA**: numbers are rendered with `decimal.Decimal` / explicit format strings, never `repr`
  of a float: `36.0 m` → `36`, `36,0`, `36000` + `mm`. A rendered quantity must convert back to
  exactly the true value (test it with `Decimal`). `typo()` must return a string **different** from
  its input, or raise — a no-op typo would silently un-plant a defect (e.g. `homoglyph` on a
  reference with no `O/0/I/1/l`: the caller filters eligibility via a
  `can_apply(reference, kind) -> bool` helper).
- **GOTCHA**: this is *defect planting*, not resolution. No function here computes a canonical key
  or compares two references. Keep it that way.
- **VALIDATE**: `uv run pytest tests/test_dirt.py`
- **SATISFIES**: AC "every planted defect category … present" (units, decimal commas, typos)
- **COMMIT**: `feat: dirt operators — typos by kind, units, decimal commas (#2)`

### 4. CREATE `src/bomreuse/catalogue.py` + `tests/test_catalogue.py`

- **IMPLEMENT**: frozen dataclasses `VariantDef`, `ComponentDef` (clean reference, designation,
  base_unit, true supplier, true unit cost), `SubAssemblyDef` with a content source that is one of:
  `FromStory(case_id, side)`, `Own(counts)`, `SameAs(variant_id, name)`,
  `Derived(variant_id, name, set_quantities, add, remove)`; per-variant overrides for planted
  supplier / cost / unit conflicts; C's label declarations (`label`, `planted_as`, hand-declared
  reusable ancestors); `NoteScript` (variant, date, fact or none, language, cited spelling choice).
  Content exactly per D2, D3, D5, D6.
- **GOTCHA**: do **not** copy the spec's story counts into this file — reference them by case id
  and side. Two copies of a count is how the generator stops reproducing the contract.
- **GOTCHA**: every component key of every story case needs a `ComponentDef` (≈ 75), plus ≈ 70
  non-story components. Fictional supplier names only.
- **GOTCHA**: the C anchorage must be `specific` against **B's** anchorage too, not only A's; D3's
  B content was checked (7 parts differ, budget 2). The bridge test of task 7 guards it.
- **TESTS**: every story-case component key has a `ComponentDef`; every story case is referenced by
  the catalogue on both sides at the variants the spec names; A/D/E have 14 sub-assemblies, B and C
  15; every resolved sub-assembly has ≥ `spec.dataset.min_subassembly_size` components; C's
  declarations match D3's counts (4 / 5 / 3 / 1 / 2); typo-family canonicals and must-not-merge
  references live in non-story sub-assemblies, pair members in different ones.
- **VALIDATE**: `uv run pytest tests/test_catalogue.py`
- **SATISFIES**: AC "no sub-assembly below the minimum size"; scope "4–6 variants … A, B, C"
- **COMMIT**: `feat: catalogue — five variants, fifteen sub-assemblies, the note scripts (#2)`

### 5. CREATE `src/bomreuse/generate.py` + `tests/test_generate.py`

- **IMPLEMENT**:
  - `DEFAULT_SEED: Final[int]` (pick once, e.g. `20260920`; doc-comment: "a default, not a hidden
    constant — the CLI takes `--seed`").
  - `build_true_model(spec) -> TrueModel` — resolves the catalogue against the spec: true ids (D4
    numbering, reserved ids skipped), true lines `(variant, sub_assembly, true_component, quantity,
    base_unit, supplier, cost)`, notes. Seed-independent.
  - `render(model, spec, seed) -> Dataset` — applies the dirt: forced placement of every family
    string and of the two out-of-reach spellings (D4), generated within-reach typos, unit /
    decimal / spelling noise; assigns `line_id`s in emission order (variant by design date, then
    catalogue order). `Dataset` carries raw rows **and**, per row, the true ids (in memory only).
  - `derive_ground_truth(model, dataset, spec, seed) -> GroundTruth` — mapping, families, pairs,
    backtest labels (raw `sub_assembly_ref`s as emitted, `reused` ancestors by shared content
    object, `reusable` ancestors + diffs from the declarations), defects per D5, notes per D6.
  - `write_raw(dataset, out_dir)` — the three CSVs of D1; `generate(spec, seed, out_dir,
    ground_truth_path)` — orchestrates and returns a small summary dataclass.
  - `GenerationError(ValueError)` for every broken invariant (collision, unplaceable spelling,
    sub-assembly below the minimum, a family string not emitted).
- **IMPORTS**: `bomreuse.spec`, `bomreuse.catalogue`, `bomreuse.dirt`, `bomreuse.ground_truth`.
  **Nothing else from `bomreuse`** — not `signatures`, and `resolve` / `normalize` never.
- **GOTCHA — determinism**: one `random.Random(f"{seed}:{concern}")` per concern (`typos`,
  `units`, `costs`, `notes`…) so touching one does not reshuffle the others (string seeds are
  hashed with SHA-512, independent of `PYTHONHASHSEED` — verified). Never the module-level
  `random`. **Never iterate a `set`**: sort first. No `datetime.now()`, no absolute path, no
  username in any output.
- **GOTCHA — the diff is computed on true ids by plain dict comparison of the two declared
  contents.** That is bookkeeping (what was added / removed / changed), not the verdict rule: it
  applies no budget and decides no class. The class comes from the declaration; the bridge test
  confronts it with `signatures.compare`.
- **GOTCHA**: the diff direction is ancestor → newest (`signatures.py:107-117`).
- **TESTS** (`tests/test_generate.py`, on an in-memory build, default seed unless said):
  - the true content of each `(variant, sub_assembly)` named by a story case equals the spec's
    counts and units exactly (parametrized by case id and side);
  - every string of every typo family is emitted, out-of-reach ones included; `BGI-2013` only on an
    older variant, `SEAT-FIX-KIT-447` only in C's panels, no other out-of-reach spelling;
  - both references of every must-not-merge pair are emitted, mapped to their reserved ids;
  - each defect category of D5 has ≥ 1 record; unit conflicts touch neither C nor a story
    sub-assembly; outside planted cost conflicts every true cost is constant;
  - mixed units, decimal commas and the `pcs` / `units` / `u` spellings all occur in `bom.csv`;
  - 100–250 lines per variant, 500–1,500 in total, 35–45 notes, all three languages present, ≥ 8
    notes with no fact;
  - ≥ 1 unsafe reuse, present both as a defect and on its backtest label;
  - **two different seeds give different `bom.csv` bytes and the same backtest section** (labels,
    `planted_as`, ancestors, diffs all equal) — the seed moves the dirt, never the story.
- **VALIDATE**: `uv run pytest tests/test_generate.py`
- **SATISFIES**: AC 2, 3, 4, 5; scope "honours … the planted-case component counts"
- **COMMIT**: `feat: generator — true model first, dirt second, ground truth derived (#2)`

### 6. CREATE `src/bomreuse/cli.py` + UPDATE `pyproject.toml` + `tests/test_cli_generate.py`

- **IMPLEMENT**: `main(argv: list[str] | None = None) -> int` with `argparse` sub-commands;
  `generate --out <dir> --ground-truth <path> [--seed N] [--spec <path>]`. `--out` and
  `--ground-truth` are **required, with no default**. `--seed` defaults to `DEFAULT_SEED`, `--spec`
  to `DEFAULT_SPEC_PATH`. Refuse (exit 2, message on stderr) when the ground-truth path resolves
  inside `--out`. Print a short summary (files, line counts, seed). Add
  `[project.scripts] bomreuse = "bomreuse.cli:main"` and drop the comment on lines 10-11 of
  `pyproject.toml`; then `uv sync`.
- **GOTCHA (A5)**: no string like `data/ground_truth` anywhere in `src/`. The CLI is where later
  sub-commands land (#3 `normalize`, #4 `run`, #5 `evaluate`): build the sub-parser so adding one
  is three lines, and keep `generate`'s handler a separate function.
- **TESTS**: `main([...])` into `tmp_path` writes exactly the three CSVs in `--out` and the JSON at
  the given path, returns 0, and the JSON loads through `load_ground_truth`; missing
  `--ground-truth` exits with `SystemExit(2)`; ground truth inside `--out` is refused.
- **VALIDATE**: `uv run pytest tests/test_cli_generate.py && uv run bomreuse generate --help`
- **SATISFIES**: AC 8; "CLI, and A5 made structural"
- **COMMIT**: `feat: bomreuse generate — both paths given on the command line (#2)`

### 7. CREATE `tests/test_generate_invariants.py`

- **IMPLEMENT**:
  - **byte-identity, in process**: generate twice into two `tmp_path` dirs, compare every file's
    bytes;
  - **byte-identity, across processes**: run `sys.executable -m bomreuse.cli generate …` twice
    with `PYTHONHASHSEED=1` and `=2` in the environment, compare bytes (this is the test that
    catches set iteration; two subprocesses, well inside the 30 s budget). Add
    `if __name__ == "__main__": raise SystemExit(main())` to `cli.py` if not already there;
  - **no leaked identity**: no file under the generated raw dir contains `TRUE-`, and the raw
    headers are exactly D1's;
  - **import isolation (AST)**: parse `generate.py`, `catalogue.py`, `dirt.py`, `ground_truth.py`;
    the `bomreuse.*` modules they import are a subset of `{spec, catalogue, dirt, ground_truth}`;
    assert explicitly that `resolve`, `normalize` and `signatures` are absent, with a message citing
    ARCHITECTURE A3. (`resolve.py` does not exist yet; the test is on the import statement.);
  - **the bridge** (imports `bomreuse.signatures` — allowed in a test, that is its whole point): for
    every sub-assembly of the newest variant, build `Signature.from_counts` over **true ids** for it
    and for every sub-assembly of every older variant, run `compare` with `spec.thresholds`; the
    best verdict maps to the declared label (`identical`→`reused`, `reusable`→`reusable`,
    `specific`→`new`); the set of `(variant, sub_assembly_ref)` reaching it equals the ground
    truth's `ancestors`; for `reusable`, each ancestor's diff equals `compare(...).diff` item for
    item. The failure message says: fix the catalogue, never the thresholds (DECISIONS.md 17).
- **VALIDATE**: `uv run pytest tests/test_generate_invariants.py`
- **SATISFIES**: AC 1, 6, 7
- **COMMIT**: `test: generator invariants — byte-identity, isolation, labels vs the verdict rule (#2)`

### 8. CREATE `data/raw/*.csv` + `data/ground_truth/ground_truth.json`, ADD the freshness test

- **IMPLEMENT**: `uv run bomreuse generate --out data/raw --ground-truth
  data/ground_truth/ground_truth.json` with the default seed. Add to
  `tests/test_generate_invariants.py`: regenerating with `DEFAULT_SEED` into `tmp_path` yields
  bytes equal to the committed files; `data/raw/` contains exactly the three CSVs;
  `data/ground_truth/` exactly the one JSON.
- **GOTCHA**: the ground-truth path appears in `tests/` and in `README.md` — that is fine; A5 is
  about `src/`. Read the generated `bom.csv` and `notes.csv` with your own eyes before committing:
  ten minutes of reading is the only check that the data *looks* like a client export.
- **VALIDATE**: `uv run pytest`, then `grep -rl "TRUE-" data/raw` (expect no output), then
  `grep -rn "data/ground_truth" src/` (expect no output — A5: the path is never a constant in `src/`)
- **SATISFIES**: AC 7; "Files"
- **COMMIT**: `feat: the generated dataset and its ground truth, default seed (#2)`

### 9. UPDATE `CLAUDE.md`, `README.md`, `CONTEXT.md`, `.claude/STATUS.md`

- **IMPLEMENT**: `CLAUDE.md` module block — add `catalogue.py`, `dirt.py`, `ground_truth.py`, one
  line each, and adjust `generate.py`'s line; `README.md` "How to run" — the `generate` command
  (leave the rest "to be written"); state in the data section that there are 5 variants and that
  the delimiter is `;`; `CONTEXT.md` Status — one dated line; `.claude/STATUS.md` — four-section
  format, #2 to Done, focus → #3, keep Current Focus to 1–2 lines.
- **GOTCHA**: no number in the README that the code did not compute (rule 1): line and note counts
  come from the generated files, quote them exactly or not at all.
- **VALIDATE**: run the `piv-validate` skill; expect checks 1, 3 (determinism), 4 PASS, 2 N/A.
- **SATISFIES**: DoD "CLAUDE.md and README.md still true"
- **COMMIT**: `docs: module block, how to generate, STATUS — issue #2 done (#2)`

---

## TESTING STRATEGY

pytest, everything under `tests/`, offline, whole suite < 30 s. Build the dataset **once per test
module** (`@pytest.fixture(scope="module")`) — generation is cheap, but the parametrized tests are
many.

### Unit Tests

`test_ground_truth_schema.py` (validators, round-trip), `test_dirt.py` (each operator, round-trip
of rendered numbers, refusal of out-of-reach kinds), `test_catalogue.py` (coverage of the spec,
structure of D3).

### Integration Tests

`test_generate.py` (the planted content, in memory), `test_cli_generate.py` (the files, through
`main`), `test_generate_invariants.py` (byte-identity in and across processes, isolation, the
bridge, freshness of the committed data).

### Edge Cases

- A `homoglyph` typo asked on a reference with no foldable character → refused, not a no-op.
- A generated spelling colliding with another component's reference → `GenerationError`.
- A sequential true id reaching `TRUE-0101` → reserved range skipped.
- `36.0 m` rendered as `36000 mm` and `2.5 kg` as `2500 g` / `2,5 kg` convert back exactly.
- A note citing a dirty spelling: the string lands in `raw_references`.
- `variant_pair` with the same variant twice (`("B", "B")`) is valid and sorted.
- Ground-truth path inside `--out` → refused.
- A different seed → different bytes, same labels.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

No linter or type checker in this project, on purpose (`piv-validate`, last section). Type hints
everywhere all the same.

```bash
uv run python -m compileall -q src tests
```

### Level 2: Unit Tests

```bash
uv run pytest tests/test_ground_truth_schema.py tests/test_dirt.py tests/test_catalogue.py
```

### Level 3: Integration Tests

```bash
time uv run pytest
```

### Level 4: Manual Validation

```bash
uv run bomreuse generate --out /tmp/bomreuse-check/raw --ground-truth /tmp/bomreuse-check/gt/ground_truth.json
```

```bash
diff -r /tmp/bomreuse-check/raw data/raw && diff /tmp/bomreuse-check/gt/ground_truth.json data/ground_truth/ground_truth.json && echo IDENTICAL
```

```bash
grep -rl "TRUE-" data/raw || echo "no true id leaked"
```

```bash
uv run python -c "import csv,collections; r=list(csv.DictReader(open('data/raw/bom.csv',encoding='utf-8'),delimiter=';')); print(len(r), dict(collections.Counter(x['variant_id'] for x in r)))"
```

Then open `data/raw/bom.csv` and `data/raw/notes.csv` and read them.

### Level 5: Additional Validation

Run the project's `piv-validate` skill.

---

## ACCEPTANCE CRITERIA

From the issue, verbatim in meaning:

- [ ] AC1 — Same seed → byte-identical files, asserted by a test (in process **and** across two
      processes with different `PYTHONHASHSEED`).
- [ ] AC2 — Every planted defect category of `CONTEXT.md` is present in the data and recorded in
      the ground truth.
- [ ] AC3 — Every typo family of the spec is emitted, the out-of-reach ones included.
- [ ] AC4 — The must-not-merge pairs are emitted and declared as such in the ground truth.
- [ ] AC5 — No sub-assembly below the minimum size.
- [ ] AC6 — A test asserts `generate.py` does not import `resolve.py` (extended: no pipeline module,
      nor `signatures`).
- [ ] AC7 — `data/raw/` holds only inputs; `data/ground_truth/` only the ground truth; nothing in
      `data/raw/` reveals a true component id.
- [ ] AC8 — `bomreuse generate` runs offline and writes both, to the paths given on the command line.

Added by this plan (agreed at the clarification gate):

- [ ] The true content of every story-case sub-assembly equals the spec's counts.
- [ ] The declared labels, ancestors and diffs agree with `signatures.compare` on true ids.
- [ ] The seed moves the dirt, never the story.
- [ ] Exactly one out-of-reach spelling in C, in a non-story `reused` sub-assembly.

Definition of done: `uv run pytest` green, < 30 s, offline · `evaluate` N/A until #5 · pydantic
covered by DECISIONS.md 19 · `CLAUDE.md` and `README.md` still true.

---

## COMPLETION CHECKLIST

- [ ] All 9 tasks completed in order, one commit each, every commit referencing `#2`
- [ ] Each task's validation passed before moving on
- [ ] Full suite green and timed under 30 s
- [ ] Committed data equals a fresh generation (freshness test)
- [ ] `bom.csv` and `notes.csv` read by a human eye
- [ ] `DECISIONS.md`, `dataset_spec.toml`, `spec.py`, `signatures.py` untouched
- [ ] `piv-validate` run, verdict quoted in the PR

---

## OPEN QUESTIONS / ASSUMPTIONS

Settled at the gate (2026-09-20, the human agreed to all six recommendations and to the defaults):
raw layout D1; C's mix and five variants; one out-of-reach spelling in C; all acceptable ancestors
listed as `(variant, raw sub-assembly ref)`; defect semantics D5; per-note facts and the `unsafe`
flag in the ground truth; catalogue in Python; `generate.py` does not import `signatures`; committed
data with a freshness test; DECISIONS.md 19 is the pydantic line.

Still assumed — confirm before or during execution:

- Confirmed by the human (2026-09-20, after the plan was drafted) — the CSV delimiter is `;`. It
  constrains #3.
- Assumed — two extra modules (`catalogue.py`, `dirt.py`) beyond the three the issue names; the
  issue's "Files" list is read as a minimum. `CLAUDE.md`'s module block is updated in task 9.
- Assumed — `DEFAULT_SEED = 20260920`. Any integer does; changing it later rewrites the committed
  data.
- Assumed — supplier names carry case / whitespace noise only. Supplier *name resolution* (true
  aliases) is nobody's issue and is not planted.
- To remind the human of: if they want a dated DECISIONS.md line for the day pydantic actually
  landed, or for the `;` delimiter, **they** write it; propose wording in the PR, do not commit it.

## NOTES (open canvas)

**Why labels are declared and not computed.** The generator could import `signatures.compare` and
label C mechanically. The score would not be circular in the A3 sense (the rule is a contract, and
the pipeline's difficulty is recovering identity from dirt, not applying the rule) — but a bug in
`compare` would then be invisible: both sides would share it. Declaring the labels and confronting
them with `compare` in a test keeps two independent statements of the story, exactly like S1 did
for the spec. The diff bookkeeping in the generator applies no budget, so it is not a second copy
of the rule.

**Why the defect records are derived mechanically.** "Every pair of variants whose true value
differs" is a definition anyone can recompute from the true model; a hand-written defect list would
drift from the data at the first catalogue edit.

**Why the out-of-reach typo in C matters.** With `SEAT-FIX-KIT-447` in C's panels, rules-only
resolution sees one part removed and one added: the tool will answer `reusable` where the truth is
`reused`. That is one honest backtest miss caused by resolution, so the README's "Known limits" can
carry a backtest figure and not only a resolution-recall figure.

**Risk: the must-not-merge pairs and `Signature`.** If #4's rules merge a pair whose two members sat
in one sub-assembly, `Signature.__post_init__` would raise on the duplicate component. Placing the
members in different sub-assemblies keeps a false merge a *measured* precision loss instead of a
crash. #4 should still be told (forward reference).

**Risk: authoring volume.** ~145 component definitions and ~40 note scripts are the real cost of
this issue. The catalogue tests are there so that a missing or misplaced entry fails in seconds.

**Sequencing.** Phases 1 and 2 are independent and tiny; Phase 3 is the long one. If the work is
split across sessions, the natural cut is after task 4 (catalogue committed and tested).

## AMENDMENTS

- (none yet)
