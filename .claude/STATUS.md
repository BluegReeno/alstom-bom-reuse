# STATUS — alstom-bom-reuse

Last updated: 2026-09-20

## Current Focus
Planning done: 7 GitHub issues created, dependency graph fixed. Next: issue #1 — the dataset
spec, the spec loader and the reuse verdict rule (spike S1), before anything is generated.

## In Progress
- [ ] #1 Contract: dataset spec, spec loader and reuse verdict rule (spike S1)

## Done (current sprint)
- [x] Framing committed: rules, problem statement, data requirements, 16 decisions
- [x] `docs/PRD.md` — one page, assumptions marked
- [x] `docs/ARCHITECTURE.md` — 7 open calls settled, 2 spikes named — 2026-09-20
- [x] `DECISIONS.md` 19-20 — pydantic scope, R5 verdict meaning — 2026-09-20
- [x] 7 GitHub issues created, backlog renumbered — 2026-09-20

## Backlog
- [ ] #2 Synthetic dataset generator, planted defects and ground truth — `piv-full`
- [ ] #3 Ingest, normalize and the entity model — `piv-full`
- [ ] #4 Reference resolution, signatures and inconsistency checks — `piv-full`
- [ ] #5 Evaluation: one scorer, two predictors, and the naive baseline — `piv-full`
- [ ] #6 Note extraction: LLM adapter, keyword fallback and linking — `piv-direct`, after S2
- [ ] #7 HTML report, findings artifact and a true README — `piv-direct`

## Note
The build runs in slices across several sessions. This file carries state, not elapsed time.

Order of execution: #1 -> #2 -> #3 -> #4 -> #5, then #6 and #7 in parallel. Spike S2 (does the
local model return usable JSON) is throwaway, off the critical path, and can run at any time.
The cut order is the reverse: #7 first, then #6; #5 is never cut.
