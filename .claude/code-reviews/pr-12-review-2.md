# Review 2 — PR #12: ingest, normalize and the entity model (#3)

**Recommendation: APPROVE** — no critical, high or medium issue at `510c041`. Every finding of the
first review (`pr-12-review.md`, at `3466df5`) is fixed or deferred to an open issue; three low
findings remain, none blocking. Second pass in a fresh context: deep pass by a clean-context
sub-agent that tried to break each fix on a copy of `data/raw/`, the three new findings re-run by
the reviewing session. Rubric: `CLAUDE.md`, the plan, the implementation report (its seven
deviations are decisions, not issues), `DECISIONS.md` 24, 27, 28.

Posted as a comment: GitHub does not let the PR's author approve their own PR.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 3 |

## Validation

| Check | Result |
| --- | --- |
| `uv run pytest` | PASS — 612 passed in 1.5 s of a 30 s budget, offline (574 at the first review) |
| `compileall` on `src`, `tests` | PASS |
| `uv run bomreuse normalize --raw data/raw --out <scratch>` | `696 / 160 / 72 / 12 / 0`, exit 0 — the figures of the PR body, the README and the report |
| `data/`, `pyproject.toml`, `uv.lock` vs `origin/main` | untouched; working tree clean after the run |
| Evaluation gate | N/A — `evaluate` arrives with #5 |
| Invariants | Determinism, ground-truth isolation (static + runtime, now with a decoy), inputs read-only: present and green. Traceable findings: missing, belongs to #4 |
| Definition of done | No new dependency; `CLAUDE.md` module list and README still true; README's new known limit checked against the code |

## First-review findings at HEAD

| # | Status | Evidence |
| --- | --- | --- |
| H1 | FIXED | `cli._writes_into` compares by `samefile` and resolves the artifact, not only its directory. 17 attacks on a copy of `data/raw/` (case variant, artifact pre-linked to `bom.csv` by symlink and by hard link, `--out` a symlink into raw, `--out == --raw`, deep not-yet-existing path under raw, `..` segments, raw itself a symlink): all exit 2, sha256 of the inputs unchanged; a sibling `--out` still exits 0. Restoring the old guard makes the three new tests fail. |
| M1 | FIXED for the reported cases | 13 usage errors → `error: …`, exit 1, no traceback. One new gap, in the new guard only: L-A. |
| M2 | DEFERRED | #13, open, in the STATUS backlog "before the first stage that loads the artifact". |
| M3 | FIXED | `from .generate import x`, `from . import catalogue`, `importlib.import_module`, `__import__` each fail the test under mutation; `rglob` in place. |
| M4 | FIXED | The decoy test fails when the pipeline opens the decoy through `read_bytes`, `os.open`, or `chdir` + relative open, even spelled `"ground" + "_" + "truth"`; it asserts the hook saw `bom.csv`, so it cannot pass on an empty record. |
| M5 | FIXED at the upper bound | 5000-digit `seats`, 400-digit quantity or cost → `out of range`, exit 0; `allow_nan=False` present and tested. The lower bound is L-B. |
| M6 | FIXED | Empty or unknown variant: row kept, one issue, `parent_id == ""`, no sub-assembly, round-trip holds. Logged as Decision 28. |
| L1–L5 | FIXED | NFC in `reference_key` with a test; docstring and report wording corrected; `1,500 → 1.5` in the README's known limits; `csv.reader(strict=True)` with refusal tests; no `type: ignore` left in `test_normalize.py`. |
| Generator guard | DEFERRED | #14, open. |

## Low

### L-A — The new guard can itself print a traceback
`src/bomreuse/cli.py:87` (`_writes_into`, `:125-130`). The guard runs outside any `try`.
Reproduced: with `out/normalized.json` a symlink to itself, `bomreuse normalize` ends in
`RuntimeError: Symlink loop from '…/out/normalized.json'`; a 300-character path component gives
`OSError: [Errno 63] File name too long`. Nothing is written and the inputs' hashes are unchanged,
so rule 3 holds — this is M1's "usage errors are reported" not reaching the code M1's fix sat next
to. **Fix:** `try: … except (OSError, RuntimeError)` around the guard call → `error: … cannot be
checked: …`, `return 2`; one test with a self-referencing symlink.

### L-B — A positive quantity that underflows becomes `0.0` with no issue
`src/bomreuse/normalize.py:170-182`. `not positive` is checked on the `Decimal`; the artifact
holds the float. `normalize_quantity("0," + "0"*400 + "1", "pcs")` → `value=0.0, unit="pcs",
issues=[]`, while `"0"` → `not positive`. Same family as M5 — an absurd input escaping "counted,
never silently lost" — and M5's fix guards the upper end only. **Fix:** compute the final float
once; `out of range` when it is `<= 0.0` or not finite. Could ride with #13 rather than hold this
PR.

### L-C — The implementation report is half-updated
`.claude/reports/ingest-normalize-entity-model-report.md:30,44,55`. The fix commits edited
deviations 1 and 2 but the counts are those of `3466df5`: "273 tests (suite: 301 → 574)",
"574 passed", `test_cli_normalize.py (12)`, "`--out` inside `--raw` refused (2)". At HEAD: 612
total; `test_model` 38, `test_ingest` 35, `test_normalize` 164, `test_cli_normalize` 17,
`test_pipeline_invariants` 57. Rule 1 is about numbers the code computed *now*. **Fix:** keep the
report as a dated snapshot and add a short "After review" addendum with the HEAD counts — or
refresh the figures. The PR body's "574 passed" is in the same state.

## Informational — not findings

- **Import scanner, adversarial spellings.** `import bomreuse` then `bomreuse.generate.x`,
  `sys.modules["bomreuse.generate"]` and `builtins.__import__` still pass the static test. Beyond
  what M3 asked; the runtime decoy test (M4) is the backstop for what a static check cannot see.
- **Guard and a symlinked sub-directory of raw.** With `raw/extlink -> ext` and `--out ext`, the
  artifact is written: `rglob` does not descend into symlinked directories. The tool never reads
  under `raw/` beyond its three named files, so no input is touched.
- **Decisions 27 and 28** both say the human chose, and 28 says the human authorized the AI to
  write the line. That cannot be verified from the repository: the human confirms it on merge.
- **Commits.** All 19 are conventional and reference `(#3)`; `ba81101` and `76b8518` each group
  several review findings, all of #3 — no commit mixes two issues.

## What is good

- **The guard asks the filesystem, not the string**: inode identity, the artifact resolved as well
  as its directory, a hard link caught, and it runs before anything is read.
- **Failing tests first, and they fail under mutation** — for H1 and for M3. The M4 decoy uses
  the committed ground truth and asserts the audit hook really recorded `bom.csv`.
- **`except` clauses stayed narrow**: `FileNotFoundError` before `OSError`, `ValueError` only
  around `int()`, and `allow_nan=False` left loud on purpose as a backstop rather than caught.
- **Deferrals are real**: #13 and #14 exist, with their ordering constraint in STATUS; the README
  limit and Decision 28 say what the code does.
- **The human call of M6 was made by the human** and logged, with the rejected alternative named.

## Next step

Mergeable as it stands. L-A and L-C are five-minute fixes worth taking before the merge
(`piv-fix-review-findings` on this file, then `piv-validate`); L-B can ride with #13. Then the
human reads the PR, confirms Decisions 27–28 and the `sub_assembly_designation` field (deviation 1,
"to be confirmed by the human"), and merges with a merge commit.
