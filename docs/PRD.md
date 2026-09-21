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
  classify each of its sub-assemblies, and measure the tool against two naive searches on the
  same data — exact reference, and same name. The gap is the only value claim made.
- **G4 — On-prem path.** The pipeline runs offline end to end on the keyword fallback; the LLM
  reads notes only, through one backend that runs on a 16 GB laptop. Neither backend is scored:
  the on-prem argument is the adapter interface and the offline run, not a benchmark.

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
| R8 | `evaluate`: precision and recall on the three reuse classes of the newest variant, for the tool and for the two naive baselines, counts next to every ratio | CLAUDE.md, Dec. 5 |
| R9 | Static HTML report: sponsor summary first, traceable detail after | CLAUDE.md |
| R10 | One CLI entry point; full pipeline runs with no network | CLAUDE.md, Dec. 5 |
| R11 | Every finding carries source rows, the rule that produced it, and a confidence | CLAUDE.md |
| R12 | Inputs read-only; the pipeline never reads the ground truth — both enforced by tests | CLAUDE.md, Dec. 8 |

## 6. Success criteria

1. `uv run bomreuse evaluate` prints precision and recall on the three reuse classes for the
   default dataset, and the same figures for the two naive baselines of [A3], with counts next
   to every ratio. **The gap between the tool and the baselines is the only value claim this
   build makes** (Dec. 3, Dec. 17).
2. Every planted *reused* case and every *re-designed in the newest variant* case is found by
   the end-to-end test, on a small dataset generated with a test seed.
3. The README's Results section contains only numbers `evaluate` computed. (Dec. 3.)
4. `uv run pytest` green in under 30 s, offline.

The reuse threshold is fixed in the dataset spec before the data is generated, and is never
tuned against these scores (Dec. 17). There are no regression floors in this build: `evaluate`
prints its figures and the README quotes them; floors are a pilot-scale practice (CLAUDE.md).

## 7. Constraints

Scope is small on purpose. The build runs as six autonomous issue-to-PR runs, in the order
CLAUDE.md names; the cut order is its reverse, and what is not reached goes into the README's
Known limits with its reason. Python 3.12 + `uv`, few pinned dependencies. Offline
by default; Ollama at `http://localhost:11434`, one backend wired — `gemma4:12b-mlx`, the on-prem
path. `glm-5.3-flash:cloud` (Dec. 6) may be run by hand; its figures, if any, go in the README
labelled as a manual measurement (Dec. 29). Tests never call a live model or the network.
Priority order, and it is the cut order: the client's question first (resolution, then signatures), then the
inconsistencies, then the value claim, then the notes, then the report.

## 8. Assumptions

- **[A1]** The BOM is two levels: variant → sub-assembly → component. Sub-assembly is the unit
  of reuse and the unit of comparison; nested sub-assemblies are out of scope for this build.
- **[A2]** A sub-assembly signature is the multiset of (canonical component, normalized
  quantity, SI unit) it contains, built on every merged component group — a supplier, cost or
  unit conflict is a finding, not a doubt about what the part is (Dec. 26); *reusable* means a signature distance within the threshold
  fixed by the dataset spec, written before the data is generated (Dec. 17). The threshold is a
  contract `generate.py` and `signatures.py` both read; `evaluate` reports against it and never
  moves it.
- **[A3]** Two naive baselines, both reading raw rows only. *Exact reference*: a sub-assembly
  of the newest variant counts as "already exists" only if its raw reference string matches an
  older variant's raw reference exactly. *Same name*: it counts as "already exists" if its raw
  designation, compared case- and whitespace-insensitively, equals an older variant's — the
  search a data engineer would try first, which finds a namesake almost everywhere and cannot
  tell identical from changed from re-designed.
- **[A4]** `evaluate` scores the three reuse classes and nothing else (settled 2026-09-21).
  Inconsistency findings — duplicate reference, unit, supplier and cost conflicts, note-vs-BOM
  contradictions — are counted and displayed with their evidence, and the end-to-end test
  asserts the planted ones are found. Scoring them per defect type, and scoring resolution as a
  clustering problem, are cut: they measure the dataset generator as much as the tool, and the
  value claim does not rest on them.
- **[A5]** Confidence is a 0–1 score per finding, produced by the rule that emitted it; it
  is reported, not thresholded, in this build.
- **[A6]** The report is a single self-contained HTML file written to `out/`, plus findings as
  JSON for the reviewer.
- **[A7]** One backtest target only — the newest variant (C). Leave-one-out across all variants
  is a later idea, out of scope here.
