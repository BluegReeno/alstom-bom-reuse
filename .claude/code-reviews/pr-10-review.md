# Review — PR #10: synthetic dataset generator, planted defects and ground truth (#2)

**Recommendation: APPROVE** — no critical or high issue, validation green, the PR does what #2 asks.
Reviewed at `64cf0b2`, in a fresh context, against `CLAUDE.md`, issue #2, the plan and the
implementation report. The eight deviations listed in the report are treated as decisions, not issues.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 1 |
| Low | 4 |

## Validation (re-run by the reviewer)

| Check | Result |
| --- | --- |
| `uv run pytest` | **268 passed**, 0.78 s wall-clock (budget 30 s), offline |
| Regenerate with the default seed + `diff -r` against `data/` | identical (raw CSVs and ground truth) |
| `grep -rl "TRUE-" data/raw` | no output |
| `grep -rn "data/ground_truth\|ground_truth.json" src/` | no output |
| `bomreuse generate` with `--ground-truth` inside `--out` | refused, exit 2, nothing written |
| Evaluation gate | N/A until #5 |
| README figures (5 variants, 696 lines, 135–145 per variant, 40 notes) | match the generator's own summary |
| Commits | 13, all conventional, all `#2`, no mixed issue |

## Medium

### M1 — Three `reused` ancestors are not identical in the raw files, and the ground truth does not say so

`generate.py:494-498` finds `reused` ancestors by equality of **true** content. Three of the listed
ancestors cannot be seen as identical by any honest pipeline, because the dirt planted on them
changes what the raw line says:

- `(B, SA-0106)` Gangway — `COUP-JUMPER-CABLE` is `4 pcs` (unit conflict), C has `9.6 m` — `bom.csv` L00172;
- `(E, SA-0108)` Interior lighting — `LIGHT-CABLE` is `2 pcs`, C has `45000 mm` — L00491;
- `(E, SA-0105)` Braking unit — carries the out-of-reach `BGI-2013` — L00445.

All three are emitted with `diff: null`. The label stays reachable through the other ancestors, and
the report's forward reference says "#5: any listed ancestor is acceptable" — but that rule lives in
a report, not in the contract #5 will read. If #5 ever scores the ancestor *set*, or the diff against
E, the pipeline is penalised for telling the truth, and the out-of-reach placement moves with the seed.

Deviation 1 documents the `(C, E)` defect pair, not this consequence on the backtest section.

**Fix (small):** state the rule where #5 will find it — the `Ancestor` / `BacktestLabel` docstring in
`ground_truth.py` ("ancestors are equal in true content; a hit on any one of them is a hit") and a
line in issue #5. Optional: a test asserting every `reused` label keeps at least one ancestor whose
raw lines carry no unit conflict and no out-of-reach spelling, over the 25 seeds already looped on.

## Low

- **L1 — `cli.py:54`**: `CatalogueError` (raised by `catalogue.contents`) is not in the `except`, so a
  broken catalogue gives a traceback instead of `error: …` / exit 1. Same family: a note script citing
  a reference absent from the master ends in a bare `KeyError` (`generate.py:420-422`, `:481`) rather
  than a `GenerationError`. Static data and the tests cover today's catalogue; this is about the next edit.
- **L2 — `cli.py:45`**: the "ground truth never inside the raw directory" guard lives in the CLI only.
  `generate.generate()` — the function tests and #5 will call — writes wherever told. A5 wants the
  invariant structural; moving the check into `generate()` (the CLI keeps its message) costs three lines.
- **L3 — `ground_truth.py:181-183, 54`**: `effective_date`, `scope` and `base_unit` are free `str` at the
  one boundary pydantic is there to guard. An ISO-date pattern and a `Literal["pcs", "m", "kg"]` would
  make a hand-edited ground truth fail loudly.
- **L4 — `generate.py:584`**: `# type: ignore[arg-type]` in a project that runs no type checker, on
  purpose. Harmless; a `dict[gt.DefectType, …]` annotation on `observed` removes the need.

## What is done well

- **A3 is real, not declared.** True ids first, raw strings second, no canonical key on the generator's
  side; the injectivity check (`generate.py:407-413`, again in the schema) means a seeded typo that
  lands on a must-not-merge partner fails generation instead of corrupting the score.
- **The bridge test** (`test_generate_invariants.py:170`) confronts declared labels, ancestor sets and
  diffs with `signatures.compare` on true ids — two independent statements of the story, and the
  failure message points at the catalogue, never the thresholds (Decision 17).
- **Determinism is tested where it breaks**: two interpreters with different `PYTHONHASHSEED`, one RNG
  per concern, `Decimal` through `str()`, controlled line terminators.
- **The dataset can embarrass the tool**: out-of-reach spellings, one forced into C so "Known limits"
  gets a figure; notes respected by the BOM as precision negatives; a no-fact note that still cites
  `BGI-2031`; `SA-0213` kept with changed content so the exact-reference baseline is wrong somewhere.
- Defect records are derived mechanically from emitted rows; counts check out by hand
  (3 unit conflicts → 11 pairs, 5 supplier and 5 cost overrides → 20 pairs each).
- The freshness test makes a catalogue edit without regeneration impossible to merge green.
- Docs are true: `CLAUDE.md` module block, README run instructions and figures, `STATUS.md` handover.

## For the human

- `DECISIONS.md` line 24 was transcribed by the agent at your request; issue #2 says decision lines are
  written by the human. The report is transparent about it — confirming it at merge is enough.
- Rule 2's enforcing test (pipeline never reads the ground truth) is deferred to #3 / #4 as planned;
  #3's AST test must exempt `generate.py`, `ground_truth.py` and `cli.py`.

Next step if you want the findings closed before merge: `piv-fix-review-findings` on this report
(M1 + L1 + L2 are ~20 lines together), then `piv-validate`.
