# Implementation Report — `dataset_from_dict` validates leaf types, and a quantity that underflows (#13)

**Plan**: none — `piv-direct` issue, the fix is specified in #13 itself   **Branch**: `claude/issue-13-model-leaf-types`   **Status**: COMPLETE

## Summary

`dataset_from_dict` promised "or raise `ModelError`" and checked keys only. It now checks every
leaf as it reads it, and `load_dataset` turns `OSError` and `UnicodeDecodeError` into the same
error type, so #4 — the first stage that will read `out/normalized.json` — meets one exception
type and a field path, never a `TypeError`, a bare `ValueError`, or a value that was quietly
misread. Review 2's finding L-B rides along: a positive quantity too small for a float was
written as `0.0` with no issue, where `"0"` is refused; it is now `out of range`. The review
of PR #15 found four more ways out of the read path that were not a `ModelError`; they are closed
too, in the section at the end.

No behaviour of the pipeline on the committed dataset changes: `bomreuse normalize --raw data/raw`
still reports 696 lines, 160 components, 72 sub-assemblies, 12 suppliers, 0 issues, and the
artifact it writes loads back through the new checks.

## Commits

- `aa164ce` `fix: model — read the artifact's leaves, not only its keys (#13)` — `src/bomreuse/model.py`, `tests/test_model.py`
- `c7f1c18` `fix: normalize — a quantity that underflows to zero is counted, not read as zero (#13)` — `src/bomreuse/normalize.py`, `tests/test_normalize.py`
- `53e64ba` `fix: model — nothing but ModelError leaves the read path (#13)` — `src/bomreuse/model.py`, `tests/test_model.py` (review round 1, below)

## What changed

**`model.py`** — six leaf checkers, each raising `ModelError` naming the field's path:
`_str`, `_opt_str`, `_int`, `_opt_int`, `_opt_float`, `_str_tuple`. `_int` / `_opt_int` /
`_opt_float` refuse a boolean, which `isinstance(True, int)` would otherwise let through as `1`.
Every per-type reader now passes its leaves through them. `load_dataset` catches
`(OSError, UnicodeDecodeError)` — after `FileNotFoundError`, which keeps its own message.

**`normalize.py`** — `normalize_quantity` converts to a float once and then checks it: a value
that lands on `0.0` is `out of range`, the reason M5 gave the other end of the same range.
A quantity in `mm` can be a representable float and underflow only once converted to metres,
which is why the check is after the conversion rather than on the `Decimal`.

## Tests added (first round)

13 tests, each written before the code and failing against it (suite: 613 → 626, 1.5 s of a 30 s
budget, offline):

- `tests/test_model.py` — `test_a_leaf_of_the_wrong_type_is_refused_and_named` (10 cases: the six
  the issue lists, plus a non-string inside a string array, a boolean `row_number`, a non-string
  `quantity.unit` and a non-integer `seats.normalized`), and
  `test_a_path_that_is_not_readable_utf8_text_is_a_model_error` (a directory, a latin-1 file).
- `tests/test_normalize.py` — `test_a_quantity_too_small_for_a_float_is_counted_rather_than_read_as_zero`
  (2 cases: smaller than any float; a float until it is converted to metres).

## Deviations, with their reasons

1. **Six leaf checkers, not the four the issue names.** `_opt_str` and `_opt_int` were added
   because `Quantity.unit` is `str | None` and `RawInt.normalized` is `int | None`: the four
   named checkers cover no optional string and no optional integer, and leaving those two leaves
   unchecked would have kept the docstring half-true — which is the finding itself. Both have a
   current caller and a test.
2. **No `math.isfinite` guard after the unit conversion**, though L-B's proposed fix names one.
   No factor in `UNITS` is greater than 1 (`mm` and `g` are thousandths), so a finite `Decimal`
   cannot become `inf` when converted, and `parse_number` already refuses a number whose float is
   not finite (M5, tested). The guard would protect no reachable failure mode. If a unit with a
   factor above 1 is ever added, the check belongs back here.
3. **Four test cases beyond the seven the issue lists** (see above). Each covers a branch this
   change added; no branch of the new checkers is untested.
4. **No plan file.** #13 is a `piv-direct` issue in `.claude/STATUS.md`, and
   `.claude/PIV-PROCEDURE.md` allows the plan to be a few lines or skipped for those; the fix is
   specified field by field in the issue.
5. **`.claude/STATUS.md` updated in this run**, where `PIV-PROCEDURE.md` gives that to the human
   after the merge. Asked for explicitly in the work item.

## Decisions

