# PRD — alstom-bom-reuse

One page. Foundation: `README.md` (problem, scope, user, data), `CONTEXT.md` (pilot, worked
example), `DECISIONS.md` 13–16. Anything not supported by those files is marked **[A]**
(assumption) and is a candidate for a `DECISIONS.md` line if it holds.

## 1. Problem

For a given train-car variant, engineers cannot tell which of its sub-assemblies already exist
in the other variants. Duplicated references with typos, mixed units and FR/EN notes that
contradict the BOM make the data unreadable, so existing sub-assemblies are re-designed and
re-costed. (Decision 13.)

## 2. Users

| | Who | What they need from the tool |
| --- | --- | --- |
| Primary | Design engineer preparing a tender | For each sub-assembly of the variant at hand: does an equivalent exist, and is it safe to reuse |
| Reader | Bruno Maréchal, sponsor | The value story at the top of the report: what the tool found that an exact-reference search missed |
| Reviewer | Thomas Lindqvist, lead data engineer | Evidence per finding, and code he can maintain |

## 3. Goals

- **G1 — Catalogue.** Deduplicated sub-assemblies across all variants, each classified *reused*
  (identical), *reusable* (near-identical, with the exact diff) or *specific*, with where used.
- **G2 — Inconsistencies.** Duplicate references, unit conflicts, supplier and cost conflicts,
  notes contradicting the BOM — each traceable to its source rows and rule.
- **G3 — Backtest.** The newest variant plays the new tender: given only the older variants,
  classify each of its sub-assemblies, and measure the tool against a naive exact-reference
  search on the same data. The gap is the only value claim made.
- **G4 — On-prem path.** The pipeline runs offline end to end; the LLM reads notes only, and a
  cloud and a local model are scored on the same ground truth with latency per note.

## 4. Non-goals

Decomposing a new design for later reuse. Writing back to the PLM (propose only). Requirement
or spec matching — the tool matches sub-assemblies, not requirements. Time or money saved: the
client defines it. Web UI, graph DB, real PLM connector, mandatory LLM, generalizing the code.

## 5. Requirements

| # | Requirement | Ground |
| --- | --- | --- |
| R1 | Generate the synthetic dataset from a fixed seed: 4–6 intermediate-car variants (A standard, B bike car, C newest bike car), ~100–250 BOM lines each, ~40 FR/EN notes, costs and suppliers | Dec. 1, 14, 15 |
| R2 | Plant, and record in a ground truth: hidden reuse (new or typo'd reference), near-reuse (1–3 parts differing), genuinely new sub-assemblies, unsafe reuse (matched sub-assembly holding a part a note declares obsolete) | CONTEXT, Dec. 14 |
| R3 | Ingest raw CSVs unchanged; normalize ids, units to SI, decimal commas and text, keeping raw values alongside | CLAUDE.md |
| R4 | Entity model where a BOM line is an n-ary relation (parent, child, quantity, unit, variant) | CLAUDE.md |
| R5 | Resolve duplicate references to a canonical component, with an *auto / review / reject* verdict | CLAUDE.md |
| R6 | Signature per sub-assembly; equal signatures → *reused*, near-equal → *reusable* + diff | CLAUDE.md |
| R7 | Extract structured facts from notes (replacement, obsolescence, restriction, referenced part) with the source note cited; LLM adapter + keyword fallback, schema-validated, invalid output logged and counted | CLAUDE.md, Dec. 7 |
| R8 | `evaluate`: precision and recall per defect type against the ground truth, plus the naive baseline, plus both models' scores and latency | CLAUDE.md, Dec. 5, 6 |
| R9 | Static HTML report: sponsor summary first, traceable detail after | CLAUDE.md |
| R10 | One CLI entry point; full pipeline runs with no network | CLAUDE.md, Dec. 5 |
| R11 | Every finding carries source rows, the rule that produced it, and a confidence | CLAUDE.md |
| R12 | Inputs read-only; the pipeline never reads the ground truth — both enforced by tests | CLAUDE.md, Dec. 8 |

## 6. Success criteria

1. `uv run bomreuse evaluate` prints precision and recall per defect type on the default
   dataset, and the same figures for the naive exact-reference baseline. **The gap between the
   two is the only value claim this build makes** (Dec. 3, Dec. 17).
2. Every planted *reused* case and every *re-designed in the newest variant* case is found by
   the end-to-end test, on a small dataset generated with a test seed.
3. The README's Results section contains only numbers `evaluate` computed. (Dec. 3.)
4. `uv run pytest` green in under 30 s, offline.

The reuse threshold is fixed in the dataset spec before the data is generated, and is never
tuned against these scores (Dec. 17). Regression floors are a different thing: they are written
into `DECISIONS.md` from the first real measurement, per CLAUDE.md.

## 7. Constraints

Scope is small on purpose, and the build runs in slices across several sessions: elapsed time
is not a constraint the tool is judged on. Python 3.12 + `uv`, few pinned dependencies. Offline
by default; Ollama at `http://localhost:11434` with `glm-5.3-flash:cloud` and `gemma4:12b-mlx`
(Dec. 6). Tests never call a live model or the network. Priority order, and it is the cut
order: the evaluation first and never cut, then the pipeline it scores, then LLM extras, then
report polish.

## 8. Assumptions

- **[A1]** The BOM is two levels: variant → sub-assembly → component. Sub-assembly is the unit
  of reuse and the unit of comparison; nested sub-assemblies are out of scope for this build.
- **[A2]** A sub-assembly signature is the multiset of (canonical component, normalized
  quantity, SI unit) it contains; *reusable* means a signature distance within the threshold
  fixed by the dataset spec, written before the data is generated (Dec. 17). The threshold is a
  contract `generate.py` and `signatures.py` both read; `evaluate` reports against it and never
  moves it.
- **[A3]** The naive baseline is: a sub-assembly of the newest variant counts as "already
  exists" only if its raw reference string matches an older variant's raw reference exactly.
- **[A4]** Defect types scored separately by `evaluate`: duplicate reference, unit conflict,
  supplier conflict, cost conflict, note-vs-BOM contradiction, and the three reuse classes.
- **[A5]** Confidence is a 0–1 score per finding, produced by the rule that emitted it; it
  is reported, not thresholded, in this build.
- **[A6]** The report is a single self-contained HTML file written to `out/`, plus findings as
  JSON for the reviewer.
- **[A7]** One backtest target only — the newest variant (C). Leave-one-out across all variants
  is a later idea, out of scope here.
