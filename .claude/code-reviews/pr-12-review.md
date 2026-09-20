# Review — PR #12: ingest, normalize and the entity model (#3)

**Recommendation: REQUEST CHANGES** — one high issue, on the guard of a non-negotiable rule; the
rest is sound. Validation is green and the PR does what #3 asks. Reviewed at `3466df5`, in a fresh
context (deep pass by a clean-context sub-agent, every finding below re-run by the reviewing
session), against `CLAUDE.md`, the plan and the implementation report. The seven deviations listed
in the report are treated as decisions, not issues.

Posted as a comment: GitHub does not let the PR's author request changes on their own PR.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 6 |
| Low | 6 |

## Validation

| Check | Result |
| --- | --- |
| `uv run pytest` | PASS — 574 passed in 1.4 s of a 30 s budget, offline |
| `compileall` on `src`, `tests` | PASS |
| `uv run bomreuse normalize --raw data/raw --out <scratch>` | `696 / 160 / 72 / 12 / 0`, the figures of the PR body and the report |
| `data/`, `pyproject.toml`, `uv.lock` vs `origin/main` | untouched; working tree clean after the run |
| Evaluation gate | N/A — `evaluate` arrives with #5 |
| Invariants | Determinism, ground-truth isolation (static + runtime), inputs read-only: present and green. Traceable findings: missing, belongs to #4 |
| README / report figures | every number checked against a run: they match |

## High

### H1 — The `--out` inside `--raw` guard can be bypassed, and one bypass overwrites an input

`src/bomreuse/cli.py:86`. Both reproduced on a copy of `data/raw/`, on macOS:

- **Case.** `--raw t/raw --out t/RAW/sub` exits 0 and creates `t/raw/sub/normalized.json`.
  `Path.resolve()` does not canonicalize case on a case-insensitive filesystem, which is the
  filesystem this project is developed and demoed on.
- **Symlink.** With `out/normalized.json` already a symlink to `raw/bom.csv`, the run exits 0 and
  the sha256 of `bom.csv` changes. The guard resolves the directory, never the artifact path.

Rule 3 ("inputs are read-only") is non-negotiable, the guard is its only runtime enforcement, and
the read-only test only exercises the spelling the guard already handles.
**Fix:** resolve `out_dir / NORMALIZED_FILE` as well and refuse when it lands under raw; compare
the existing ancestors of `--out` with `os.path.samefile` (or `st_dev`/`st_ino`) rather than by
string. Failing tests first, one per bypass. `generate.py:695` uses the same pattern — out of
this PR's scope, worth an issue.

## Medium

### M1 — Ordinary usage errors print a traceback
`src/bomreuse/ingest.py:82-87`, `src/bomreuse/cli.py:89-95`. Reproduced: `--raw data/raw/bom.csv`
→ `NotADirectoryError`; `--out <existing file>` → `FileExistsError`. `_read_rows` catches
`FileNotFoundError`, `UnicodeDecodeError` and `csv.Error` only, and `dump_dataset` sits outside any
`try`. **Fix:** catch `OSError` in `_read_rows` → `IngestError`; wrap the write, print `error: …`,
return 1.

### M2 — `dataset_from_dict` promises "or raise `ModelError`" and checks keys only
`src/bomreuse/model.py:281-425`. `raw_names: null` → `TypeError`; `quantity.value: "abc"` → bare
`ValueError`; `supplier.id: 5`, `row_number: "x"`, `quantity.value: true` (→ `1.0`),
`raw_names: "abc"` (→ `('a','b','c')`) are accepted silently. The artifact is machine-written and
`schema_version` guards staleness, so this is not high — but #4 and #5 will read it on the
strength of that docstring. **Fix:** four small leaf checkers (`_str`, `_int` refusing `bool`,
`_opt_float`, `_str_tuple`) raising `ModelError(where)`; catch `OSError`/`UnicodeDecodeError` in
`load_dataset`.

### M3 — The "no pipeline module imports the generator side" test misses relative imports
`tests/test_pipeline_invariants.py:154-163`. `from .generate import generate` and
`from . import catalogue` yield an empty set: the walker requires
`node.module.split(".")[0] == "bomreuse"` and ignores `node.level`. **Fix:** handle
`node.level > 0`; flag `importlib` / `__import__` in pipeline modules; `rglob` rather than `glob`.

