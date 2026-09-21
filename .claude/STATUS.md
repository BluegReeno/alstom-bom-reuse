# STATUS — alstom-bom-reuse

Last updated: 2026-09-21

## Current Focus
#5 merged (PR #22): tool 14/15, same name 9/15, exact reference 6/15. Next: #6 ‖ #7, per `.claude/RUN-PROCEDURE.md`.
#7 carries two notes from PR #21: count conflicts from `checks.*`, and the strict `[check]` lead.

## In Progress
- (nothing — no run underway)

## Done (current sprint)
- [x] #5 — `evaluate`: one scorer, three predictors (tool, exact reference, same name), counts beside every ratio; PR #22 merged — 2026-09-21
- [x] PR #22's four deviations settled: `--raw` default kept, baseline variant cleanup kept, the ordering test dropped (no floor), the ARCHITECTURE A3 and `piv-validate` alignments kept — 2026-09-21
- [x] #17 — unit, supplier and cost checks on canonical components, inconsistencies block and `[check]` flag in `bomreuse run`; PR #21 merged — 2026-09-21
- [x] PR #21's two calls settled as-is (two rules on one fact; component-wide flag), both carried to #7 as comments — 2026-09-21
- [x] DECISIONS 5 and 6 amended — one LLM backend (`gemma4:12b-mlx`), the cloud comparison cut by #29 — 2026-09-21
- [x] #16 — signatures wired, backtest predictions, stdout summary; PR #20 merged — 2026-09-21
- [x] DECISIONS 30 — `specific` against `new` is a one-way correctness relation in `evaluate` — 2026-09-21
- [x] Refocus: data layer frozen, six issue-to-PR runs, `evaluate` scores the reuse classes only (`DECISIONS.md` 29) — 2026-09-21
- [x] #13 — the artifact's leaf types, PR #15 merged; #14 and #18 closed won't-do — 2026-09-21
- [x] #4 — resolution, rule catalogue, `bomreuse run`, PR #19 merged — 2026-09-21
- [x] PR #19's discoveries: the artifact-set seam folded into #16, the split-part conflicts into #17 — 2026-09-21
- [x] `docs/ARCHITECTURE.md`, `docs/PRD.md`, `README.md` aligned with the refocus — 2026-09-21

## Backlog
- [ ] DECISIONS 31–32 to write (human): `evaluate --raw` default; the baselines' variant-cell cleanup
- [ ] #6 notes: keyword fallback, one LLM backend, linking
- [ ] #7 HTML report and a true README — owes #14's Known-limits line
- [ ] Not code: the email and the 40-minute case narrative — reserve time for them
