# Implementation Report — `dataset_from_dict` validates leaf types, and a quantity that underflows (#13)

**Plan**: none — `piv-direct` issue, the fix is specified in #13 itself   **Branch**: `claude/issue-13-model-leaf-types`   **Status**: COMPLETE

## Summary

`dataset_from_dict` promised "or raise `ModelError`" and checked keys only. It now checks every
leaf as it reads it, and `load_dataset` turns `OSError` and `UnicodeDecodeError` into the same
error type, so #4 — the first stage that will read `out/normalized.json` — meets one exception
type and a field path, never a `TypeError`, a bare `ValueError`, or a value that was quietly
misread. Review 2's finding L-B rides along: a positive quantity too small for a float was
written as `0.0` with no issue, where `"0"` is refused; it is now `out of range`.

No behaviour of the pipeline on the committed dataset changes: `bomreuse normalize --raw data/raw`
still reports 696 lines, 160 components, 72 sub-assemblies, 12 suppliers, 0 issues, and the
artifact it writes loads back through the new checks.

## Commits

- `aa164ce` `fix: model — read the artifact's leaves, not only its keys (#13)` — `src/bomreuse/model.py`, `tests/test_model.py`
- `c7f1c18` `fix: normalize — a quantity that underflows to zero is counted, not read as zero (#13)` — `src/bomreuse/normalize.py`, `tests/test_normalize.py`

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

## Tests added

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

`/piv-validate`, run on `c7f1c18`:

```
1. Tests .................... PASS      (626 tests, 1.5 s of a 30 s budget, offline)
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

## For the next stage (#4)

`load_dataset` and `dataset_from_dict` now raise `ModelError` and nothing else for any badly
shaped artifact — a missing file, a directory, another encoding, invalid JSON, a wrong
`schema_version`, an unknown or missing key, or a leaf of the wrong type. A stage that loads the
artifact needs one `except ModelError`, and the message already names the field.
