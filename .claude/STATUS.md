# STATUS — alstom-bom-reuse

Last updated: 2026-09-21

## Current Focus
PR #24 (#6) merged — its four deviations settled as-is, DECISIONS 34–35 written. Next: PR #23 (#7) rebases on main, then its pre-merge check — see In Progress.

## In Progress
- [ ] PR #23 (#7 report, `claude/issue-7-report` @ 1625a2a, 4 commits) — open, branched before #6: must rebase on main now that #24 merged (README conflict; its body says one README sentence must turn affirmative once notes exist). Check it carries #14's Known-limits line.
- [ ] Pre-merge check of #23, done by the session: re-run `bomreuse evaluate` and `bomreuse run` on the branch and match every figure in README + PR body; list each deviation with pro / con / recommendation; re-run `uv run pytest` and `piv-validate`.
- [ ] After merge: STATUS.md, DECISIONS.md with the human's approval, `archon complete <branch>`, push.

## Done (current sprint)
- [x] #6 — notes: FR/EN keyword fallback, `gemma4:12b-mlx` adapter, link to canonical components, note-vs-BOM checks; PR #24 merged — 2026-09-21
- [x] PR #24's four deviations settled as-is (sixth artifact, flag on all three note kinds, three catalogue rules, ARCHITECTURE.md aligned); logged as DECISIONS 34–35 — 2026-09-21
- [x] #5 — `evaluate`: one scorer, three predictors (tool, exact reference, same name), counts beside every ratio; PR #22 merged — 2026-09-21
- [x] PR #22's four deviations settled: `--raw` default kept, baseline variant cleanup kept, the ordering test dropped (no floor), the ARCHITECTURE A3 and `piv-validate` alignments kept; logged as DECISIONS 31–33 — 2026-09-21
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
- [ ] Not code: the email and the 40-minute case narrative — reserve time for them
