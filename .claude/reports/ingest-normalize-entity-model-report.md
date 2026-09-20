# Implementation Report — Ingest, normalize and the entity model (#3)

**Plan**: `.claude/plans/ingest-normalize-entity-model.md`   **Branch**: `claude/issue-3-ingest-normalize`   **Status**: COMPLETE

## Summary

`bomreuse normalize --raw <dir> --out <dir>` reads the three raw CSV files exactly as they are,
turns them into the project's single set of types — frozen dataclasses carrying the raw value and
the normalized value side by side — and writes `out/normalized.json`, which reads back into equal
objects. Three new modules, standard library only: `model.py` (types + JSON round-trip),
`ingest.py` (strict structure, untouched values), `normalize.py` (pure rule functions, then
`normalize(raw)`). The ground-truth isolation and read-only invariants now have their tests.

On the committed dataset: 696 lines, 160 components (candidate groups), 72 sub-assemblies,
12 suppliers, 0 issues — the figures measured during planning. These are counts, not quality
claims; `evaluate` (#5) makes those.

## Tasks completed

- 1 — entity model → `src/bomreuse/model.py`, `tests/test_model.py` (CREATE) — `ae0b6de`
- 2 — ingest → `src/bomreuse/ingest.py`, `tests/test_ingest.py` (CREATE) — `7372c85`
- 3a — pure normalizers → `src/bomreuse/normalize.py`, `tests/test_normalize.py` (CREATE) — `1848990`
- 3b — `normalize(raw)` → `normalize.py`, `model.py`, `tests/test_normalize.py`, `tests/test_model.py` (UPDATE) — `2674163`
- 4 — CLI → `src/bomreuse/cli.py` (UPDATE), `tests/test_cli_normalize.py` (CREATE) — `bdd2d90`
- 5 — invariants → `tests/test_pipeline_invariants.py` (CREATE) — `368ef86`
- 6 — paperwork → `CLAUDE.md`, `README.md`, `CONTEXT.md`, `.claude/STATUS.md` (UPDATE) — `c26c8e4`, `9014573`

## Tests added

273 tests (suite: 301 → 574, 1.4 s of a 30 s budget, offline).

- `test_model.py` (36) — round-trip to equal objects, tuples rebuilt, `None` and floats survive,
  byte-stable text, unknown / missing key and wrong `schema_version` refused by name, every type
  frozen, `BomLine` n-ary, `Component` and `Supplier` have no variant field.
- `test_ingest.py` (32) — committed data loads (5 / 696 / 40); re-joining ingested cells gives back
  each committed file line for line; leading zero, spaces, NBSP survive; quoted `;` and newline;
  header mismatch (incl. BOM-prefixed), short / long / blank row, missing file, duplicate ids,
  empty file, non-UTF-8 → `IngestError` naming file and row; columns equal the generator's.
- `test_normalize.py` (156) — reference-key families driven by `load_spec()` (within reach
  collapse, out of reach do not, the three must-not-merge pairs share a key — the accepted cost
  of DECISIONS.md 27); numbers, ints, dates, units; `36000 mm == 36 m == 36,0 m` with `==`;
  `normalize()` on the committed data and on hand-built rows: zero issues, one entity per key
  across five variants, every raw cell carried untouched, each unreadable cell → exactly one issue.
- `test_cli_normalize.py` (12) — success, round-trip, byte-identical reruns, no default path, no
  other option, `--out` inside `--raw` refused (2), structure error (1, nothing written), issues
  counted with exit 0.
- `test_pipeline_invariants.py` (37) — scanner self-tests (15 flagged, 5 clean), static isolation
  per pipeline module, no pipeline module imports the generator side, runtime isolation,
  read-only inputs (sha256 + size + file list, on a copy and on `data/raw/`), artifact identical
  across `PYTHONHASHSEED` 1 and 2.

## Validation results

- Level 1 `compileall` — PASS
- Level 2 / 3 `uv run pytest` — PASS, 574 passed in 1.4 s
- Level 4 manual — `696 160 72 12 0`, as expected; `git status --short data/` empty; no `ground`
  in `ingest.py` / `normalize.py` / `model.py`; no string-distance import in `src/`
- Mutation check (task 5) — `GT = "data/ground_truth/x.json"` added to `normalize.py`: the static
  test failed naming line and constant; reverted
- Level 5 `piv-validate` — 1 PASS · 2 N/A (`evaluate` arrives with #5) · 3 Determinism PASS,
  Ground-truth isolation PASS (now present), Inputs read-only PASS (now present), Traceable
  findings MISSING (belongs to #4) · 4 PASS (no new dependency; `pyproject.toml`, `uv.lock`,
  `data/**` untouched)

## Deviations from the plan

1. **`BomLine` gained a field: `sub_assembly_designation: RawText`.** The plan's types carried
   the sub-assembly designation only as normalized text on `SubAssembly`. That column is dirty in
   `bom.csv` (`HVAC unit `, `TOILET MODULE`, `traction package`), so its raw characters would not
   have survived into the artifact — against the feature's own user story and AC1's spirit. With
   the field, the test "every raw cell of every row is carried on its line untouched" covers nine
   of the ten columns: the raw `variant_id` is the exception, see "Issues encountered" (wording
   corrected after the PR review, L2). Landed in the 3b commit, with the reason in its message.
2. **Every cell is required.** The plan's D3 says "empty required cell" without listing which.
   Rule applied: an empty (or whitespace-only) cell in any column of the three files is one issue
   with reason `empty` (`empty reference` for the two reference columns). No supplier, component
   or sub-assembly entity is created for an empty key. Since the PR review (M6) that covers both
   halves of the sub-assembly's key: a line whose variant is empty or unknown keeps its row and
   its issue, gets `parent_id = ""`, and creates no sub-assembly.
3. **Extra issue reasons beyond the plan's list**: `not positive` (quantity ≤ 0; a zero *cost* is
   accepted), `duplicate variant` (two raw variant ids normalizing to one — both rows kept), and
   `parse_date` checks the `YYYY-MM-DD` shape before `date.fromisoformat`, which alone also
   accepts `20190314` and week dates.
4. **`parse_unit` is a public function** (the plan folded the lookup into `normalize_quantity`);
   it made the unit tests one-behaviour-each.
5. **The plan's `asdict` gotcha was inaccurate**: `dataclasses.asdict` keeps every tuple a tuple.
   `dataset_to_dict` converts tuples to lists and dates to ISO strings so that it equals what
   `json.loads` returns from the artifact. `from_dict` rebuilds tuples as planned.
6. **`NOT_PIPELINE` extras**: a second static test asserts no pipeline module imports
   `generate`, `catalogue`, `dirt`, `ground_truth` or `evaluate` (the reverse of the existing A3
   test). `bomreuse_imports` was re-written inline rather than imported from
   `tests/test_generate_invariants.py`: importing that module would run its module-level
   `load_spec()` and drag its fixtures along for six lines of AST walking.
7. **One extra docs commit** (`9014573`): the README example first cited `36000 mm`, a value that
   is not in the committed `bom.csv`; replaced by line `L00052` (`42000 mm` → `42.0 m`), checked
   against the artifact.

## Issues encountered

None blocking. Worth knowing for #4 and #5:

- `BomLine.variant_id` and `Note.variant_id` are normalized (`strip().upper()`); the raw variant
  cell is not carried on the line (it is clean in the committed data, and an unknown or empty one
  is recorded in an issue with its raw value). If a later stage needs it, it is one `RawText` away.
- `RawText.normalized` is a *key* (`text_key`: NFC, spacing collapsed, casefolded), not a display
  label. Reports should show `raw`.
- The three must-not-merge components (`SEATRA111`, `D00RSEA10`, `HVACGR111E11`) each hold two
  designations, as the plan predicted — the signal `reject` needs.
