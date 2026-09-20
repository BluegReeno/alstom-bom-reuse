# Implementation Report — Synthetic dataset generator, planted defects and ground truth (#2)

**Plan**: `.claude/plans/synthetic-dataset-generator.md`   **Branch**: `claude/piv-plan-implementation-0825fc`   **Status**: COMPLETE

## Summary

`bomreuse generate` now produces, from a fixed seed, the dataset the whole build is measured on:
three `;`-separated raw CSVs (5 variants, 696 BOM lines, 40 FR / EN / mixed notes) and one
pydantic-validated ground-truth JSON (169 true components, the planted typo families, the
must-not-merge pairs, 15 backtest labels, 149 defect records, per-note facts). The generator is two
layers — a hand-written, seed-independent story (`catalogue.py` + the spec's story cases) and seeded
dirt (`dirt.py`) — and it owns identity: true components first, raw strings second, no pipeline
import and no canonical key anywhere on its side (ARCHITECTURE A3). The backtest labels are
declared in the catalogue and confronted with `signatures.compare` by a test, never computed with it.

## Tasks completed

- 1 pydantic → `pyproject.toml`, `uv.lock` (UPDATE)
- 2 ground-truth schema → `src/bomreuse/ground_truth.py` (CREATE)
- 3 dirt operators → `src/bomreuse/dirt.py` (CREATE)
- 4 catalogue → `src/bomreuse/catalogue.py` (CREATE)
- 5 generator → `src/bomreuse/generate.py` (CREATE)
- 6 CLI → `src/bomreuse/cli.py` (CREATE), `pyproject.toml` `[project.scripts]` (UPDATE)
- 7 invariants → `tests/test_generate_invariants.py` (CREATE)
- 8 dataset → `data/raw/{variants,bom,notes}.csv`, `data/ground_truth/ground_truth.json` (CREATE)
- 9 paperwork → `CLAUDE.md`, `README.md`, `CONTEXT.md`, `.claude/STATUS.md` (UPDATE)

One commit per task, each referencing `#2`, plus one `fix:` commit (see deviations).

## Tests added

200 new tests (68 → 268), whole suite 0.6 s, offline.

- `tests/test_ground_truth_schema.py` (22) — round-trip, byte-stable rendering, 17 refused violations each naming its offender.
- `tests/test_dirt.py` (27) — a typo never returns its input, out-of-reach kinds are never generated, rendered quantities convert back exactly (`Decimal`), costs, noise.
- `tests/test_catalogue.py` (44) — spec coverage, 14/15 sub-assemblies, minimum size, C's mix 4/5/3/1/2, planted components outside story sub-assemblies, must-not-merge members apart, overrides blunt and disjoint, note mix, wording stock, chronology.
- `tests/test_generate.py` (86) — story contents equal the spec, every family spelling emitted, out-of-reach placement, must-not-merge ids, every defect category, deviating unit lines, constant costs outside planted conflicts, volume, literal wordings on 4 seeds, unsafe reuse ×2, **the seed moves the dirt never the story**, 25 seeds hold together, 3 `GenerationError` paths.
- `tests/test_cli_generate.py` (6) — files written where told, no default for either path, ground truth inside `--out` refused before any write.
- `tests/test_generate_invariants.py` (15) — byte-identity in process and across two interpreters (`PYTHONHASHSEED` 1 / 2), no `TRUE-` / label / defect tag in raw files, AST import isolation, no ground-truth path in `src/`, **the bridge** (labels, ancestor sets and diffs vs `signatures.compare` on true ids — mutation-checked: a wrong ancestor list fails it), freshness of the committed data.

## Validation results

- `uv run python -m compileall -q src tests` — pass
- `time uv run pytest` — **268 passed in 0.58 s** (budget 30 s), no network, no model
- regenerate + `diff -r` against committed data — IDENTICAL
- `grep -rl "TRUE-" data/raw` — no output; `grep -rn "data/ground_truth" src/` — no output
- `piv-validate`: 1 Tests PASS · 2 Evaluation gate N/A (until #5) · 3 Invariants: determinism PASS; ground-truth isolation (runtime + pipeline AST), inputs read-only and traceable findings are not written yet — they belong to #3 / #4, as the plan states · 4 Definition of done PASS (pydantic is covered by DECISIONS.md 19; CLAUDE.md and README.md updated and true)
- No linter / type checker in this project, on purpose.

## Acceptance criteria

AC1 byte-identity (in and across processes) ✓ · AC2 every defect category planted and recorded ✓ · AC3 all typo families emitted, out-of-reach included ✓ · AC4 must-not-merge pairs emitted and declared ✓ · AC5 no sub-assembly below 4 ✓ · AC6 no pipeline import, nor `signatures` ✓ · AC7 `data/raw/` inputs only, no true id ✓ · AC8 offline, both paths from the command line ✓ · plan's four additions ✓.

## Deviations from the plan

1. **"Unit conflicts never in C"** is read as: the *deviating line* is never in the newest variant nor in a story sub-assembly. D3 plants one conflict in E's Interior lighting, a sub-assembly C also carries, so the mechanically derived pair `(C, E)` is recorded. D3 and D5 could not both hold literally; the mechanical derivation (plan's NOTES) won.
2. **`catalogue.py` holds one function**, `contents(spec)`, resolving its own content sources (`FromStory` / `Own` / `SameAs` / `Derived`). The plan said data and dataclasses only; its tests need resolved contents before `generate.py` exists.
3. **`unsafe` is derived, not declared**: every obsolescence / replacement contradiction whose offender is the newest variant, on a part of a non-`new` sub-assembly. The catalogue is written so exactly the two planted ones (Auxiliary converter, Bike module) come out, and a test pins that.
4. **C's mistyped sub-assembly reference `SA-O107` is hand-written**, not seeded — a seeded one would make the backtest section vary with the seed, against "the seed never moves the story".
5. **One extra commit**: `fix: notes are filed once their fact is effective, in date order`. Reading `notes.csv` by eye (task 8) showed "obsolete since 2026-02-01" in a note dated 2025. No label, ancestor or contradiction changed.
6. `reused` ancestors are found by **equality of resolved content**, not object identity: C's trailer bogie is the story's *right* side, a different object from A's *left* side with equal counts.
7. Sub-assembly designation noise is drawn once per `(variant, sub-assembly)`, not per line — a flat export repeats the parent's designation.
8. Counts landed slightly off the plan's estimates: 169 components (plan: ≈145), 13 typo plans, 3 unit conflicts, 5 supplier and 5 cost overrides — all inside the plan's ranges.

## Issues encountered

- A literal U+FEFF slipped into a test source through the editor; replaced by its escape before commit.
- The wording-stock test caught a real hole on first run (one mixed-language obsolescence note, two wordings): the literal patterns CONTEXT.md quotes are guaranteed because wordings are dealt in turn and no group is smaller than its stock.

## For the human

- `DECISIONS.md` gained line 24 (the `;` delimiter) **after** the implementation, at the human's explicit request and with the wording they validated — the agent transcribed, it did not decide. No line was added for pydantic landing: Dec. 19 covers it.
- Forward reference for **#3**: its AST test must exempt `generate.py`, `ground_truth.py` and `cli.py`. For **#4**: must-not-merge members sit in different sub-assemblies, so a false merge costs precision instead of crashing `Signature`. For **#5**: any listed ancestor is acceptable; `components[].raw_references` is injective.

### Ready for the next step

All changes complete, validations pass. Next: `piv-create-pr` (this report fills the PR body), then `piv-review-pr`.