### M4 — The runtime isolation test proves the pipeline works without a ground truth, not that it ignores one
`tests/test_pipeline_invariants.py`. The static scanner is, by its own docstring, limited to
spellings it can see (`'data/ground' + '_truth'` passes). That is an honest limit for a static
check; the runtime test is what should cover it and does not. **Fix:** a differential test — run
once with a decoy `ground_truth/ground_truth.json` beside `raw/`, once without, assert a
byte-identical artifact.

### M5 — Two inputs escape "counted, never silently lost"
`src/bomreuse/normalize.py:125` — a digit string over 4300 characters in `seats` raises
`ValueError` out of `normalize()` (Python's int-conversion limit). `normalize.py:171,240` — a
400-digit quantity or cost becomes `inf` with no issue, and the artifact then holds a bare
`Infinity`, which is not JSON. Absurd inputs, both reproduced, both two-line fixes: catch the
`ValueError` → `"not an integer"`; `math.isfinite` → `"out of range"`, plus `allow_nan=False` in
`json.dumps` as a backstop.

### M6 — A sub-assembly entity is created for an empty or unknown variant
`src/bomreuse/normalize.py:296,341-359`. `variant_id=""` yields `SubAssembly(id=':SA1',
variant_id='')`; `variant_id="Q"` yields `'Q:SA1'` for a variant that is not in `variants`. The
issue is recorded, but deviation 2 states "no entity is created for an empty key" and only covers
references and suppliers; no test exercises the variant half of the key. #4 compares sub-assemblies
across variants and would meet a ghost one. **Fix:** `parent_id = ""` when the variant is empty or
unknown — or keep the behaviour, say so in the report, and test it. A human call.

## Low

- **L1** `normalize.py:96` — `reference_key` does not NFC-normalize while `text_key` does:
  `reference_key("é") == "E"`, `reference_key("é") == "É"`, against its own docstring.
- **L2** `model.py:184-185` and report deviation 1 overstate: "every column of the raw row is
  carried" / "all ten columns" — the raw `variant_id` is not carried (admitted further down, under
  "Issues encountered"). Correct the two sentences, or carry it as a `RawText`.
- **L3** `normalize.py:107-116` — `1,500` and `1.500` are read as `1.5`. Consistent with
  Decision 24 (comma is the decimal mark) and no such value exists in the committed data, but
  `1.234,56` is refused as "guessing would be a repair" while `1,234` is guessed. Belongs in the
  README's known limits.
- **L4** `ingest.py:72` — a non-strict `csv.reader` rewrites malformed quoting (`"Premium" seat` →
  `Premium seat`) against "exactly as they are"; `strict=True` would turn it into an `IngestError`.
- **L5** `tests/test_normalize.py:64,275` — two `# type: ignore`, one hiding an untyped parameter;
  the project rule is type hints everywhere.
- **L6** Commits: all twelve are conventional and reference `#3`. `3466df5` (the generic PIV
  procedure) is process documentation rather than #3's scope — tolerable, better in its own PR.
  `402a655` adds `DECISIONS.md` line 27: its last column says the human validated the wording and
  asked for the line; the human confirms that on merge.

## What is good

- **Parsers check the shape before converting.** ASCII-only regexes refuse full-width digits,
  signs, exponents and `NaN`; `1.234,56` is refused rather than guessed; `parse_date` blocks
  `20190314` and week dates that `fromisoformat` alone would take.
- **Exact quantities.** Decimal arithmetic, one float conversion at the end: `36000 mm == 36 m ==
  36,0 m` holds with `==`, and the artifact is byte-identical across two `PYTHONHASHSEED` values.
- **The scanner tests itself** — 15 must-flag and 5 must-pass cases — and the PR body reports a
  mutation check of the static test. `evaluate.py` is pre-listed so the rule is not widened later.
- **Ingest's strictness is argued, not assumed**: no `DictReader`, no `utf-8-sig`, no
  `skipinitialspace`, each with its reason; a line-for-line re-join test on the committed files;
  columns cross-checked against the generator without importing it.
- **Tests and measurement stay apart.** Family tests are driven by `load_spec()`; the
  must-not-merge key collision is asserted as an accepted cost (Decision 27), not hidden.
- **The report is honest**: seven deviations, each with its reason, including the plan's own
  inaccurate `asdict` gotcha.

## Next step

`piv-fix-review-findings` on this file: H1 before merge; M1, M5 and M6 are a few lines each and
worth taking in the same pass; M2–M4 can be fixed here or logged as issues — the human decides.
Then re-run `piv-validate`.