None owed. No new dependency (`pyproject.toml` and `uv.lock` are untouched), no new
`NormalizationIssue` reason — `out of range` already exists and is already tested at the upper
end — and no threshold or floor was chosen.

## Validation

`/piv-validate`, run on `53e64ba`:

```
1. Tests .................... PASS      (633 tests, 1.5 s of a 30 s budget, offline)
2. Evaluation gate .......... N/A       (`bomreuse evaluate` does not exist before #5)
3. Invariants ............... PASS      (determinism, ground-truth isolation static + runtime
                                         + decoy, inputs read-only, artifact byte-identical
                                         across processes — all present, none removed)
4. Definition of done ....... PASS      (no dependency diff against main; CLAUDE.md module
                                         boundaries and README.md still true — no number in
                                         either changed)

VERDICT: PASS
```

Manual run: `uv run bomreuse normalize --raw data/raw --out <tmp>` exits 0 with the counts above,
and `model.load_dataset` reads the artifact it wrote back into tuples.

## Review round 1 of PR #15 — the read path was not sealed yet

The review reproduced four ways out of `load_dataset` / `dataset_from_dict` that were not a
`ModelError`, which made the sentence shipped to #4 — one exception type, whatever is wrong with
the artifact — false. Both findings land in the two functions this issue already names, and one
commit (`53e64ba`) closes both because the correction is the same three lines of `_opt_float`
plus one `except` clause.

**R1 — three exceptions still escaped.** Every point of the read path that *converts* rather than
*tests* could raise its own error:

- `_opt_float` accepted an integer (`isinstance(10**400, int)` is true) and then overflowed on
  `float(value)`. Both `float | None` leaves were affected — `lines[].quantity.value` and
  `lines[].unit_cost.normalized` — and both are now fed `10**400` by a test.
- `json.loads` raises a plain `ValueError` past CPython's 4300-digit integer limit, the same
  limit `normalize.parse_number` already catches for CSV input, and a `RecursionError` on a
  deeply nested file. Neither is a `JSONDecodeError`. One widened clause,
  `except (ValueError, RecursionError)`, covers all three cases; it stays *after* the
  `(OSError, UnicodeDecodeError)` clause, since `UnicodeDecodeError` is itself a `ValueError`
  and keeps its own "cannot be read" message.

The class is closed: `date.fromisoformat` is already wrapped, `path.read_text` is already
covered, and the other six primitives test without converting.

**R2 — `NaN` and `Infinity` were accepted at reading.** `json.loads` reads Python's dialect, so
the bare literals `NaN` / `Infinity` and an overflowing `1e400` all became a float the module's
own writer refuses (`render_dataset`, `allow_nan=False`). The reader handed back a dataset that
could not be written again, and a non-finite value has no marker a caller can test —
`normalized is None` is this module's only word for "could not be read". `math.isfinite` now
guards the same three lines, so `_raw_number` and `_quantity` both inherit it. `import math` is
stdlib: no dependency, so no `DECISIONS.md` line is owed.

7 tests, written first and all failing against `7feef5f`: two overflow rows in the leaf table,
`test_a_number_json_cannot_hold_is_refused_at_reading_too` (4 literals, fed as JSON *text*, since
the value only arises through the parser) and
`test_a_json_file_python_itself_refuses_to_parse_is_a_model_error`. Suite 626 → 633, 1.5 s.

### Deviations in this round

6. **R1 and R2 in one commit**, where the review lists them as two findings. They are one
   outcome — nothing but `ModelError` leaves the read path — and the two corrections overlap in
   the same three lines of `_opt_float`; splitting them would have produced a commit whose tests
   fail at their own HEAD, which this project's "test with the code" rule forbids.
7. **Suggestions R3 to R6 not implemented.** The review marks them non-blocking, and the accepted
   contract names the tests and checkers field by field and forbids re-planning. R6 (the same
   underflow still open on `unit_cost_eur` in `_Cells.number`) is the run's one accepted adjacent
   discovery and wants its own issue; R3 (a generic 80-leaf sweep test) and R4 (a parametrised
   check over `UNITS`) are guards on tomorrow, with no current defect. R5 (`_str_tuple` duplicates
   `_each(..., _str, ...)`) is not a deviation at all: the contract names `_str_tuple`.

## For the next stage (#4)

`load_dataset` and `dataset_from_dict` now raise `ModelError` and nothing else for any badly
shaped artifact — a missing file, a directory, another encoding, invalid JSON, a wrong
`schema_version`, an unknown or missing key, or a leaf of the wrong type. A stage that loads the
artifact needs one `except ModelError`, and the message already names the field. A number it
gets is finite: a leaf holding `NaN` or `Infinity` is refused at reading, as it already was at
writing.
