# Feature: Ingest, normalize and the entity model (#3)

The following plan should be complete, but it is important that you validate documentation and
codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types and models. Import from the right files.
In particular: **no pipeline module imports `generate`, `catalogue`, `dirt` or `ground_truth`**, and
no module written here computes anything with a string distance.

## Feature Description

`bomreuse normalize` reads the three raw CSV files of `data/raw/` exactly as they are, turns them
into the project's single set of types — frozen dataclasses carrying the raw value and the
normalized value side by side — and writes `out/normalized.json`, which reads back into the same
objects. It is the first stage of the pipeline and the place where the non-negotiable invariants
(ground-truth isolation, read-only inputs) get their tests.

## User Story

As the lead data engineer reviewing this prototype (Thomas Lindqvist)
I want every raw value of my export kept byte-for-byte next to what the tool made of it
So that any later finding can be traced to the exact characters in my file, and I can check that
the tool never "cleaned" away the very defects it claims to detect.

## Problem Statement

The raw files are dirty on purpose (DECISIONS.md 24): `48200,00` next to `17650.00`, `pcs` / `u` /
`units`, `36000 mm` for `36 m`, trailing spaces, `BGI-2O3I` / `BGI_2031` / `bgi-2031` for one part.
A parser that coerces on read (pandas) destroys that evidence before anyone sees it
(docs/ARCHITECTURE.md A4). And nothing downstream (#4 resolution, #5 baselines) can be written
until rows exist as typed, traceable records.

## Solution Statement

Three small modules, standard library only.

- `model.py` — the types: raw rows, raw/normalized value pairs, the entities (`Variant`,
  `SubAssembly`, `Component`, `Supplier`, `BomLine`, `Note`), `NormalizationIssue`, the
  `NormalizedDataset` container, and its explicit JSON round-trip.
- `ingest.py` — `csv` with `delimiter=";"`, every value a `str`, nothing stripped, structure
  checked strictly (`IngestError`).
- `normalize.py` — pure functions: reference key, text key, number parsing, unit conversion, date
  and int parsing; then `normalize(raw) -> NormalizedDataset`. A value that cannot be read keeps its
  row, gets `normalized = None`, and is recorded as a `NormalizationIssue` — counted, never dropped.

## Out of Scope / Non-Goals

- Not included: grouping verdicts `auto / review / reject`, `match_reference`, splitting a key that
  covers two products — all #4. A `Component` here is a **candidate group** (one per reference key),
  not yet a canonical component.
- Not included: any note reading — no lexicon, no extraction, no language detection (#6). Notes are
  carried through untouched, date parsed.
- Not included: findings. A `NormalizationIssue` is a data-quality record of this stage, not a
  `Finding` with `rule_id` and confidence (that type arrives with #4's rule catalogue).
- Not included: `bomreuse run`, `evaluate`, the baselines (#5), `out/findings.json`, the report.
- Not included: a display label for a component (#4 / #7 decide how a canonical component is named).
- Not changing: `generate.py`, `catalogue.py`, `dirt.py`, `ground_truth.py`, `spec.py`,
  `signatures.py`, `data/**`. `bom.csv`, `notes.csv`, `variants.csv` and the ground truth stay
  byte-identical (the freshness test `tests/test_generate_invariants.py:211` guards it).
- Not changing: `DECISIONS.md` — agents never write there (see Open Questions for the line to propose).
- No new dependency. No pandas, no rapidfuzz, no `difflib`.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium (the code is small; the risk is in the contracts #4 and #5 inherit)
**Primary Systems Affected**: `src/bomreuse/{model,ingest,normalize,cli}.py`, `tests/`
**Dependencies**: standard library only (`csv`, `dataclasses`, `datetime`, `decimal`, `json`, `re`, `unicodedata`, `hashlib`, `ast`)

## Related Work

**Implements**: [#3](https://github.com/BluegReeno/alstom-bom-reuse/issues/3) · **Epic**: `docs/ARCHITECTURE.md` (A2, A4, A5, A8), `docs/PRD.md` (R3, R4, R12)

**Back-references**:

- `.claude/plans/synthetic-dataset-generator.md` — Why: fixes the raw layout this issue reads.
- `.claude/reports/synthetic-dataset-generator-report.md` — Why: handover (AST exemptions; must-not-merge members sit in different sub-assemblies).

**Forward-references**:

- #4 inherits `normalize.reference_key` (never recomputes a key), `Component` as candidate group, and must split the three must-not-merge keys with `reject`.
- #5's two baselines read `RawBomRow` (raw ingested rows), never `BomLine`.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `CLAUDE.md` — non-negotiable rules, module boundaries, test layers, commit rules.
- `docs/ARCHITECTURE.md` (A2 lines 105-137, A4 178-188, A5 190-201, A8 242-254) — inherited decisions.
- `DECISIONS.md` lines 24 and 26 — `;` delimiter, every value a string; signatures on every merged group.
- `src/bomreuse/generate.py` (lines 40-57) — file names and column tuples of the raw layout. **Do not import them** from a pipeline module; re-declare and let a test compare.
- `src/bomreuse/generate.py` (lines 680-686) — how the files are written (`newline=""`, `lineterminator="\n"`, `QUOTE_MINIMAL`): the reader mirrors it.
- `src/bomreuse/generate.py` (lines 689-699) — the path guard pattern (`resolve().is_relative_to`), refused before any write.
- `src/bomreuse/dirt.py` (lines 31-37, 96-141) — the exact dirt `normalize.py` must undo: count spellings, `mm`/`g` sub-units, decimal comma, `.0` padding. Read it to know the input; share no code with it.
- `src/bomreuse/spec.py` (lines 26-27, 275-338) — error class + strict small parsers with a `where` argument: the style to mirror.
- `src/bomreuse/signatures.py` (lines 39-46) — `SignatureItem(component, quantity: float, unit)`: why quantities are `float` and units `pcs` / `m` / `kg`.
- `src/bomreuse/ground_truth.py` (lines 330-342) — `render_* / dump_* / load_*` trio, `sort_keys=True, indent=2, ensure_ascii=False`, `newline="\n"`: mirror for `normalized.json`.
- `src/bomreuse/cli.py` (whole file) — sub-command registration, handler, exit codes 2 (usage) / 1 (data).
- `tests/test_generate_invariants.py` (lines 100-108) — `bomreuse_imports()` AST helper to reuse by import in the new invariant test; (lines 52-64) cross-process pattern.
- `tests/test_cli_generate.py` — CLI test pattern (`main([...])`, `capsys`, `SystemExit` code 2).
- `data/dataset_spec.toml` (lines 293-375) — typo families and must-not-merge pairs: the unit-test inputs.

### New Files to Create

- `src/bomreuse/model.py` — types + JSON round-trip.
- `src/bomreuse/ingest.py` — raw reader.
- `src/bomreuse/normalize.py` — pure normalizers + `normalize()`.
- `tests/test_model.py`, `tests/test_ingest.py`, `tests/test_normalize.py`, `tests/test_cli_normalize.py`, `tests/test_pipeline_invariants.py`.

### Relevant Documentation

- [csv — reader, Dialect.skipinitialspace, newline=""](https://docs.python.org/3.12/library/csv.html#csv.reader) — Why: files must be opened with `newline=""`; `skipinitialspace` must stay `False` so `" Bgi-2031"` survives.
- [decimal — Decimal from str](https://docs.python.org/3.12/library/decimal.html#decimal.Decimal) — Why: `36000 mm` and `36 m` must give the *same* float; divide in `Decimal`, convert once.
- [unicodedata.normalize](https://docs.python.org/3.12/library/unicodedata.html#unicodedata.normalize) — Why: `Polymères` in NFC and NFD must be one supplier.
- [ast — Constant, get_docstring](https://docs.python.org/3.12/library/ast.html#ast.get_docstring) — Why: the static isolation test ignores docstrings, not string constants.

### Patterns to Follow

**Dataclasses:** `@dataclass(frozen=True, slots=True)`, tuples not lists, `Final` constants with a `#:` comment explaining why (see `signatures.py:25-28`).

**Errors:** one `ValueError` subclass per module with a one-line docstring (`SpecError`, `GenerationError`). Messages name the file, the row and the offending value.

**Module docstring:** says *why* the module is shaped this way and cites the architecture section / decision (every existing module does).

**Determinism:** never iterate a `set` into an output; `sorted(...)` before building a tuple. JSON via `sort_keys=True`.

**Tests:** sentence-like names (`test_a_reference_with_a_leading_zero_survives_byte_for_byte`), `tmp_path`, `pytest.mark.parametrize`, no network, no sleep.

**Anti-patterns:** `str.strip()` in `ingest.py`; `float("1,5".replace(...))` without validating the shape first; `pandas`; `difflib`; importing `bomreuse.generate` from a pipeline module; a default value for any path.

---

## DESIGN (decided — the five gate answers, 2026-09-20)

### D1 — Reference key (human decision, gate Q1 — DECISIONS.md 27)

```
reference_key(raw) = drop non-alphanumerics( fold( raw.upper() ) )      fold: O->0, I->1, L->1
```

Uppercase **first**, then fold, so the rule is case-insensitive: `brk-ctrl-valve` and
`BRK-CTRL-VALVE` both give `BRKCTR1VA1VE`. Consequence, accepted: the three must-not-merge pairs of
the spec share a key (`SEAT-RAIL-I`/`-1`, `DOOR-SEAL-O`/`-0`, `HVAC-GRILLE-1L`/`-11`). Measured on the
169 catalogue references: 166 keys, those three collisions and **no accidental one**. Separating them
is #4's `reject`, and the outcome is read in resolution precision. Keys are ids, not labels
(`SHELL-SEAL` -> `SHE11SEA1`): nothing displays them.

### D2 — Component identity (gate Q2)

One `Component` per reference key, holding the sorted distinct raw references and normalized
designations seen. Supplier, unit cost and the raw designation live on the `BomLine` — variability
is carried by the line. Same shape for `SubAssembly`: one per `(variant, reference key)`.

### D3 — Failure behaviour (gate Q3)

| Level | Examples | Behaviour |
| --- | --- | --- |
| Structure | file missing, header differs, row with a wrong cell count, duplicate `line_id` | `IngestError`, exit 1, nothing written |
| Value | `abc`, `1.234,56`, `-3`, `0` as a quantity, unknown unit, empty required cell, bad date | row kept, `raw` intact, `normalized = None`, one `NormalizationIssue` |

### D4 — Notes (gate Q4): ingested, carried, date parsed, text untouched.

### D5 — Units (gate Q5): targets `pcs`, `m`, `kg`. `1,5 m -> 1.5 m`; `36000 mm -> 36.0 m`; `1500 g -> 1.5 kg`. Floats.

### Types (`model.py`)

```python
# raw/normalized pairs — `normalized is None` means "could not be read", and an issue says why
RawText(raw: str, normalized: str)
RawNumber(raw: str, normalized: float | None)
RawInt(raw: str, normalized: int | None)
RawDate(raw: str, normalized: date | None)
Quantity(raw_value: str, raw_unit: str, value: float | None, unit: str | None)

# raw rows: what ingest returns, what #5's baselines read. row_number is 1-based, header excluded.
RawVariantRow(row_number, variant_id, name, design_date, region, seats, bike_spaces, traction)   # all str
RawBomRow(row_number, line_id, variant_id, sub_assembly_ref, sub_assembly_designation,
          component_ref, designation, quantity, unit, supplier, unit_cost_eur)                  # all str
RawNoteRow(row_number, note_id, variant_id, date, text)                                          # all str
RawDataset(variants: tuple[RawVariantRow, ...], bom: tuple[RawBomRow, ...], notes: tuple[RawNoteRow, ...])

# entities
Variant(id: str, raw_id: str, name: RawText, design_date: RawDate, region: RawText,
        seats: RawInt, bike_spaces: RawInt, traction: RawText)
Supplier(id: str, raw_names: tuple[str, ...])                       # id = text_key(name)
Component(id: str, raw_references: tuple[str, ...], designations: tuple[str, ...])
SubAssembly(id: str, variant_id: str, reference_key: str,
            raw_references: tuple[str, ...], designations: tuple[str, ...])   # id = f"{variant_id}:{reference_key}"
BomLine(line_id: str, row_number: int, variant_id: str, parent_id: str, child_id: str,
        quantity: Quantity, sub_assembly_ref: RawText, component_ref: RawText,
        designation: RawText, supplier: RawText, unit_cost: RawNumber)
Note(note_id: str, row_number: int, variant_id: str, date: RawDate, text: str)
NormalizationIssue(source_file: str, row_number: int, row_id: str, field: str, raw: str, reason: str)
NormalizedDataset(variants, suppliers, components, sub_assemblies, lines, notes, issues)   # tuples
```

`BomLine` is the n-ary relation: `(variant_id, parent_id, child_id, quantity.value, quantity.unit)`.
`component_ref.normalized == child_id`; `supplier.normalized` is the `Supplier.id`;
`sub_assembly_ref.normalized` is the sub-assembly's reference key. No entity but `BomLine`,
`SubAssembly`, `Note` and `Variant` names a variant — `Component` and `Supplier` never do.

Orders (all deterministic): variants by `(design_date or date.max, id)`; suppliers, components,
sub-assemblies by `id`; lines and notes in file order; issues in `(source_file, row_number, field)` order.

---

## IMPLEMENTATION PLAN

### Phase 1: Types — `model.py`
### Phase 2: Reader — `ingest.py`
**Independent of:** Phase 3's pure functions (tasks 3a) — they need no row type.
### Phase 3: Normalizers — `normalize.py`
**Depends on:** Phase 1; `normalize()` itself also on Phase 2's `RawDataset`.
### Phase 4: CLI + artifact
### Phase 5: Invariants, then paperwork

---

## STEP-BY-STEP TASKS

One commit per task, conventional prefix, each ending with `(#3)`. Tests land in the same commit as
the code they cover.

### 1. CREATE `src/bomreuse/model.py` + `tests/test_model.py`

- **IMPLEMENT**: the types of the DESIGN section, verbatim names. Then the round-trip:
  `dataset_to_dict(dataset) -> dict[str, Any]`, `dataset_from_dict(data) -> NormalizedDataset`,
  `render_dataset(dataset) -> str`, `dump_dataset(dataset, path)`, `load_dataset(path)`.
  Write `to_dict` with `dataclasses.asdict` plus one pass turning `date` into `isoformat()`; write
  `from_dict` **explicitly**, one small private function per type (`_variant(d)`, `_line(d)`, …) —
  no reflection over field types. Add `SCHEMA_VERSION: Final[str] = "1"` written as `schema_version`
  and checked on load. `from_dict` raises `ModelError(ValueError)` on a missing / unknown key or a
  wrong version, naming it.
- **PATTERN**: `ground_truth.py:330-342` (render/dump/load, `sort_keys=True, indent=2, ensure_ascii=False`, trailing `"\n"`, `newline="\n"`); `spec.py:278-287` (`_check_keys`).
- **IMPORTS**: `dataclasses`, `datetime.date`, `json`, `pathlib.Path`, `typing.Any, Final`. **Nothing from `bomreuse`.**
- **GOTCHA**: `asdict` turns tuples of dataclasses into lists of dicts and keeps plain tuples as tuples — `json` writes both as arrays; `from_dict` must rebuild **tuples**, or the round-trip compares `[...] != (...)`. `float` survives `json` exactly (`repr` round-trips); do not round. `None` must survive (`null`).
- **TESTS**: round-trip equality on a hand-built dataset containing a `None` quantity, an accented supplier, a date; `render_dataset` is byte-stable (same object twice, equal strings; ends with one `\n`); unknown key / wrong `schema_version` raise `ModelError` naming the key; every dataclass is frozen (`FrozenInstanceError`); `BomLine` field names include `variant_id, parent_id, child_id, quantity`; **`Component` and `Supplier` have no field containing `variant`** (introspect `dataclasses.fields`).
- **VALIDATE**: `uv run pytest tests/test_model.py`
- **SATISFIES**: AC4 (BomLine n-ary, component not duplicated per variant — structural half), AC6 (round-trip).
- **COMMIT**: `feat: entity model — raw and normalized side by side, JSON round-trip (#3)`

### 2. CREATE `src/bomreuse/ingest.py` + `tests/test_ingest.py`

- **IMPLEMENT**: constants `VARIANTS_FILE`, `BOM_FILE`, `NOTES_FILE`, `VARIANT_COLUMNS`, `BOM_COLUMNS`, `NOTE_COLUMNS`, `DELIMITER: Final[str] = ";"` (comment: DECISIONS.md 24). `class IngestError(ValueError)`. `read_raw(raw_dir: Path) -> RawDataset`, built on one private `_read_rows(path, columns) -> list[tuple[int, list[str]]]`:
  open with `encoding="utf-8", newline=""`; `csv.reader(handle, delimiter=";")`; first row must equal `columns` exactly, else `IngestError` showing expected vs found; every data row must have `len(columns)` cells, else `IngestError` with file and row number; an empty file is an `IngestError`. Then check unique `line_id`, `note_id`, `variant_id` (raw strings, exact). A file that is missing → `IngestError(f"{name} not found in {raw_dir}")`. A `UnicodeDecodeError` → `IngestError` saying the file is not UTF-8.
- **PATTERN**: `generate.py:680-686` (mirror of the writer); `spec.py:113-120` (wrap the low-level exception, `from exc`).
- **IMPORTS**: `csv`, `pathlib.Path`, `typing.Final`, `bomreuse.model` row types.
- **GOTCHA**: no `.strip()`, no `skipinitialspace`, no `DictReader` (it silently pads short rows with `None` and swallows long ones under `restkey`). A UTF-8 BOM would make the first header cell `"﻿line_id"`: report it as a header mismatch, do **not** open with `utf-8-sig` — the contract says UTF-8 without BOM and the tool does not repair inputs. Do not import `bomreuse.generate`.
- **TESTS**: the committed `data/raw/` loads: 5 variants, 696 BOM rows, 40 notes; **byte-for-byte**: hand-written CSV in `tmp_path` with `0031`, `" Bgi-2031"`, `"BGI-2031 "`, `bgi 2031`, `1,5` → the row fields equal those exact strings; a quoted cell containing `;` and one containing a newline are read as one value; re-joining every ingested row with `;` reproduces the committed file's lines (no quoting in the committed data, so this is exact); header mismatch, short row, long row, missing file, duplicate `line_id`, empty file, non-UTF-8 bytes → `IngestError` whose message names file and row; `ingest`'s column tuples equal `generate`'s (the test imports both — the modules never do).
- **VALIDATE**: `uv run pytest tests/test_ingest.py`
- **SATISFIES**: AC1.
- **COMMIT**: `feat: ingest — raw CSV rows as-is, structure checked strictly (#3)`

### 3a. CREATE `src/bomreuse/normalize.py` (pure functions) + `tests/test_normalize.py`

- **IMPLEMENT**, each a small pure function returning the value or `None` plus, where needed, a reason string (`tuple[float | None, str | None]` is fine; keep it boring):
  - `reference_key(raw: str) -> str` — D1. `_FOLD: Final = str.maketrans({"O": "0", "I": "1", "L": "1"})`; `"".join(c for c in raw.upper().translate(_FOLD) if c.isalnum())`. The `#:` comment states the order and *why* (the `brk-ctrl-valve` case), and that there is no string distance anywhere (A2).
  - `text_key(raw: str) -> str` — `unicodedata.normalize("NFC", raw)`, whitespace collapsed (`" ".join(s.split())`), `casefold()`. Accents are kept: `Polymères` stays `polymères`.
  - `parse_number(raw: str) -> tuple[Decimal | None, str | None]` — strip surrounding whitespace only; accept exactly `^\d+$` or `^\d+[.,]\d+$` (`re.fullmatch`); comma → dot; `Decimal(text)`. Anything else → `None` with a reason: `"empty"`, `"ambiguous separators"` (both `.` and `,`), `"not a number"`.
  - `UNITS: Final[Mapping[str, tuple[str, Decimal]]]` = `pcs, units, unit, u -> ("pcs", 1)`, `m -> ("m", 1)`, `mm -> ("m", 1/1000 as Decimal("0.001"))`, `kg -> ("kg", 1)`, `g -> ("kg", Decimal("0.001"))`. Lookup key: `raw.strip().casefold()`.
  - `normalize_quantity(raw_value, raw_unit) -> tuple[Quantity, list[tuple[str, str, str]]]` (field, raw, reason) — value must be `> 0`; multiply in `Decimal`, `float(...)` once at the end. If either half fails, **both** `value` and `unit` are `None` (a number without its unit is not an amount) and each failing half yields its own issue.
  - `parse_int(raw)`, `parse_date(raw)` (`date.fromisoformat` on the stripped string, `ValueError` → `None, "not an ISO date"`).
- **GOTCHA**: `float(Decimal("36000") * Decimal("0.001")) == 36.0 == float(Decimal("36"))` — do the arithmetic in `Decimal`; `36000 / 1000.0` style float division is what makes `9600 mm != 9,6 m`. `"１２"` (full-width digits) matches `\d` — pass `re.ASCII`. `str.isalnum()` is true for `é`: harmless for references, keep it (dropping letters would merge more, not less). Do not fold `S/5`, `B/8`, `Z/2`: A2 lists `O/0` and `I,l/1` only.
- **TESTS** (parametrized, one behaviour each): `BGI-2031`, `BG1-2031`, `bgi 2031 `, `BGI_2031`, `BGI-2O3I`, ` Bgi-2031` → one key; `BGI-2013` → a different key (transposition stays out of reach); `SEAT-FIX-KIT-447` ≠ `SEAT-FIX-KIT-4471`; `HVAC-GRILLE-l2`, `HVAC-GRlLLE-12`, `hvac-grille-12` → the key of `HVAC-GRILLE-12`; `brk-ctrl-valve` → the key of `BRK-CTRL-VALVE`; **the three must-not-merge pairs of `load_spec()` share a key** (asserted and named as the accepted cost of D1, with a pointer to #4); every typo family of the spec with `within_rules_reach = true` collapses to its canonical's key and every `false` one does not (drive this from `load_spec().typo_families`, no literals); `1,5`+`m` → `1.5 m`; `1500`+`mm` → `1.5 m`; `36000 mm == 36 m == 36,0 m` with `==`, not `isclose`; `1500 g` → `1.5 kg`; `pcs`, `units`, `u`, ` U ` → `pcs`; `48200,00` and `17650.00` costs; `1.234,56`, `abc`, ``, `-3`, `1e3`, `0` quantity, unit `cm` → `None` with the expected reason; `text_key("Artois Polymères ") == text_key("ARTOIS  POLYMÈRES")` and NFD == NFC; a leading-zero reference keeps its zero in the key (`0031` → `0031`).
- **VALIDATE**: `uv run pytest tests/test_normalize.py`
- **SATISFIES**: AC2 (reworded: SI targets are `m` / `kg` / `pcs`, D5), AC3.
- **COMMIT**: `feat: normalize — reference key, units to SI, decimal commas, text (#3)`

### 3b. ADD `normalize(raw: RawDataset) -> NormalizedDataset` to `normalize.py`

- **IMPLEMENT**: one pass over each file, building lines / notes / variants and collecting issues; then derive `components`, `sub_assemblies`, `suppliers` by grouping (`dict[str, set[str]]` → sorted tuples). Variant ids: `normalized = raw.strip().upper()`; a BOM or note row naming a variant absent from `variants.csv` → issue `"unknown variant"` (row kept). An empty reference key (`"---"`) → issue `"empty reference"`; the line keeps `child_id = ""` and **no `Component` is created for the empty key**. `NormalizationIssue.source_file` is the file name, `row_id` the `line_id` / `note_id` / `variant_id` raw value.
- **PATTERN**: `generate.py:251-288` (`render`: one loop, frozen rows appended, tuple at the end).
- **GOTCHA**: build tuples from `sorted(...)`, never from a set directly — the artifact must be byte-identical across `PYTHONHASHSEED` values. `normalize()` takes a `RawDataset` and nothing else: no path, no spec — it cannot be handed a ground truth (A5).
- **TESTS** (on the committed `data/raw/`, plus small hand-built `RawDataset`s): 696 lines, 40 notes, 5 variants in chronological order with `C` last; **zero issues on the committed dataset**; every line's `child_id` is a component id and `parent_id` a sub-assembly id; `len(components) < number of distinct raw component_ref` (duplicates folded) and no two components share an id; the component of key `reference_key("BGI-2031")` lists ≥ 4 raw spellings and is referenced by lines of all five variants — **one entity, not five**; C's `SA-O107` and A's `SA-0107` have the same `reference_key` but different sub-assembly ids; 72 sub-assemblies; suppliers with a trailing space fold into one (`Artois Polymères`); a hand-built row with `quantity="abc"` is kept, `value is None`, exactly one issue naming `line_id`, field `quantity`, raw `abc`; every raw field of every `BomLine` equals the ingested string (`line.component_ref.raw == row.component_ref`, for all 696 rows and all raw-carrying fields).
- **VALIDATE**: `uv run pytest tests/test_normalize.py`
- **SATISFIES**: AC1 (raw survives through normalization), AC3, AC4.
- **COMMIT**: `feat: normalize — rows into entities, unreadable values kept and counted (#3)`

### 4. UPDATE `src/bomreuse/cli.py` + CREATE `tests/test_cli_normalize.py`

- **IMPLEMENT**: `_add_normalize(commands)` and `_normalize(args)`, registered in `main`. Arguments: `--raw` (required, directory) and `--out` (required, directory; `normalized.json` is written inside). Guard **before any work**: if `out.resolve()` is `raw.resolve()` or inside it (`is_relative_to`) → message `the output directory (...) must not be inside the raw directory (...): inputs are read-only`, exit 2. `IngestError` → `error: ...` on stderr, exit 1, nothing written. Success prints, aligned like `_generate`: raw dir, BOM lines, notes, variants, components, sub-assemblies, suppliers, `issues <n>` and, when `n > 0`, a breakdown `field reason count`; then the artifact path. Exit 0 even with issues (they are data, D3). Export `NORMALIZED_FILE: Final[str] = "normalized.json"` from `model.py`.
- **PATTERN**: `cli.py:34-62`; update the module docstring's sentence about paths to mention `normalize`.
- **GOTCHA**: neither path gets a default (mirrors `--out` / `--ground-truth`, and keeps A5 structural). `_normalize` has no parameter and no option that could carry a ground-truth path.
- **TESTS**: success on the committed data writes exactly `normalized.json`, exit 0, stdout contains `BOM lines` and `issues`; `load_dataset` reads it back and equals `normalize(read_raw(...))`; missing `--raw` or `--out` → `SystemExit` 2; `--out` inside / equal to `--raw` → 2, nothing written; an empty `--raw` directory → 1, `not found` on stderr, `--out` not created; running twice gives byte-identical artifacts.
- **VALIDATE**: `uv run pytest tests/test_cli_normalize.py && uv run bomreuse normalize --raw data/raw --out out && git status --short`  (expect no change: `out/` is gitignored)
- **SATISFIES**: AC6; issue scope "`bomreuse normalize` added to the CLI".
- **COMMIT**: `feat: bomreuse normalize — out/normalized.json, read back into the same types (#3)`

### 5. CREATE `tests/test_pipeline_invariants.py`

- **IMPLEMENT** three invariants plus one determinism check. Constants at the top, commented:
  `NOT_PIPELINE = {"generate.py", "catalogue.py", "dirt.py", "ground_truth.py", "cli.py", "evaluate.py"}` — the generator side, the entry point that routes the path, and the only legitimate reader (#5; listed now so the rule does not have to be edited when it lands).
  1. **Runtime isolation**: `shutil.copytree(ROOT / "data" / "raw", tmp_path / "raw")`, run `main(["normalize", "--raw", ..., "--out", tmp_path / "out"])` with `monkeypatch.chdir(tmp_path)` so no relative path can reach the repository; assert exit 0 and the artifact exists. Docstring: later issues extend this to `run`.
  2. **Static isolation**: `mentions_ground_truth(source: str) -> list[str]` walks the AST and reports (a) `import` / `from` of `bomreuse.ground_truth` or of a name `ground_truth`, (b) any `Name.id`, `Attribute.attr`, `arg.arg`, `keyword.arg`, function / class name containing `ground_truth` (case-insensitive), (c) any `str` constant containing `ground_truth` or `ground truth` that is **not a docstring** (collect docstring nodes first via `ast.get_docstring`-equivalent: first statement `Expr(Constant(str))` of a module / class / function). Parametrize over every `src/bomreuse/*.py` not in `NOT_PIPELINE`; assert the list is empty, with a message quoting CLAUDE.md rule 2. **Test the scanner itself** on four synthetic sources (import, identifier, string path, docstring-only mention → flagged ×3, clean ×1): a scanner that cannot fail proves nothing.
  3. **Inputs read-only**: sha256 + size + sorted file list of the copied raw dir before and after the run; equal. Also assert the run created nothing inside it.
  4. **Determinism of the artifact across processes**: two `subprocess.run([sys.executable, "-m", "bomreuse.cli", "normalize", ...])` with `PYTHONHASHSEED` 1 and 2 → identical bytes.
- **PATTERN**: `tests/test_generate_invariants.py:52-64` (subprocess), `:100-108` (AST walking), its module docstring (why these tests matter).
- **GOTCHA**: a pipeline module's **docstring** may say "never reads the ground truth" — that is documentation, which is why docstrings are exempt and everything else is not. Comments are not in the AST; acceptable. Keep the two subprocesses the only ones: suite budget is 30 s, currently ~1 s.
- **VALIDATE**: `uv run pytest tests/test_pipeline_invariants.py` then mutation-check by hand: add `GT = "data/ground_truth/x.json"` to `normalize.py`, see the test fail, revert.
- **SATISFIES**: AC5 (the three invariant tests).
- **COMMIT**: `test: invariants — ground-truth isolation (runtime and AST), inputs read-only (#3)`

### 6. UPDATE paperwork

- `CLAUDE.md` "Intended module boundaries": `ingest.py` — add "structure checked strictly"; `normalize.py` — "reference key (uppercase, then O/I/L folding), units to SI (m, kg, pcs), text, decimal commas; unreadable values kept and counted"; `model.py` — "raw rows, entities: Variant, SubAssembly, Component (candidate group), Supplier, BomLine (n-ary), Note; JSON round-trip".
- `README.md` "How to run": add the `normalize` command in its own fenced block; replace "The rest of the pipeline (`normalize`, `run`, …)" by the list without `normalize`. **No number** goes into Results.
- `CONTEXT.md` Status: one dated line. `.claude/STATUS.md`: #3 to Done with the date, Current Focus → next is #5's first slice (scorer + two baselines); move the "Handover from #2 to #3" note out, add a 3-line handover to #4/#5 (key inherited, candidate groups, three shared keys, baselines read `RawBomRow`).
- `.claude/skills/piv-validate/SKILL.md`: no command changed — leave it.
- **VALIDATE**: `time uv run pytest` (all green, < 30 s) ; `git status --short data/` (empty).
- **COMMIT**: `docs: CLAUDE.md, README, CONTEXT, STATUS — normalize exists (#3)`

---

## TESTING STRATEGY

### Unit Tests
Pure functions of `normalize.py` (parametrized), `model.py` round-trip, `ingest.py` on hand-written files in `tmp_path`. The spec's typo families and must-not-merge pairs are read through `load_spec()` so the tests follow the contract rather than copy it.

### Integration Tests
`normalize(read_raw(data/raw))` on the committed dataset; the CLI end to end; the four invariants.
**No test in this issue opens the ground truth.** Whether the folding is *good* is #5's measurement, not a #3 assertion — tests here prove the code does what it says (CLAUDE.md, "Testing").

### Edge Cases
Leading zero, leading / trailing / inner double space, NBSP, mixed case, `l` vs `L` vs `I` vs `1`, `O` vs `0`, empty reference, reference made only of separators, `1,5` / `1.5` / `1.50` / `01,5`, `1.234,56`, `1 234`, negative, zero, exponent, full-width digits, unknown unit, unit with case / spaces, empty cell, unknown variant on a BOM row, short / long row, duplicate `line_id`, BOM-prefixed file, non-UTF-8 file, quoted cell with `;` or newline, NFD accents.

---

## VALIDATION COMMANDS

### Level 1: Syntax
`uv run python -m compileall -q src tests`  (no linter, no type checker — on purpose, see `piv-validate`)

### Level 2: Unit tests
`uv run pytest tests/test_model.py tests/test_ingest.py tests/test_normalize.py`

### Level 3: Integration and invariants
`uv run pytest tests/test_cli_normalize.py tests/test_pipeline_invariants.py` then `time uv run pytest` (whole suite, < 30 s, offline)

### Level 4: Manual
```bash
uv run bomreuse normalize --raw data/raw --out out
uv run python -c "from pathlib import Path; from bomreuse.model import load_dataset; d = load_dataset(Path('out/normalized.json')); print(len(d.lines), len(d.components), len(d.sub_assemblies), len(d.suppliers), len(d.issues))"
```
Expected on the committed dataset: `696 160 72 12 0` (measured with the D1 rule during planning — a sanity check for the eye, **not** a test assertion: a catalogue edit legitimately moves the 160).
`git status --short data/` must print nothing. `grep -rn "ground" src/bomreuse/ingest.py src/bomreuse/normalize.py src/bomreuse/model.py` should show docstrings only.

### Level 5
`/piv-validate` — expect: 1 PASS · 2 N/A (until #5) · 3 Determinism PASS, Ground-truth isolation PASS (now present), Inputs read-only PASS (now present), Traceable findings MISSING (belongs to #4) · 4 PASS.

---

## ACCEPTANCE CRITERIA

- [ ] AC1 — a reference with a leading zero, surrounding whitespace or mixed case survives ingestion **and normalization** byte-for-byte in its `raw` field.
- [ ] AC2 — `1,5 m` → `1.5 m`, `1500 mm` → `1.5 m`, `36000 mm == 36 m`; `g` → `kg`; `pcs` / `units` / `u` → `pcs`; the raw value and raw unit stay on the record. *(Issue wording "1500 mm (or the SI unit chosen)": the unit chosen is `m`, D5.)*
- [ ] AC3 — `BGI-2031`, `BG1-2031`, `bgi 2031 ` share one id, with no string-distance code anywhere in `src/`.
- [ ] AC4 — `BomLine` carries (parent, child, quantity, unit, variant); one `Component` per key whatever the number of variants; `Component` has no variant field.
- [ ] AC5 — runtime isolation, AST isolation (scanner mutation-tested), read-only hash: all pass.
- [ ] AC6 — `out/normalized.json` round-trips to equal objects, and is byte-identical across runs and hash seeds.
- [ ] Zero `NormalizationIssue` on the committed dataset; a planted unreadable value yields exactly one, row kept.
- [ ] `uv run pytest` green, < 30 s, offline; `data/**` untouched; no new dependency; `CLAUDE.md` and `README.md` true.

## COMPLETION CHECKLIST

- [ ] Tasks 1 → 6 done in order, one commit each, all referencing `#3`, none touching another issue
- [ ] Each task's VALIDATE passed when it was finished
- [ ] Level 1-5 commands run; manual figures eyeballed
- [x] `DECISIONS.md` 27 written at the human's request (2026-09-20) — nothing else is owed there unless a dependency appears
- [ ] Implementation report written to `.claude/reports/ingest-normalize-entity-model-report.md`

---

## OPEN QUESTIONS / ASSUMPTIONS

- **Settled — DECISIONS.md 27** records gate Q1 (fold order, `L→1`, the accepted cost on the three must-not-merge pairs). The human validated the wording and asked for the line to be written, on 2026-09-20, before implementation. `normalize.reference_key`'s comment cites it.
- Assumed — `#4` will map each line to a canonical component id of its own (splitting `reject` groups); `BomLine.child_id` stays the key. If #4 prefers to rewrite `child_id`, `model.py` needs no change, only a new artifact.
- Assumed — issues do not fail the run (exit 0). If a strict mode is ever wanted (`--strict` → exit 1 when `issues`), it is a three-line follow-up, deliberately not built now.
- Assumed — `RawInt` for `seats` / `bike_spaces` is worth its ten lines: `48.0` seats in the report's sponsor summary would read as sloppiness.
- Not reopened: pandas, pydantic mirrors, string distance, a default raw path.

## NOTES (open canvas)

**Why the raw rows live in `model.py` and not `ingest.py`.** A4 says the dataclasses are the single set of types and #5's baselines consume raw rows without wanting to import a reader. `ingest.py` stays a 60-line reader.

**Why five tiny pair types rather than one generic `Normalized[T]`.** PEP 695 generics work in 3.12, but `from_dict` cannot recover `T` from JSON without reflection, and CLAUDE.md asks for "no clever metaprogramming". Five boring classes read in a minute.

**Why `Decimal` inside, `float` outside.** `SignatureItem.quantity` is a float and `signatures._same_amount` already tolerates 1e-9, so floats are safe downstream; but doing the unit arithmetic in `Decimal` makes `36000 mm` and `36 m` *equal*, which keeps the unit tests exact and the artifact stable.

**What D1 costs, in numbers known today.** 169 catalogue references → 166 keys; the three collisions are exactly the three must-not-merge pairs. On the committed raw file: 187 distinct raw component references → 160 keys. The two out-of-reach spellings (`BGI-2013`, `SEAT-FIX-KIT-447`) keep keys of their own, as designed. These were computed in a scratch script during planning, outside the pipeline, and are not claims about quality — `evaluate` makes those.

**A risk to watch in #4, recorded here so it is not rediscovered:** with shared keys, `Component.designations` of `SEATRA111` holds two different product names. That is the signal `reject` needs; it is why `designations` is kept on the component and the raw designation on the line.

**Sequencing.** Tasks 2 and 3a are independent and could be written in parallel; with ~600 lines in total it is not worth a second worktree.

**Confidence: 8.5/10** for a one-pass implementation. The residual risk is the AST scanner's docstring exemption (easy to get subtly wrong — hence the scanner's own four tests) and tuple/list drift in `from_dict`.

## AMENDMENTS

- (none)
