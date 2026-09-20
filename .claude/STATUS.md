# STATUS — alstom-bom-reuse

Last updated: 2026-09-20

## Current Focus
The first pipeline stage exists: `bomreuse normalize` reads `data/raw/` and writes `out/normalized.json`.
Next: issue #5, first slice — the scorer and the two naive baselines, before #4.

## In Progress
- (nothing)

## Done (current sprint)
- [x] Framing committed: rules, problem statement, data requirements, 16 decisions
- [x] `docs/PRD.md` — one page, assumptions marked
- [x] `docs/ARCHITECTURE.md` — 7 open calls settled, 2 spikes named — 2026-09-20
- [x] `DECISIONS.md` 19-20 — pydantic scope, R5 verdict meaning — 2026-09-20
- [x] 7 GitHub issues created, backlog renumbered — 2026-09-20
- [x] #1 Contract: dataset spec, spec loader, verdict rule; spike S1 run — 2026-09-20
- [x] #2 Synthetic dataset generator, planted defects and ground truth — 2026-09-20
- [x] #3 Ingest, normalize and the entity model; isolation and read-only invariants — 2026-09-20

## Backlog
- [ ] #4 Reference resolution, signatures and inconsistency checks — `piv-full`
- [ ] #5 Evaluation: one scorer, two predictors, and the naive baseline — `piv-full`
- [ ] #6 Note extraction: LLM adapter, keyword fallback and linking — `piv-direct`, after S2
- [ ] #7 HTML report, findings artifact and a true README — `piv-direct`

## Note
Project review, 2026-09-20: #4 now builds signatures on every merged group (`auto` and `review`),
Decision 26. #5 follows
Decision 25, adds a same-name baseline and lands its scorer before #4. Five trap notes replace
bland ones in `catalogue.py` (N022, N026, N028 state nothing; N027, N039 state a fact in words of
their own): `bom.csv` and the ground truth are byte-identical, only `notes.csv` moved. #6's keyword
lexicon must be written from the brief's patterns, not from `notes.csv`, or the traps measure nothing.

The build runs in slices across several sessions. This file carries state, not elapsed time.

Spike S1 result: of eight story cases, two came out `specific` where the story says `reusable`,
and the part counts changed rather than the threshold (DECISIONS.md 17) — the seating module's
armrests belong to the seat, the bike module's fixing kit follows the rail.

Handover from #3 to #4 and #5: `normalize.reference_key` is the key — #4 inherits it and never
recomputes one. A `Component` is a candidate group (one per key); the three must-not-merge pairs
share a key on purpose (Decision 27) and carry two designations each, which is what #4's `reject`
reads. #5's baselines read `RawBomRow` (ingested rows), never `BomLine`. `evaluate.py` is already
exempt from the AST isolation test. Details: `.claude/reports/ingest-normalize-entity-model-report.md`.

Order of execution: #1 -> #2 -> #3 -> #5 first slice (scorer + two baselines) -> #4 -> #5 second
slice, then #6 and #7 in parallel. Spike S2 (does the
local model return usable JSON) is throwaway, off the critical path, and can run at any time.
The cut order is the reverse: #7 first, then #6; #5 is never cut.
