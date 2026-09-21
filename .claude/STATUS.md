# STATUS — alstom-bom-reuse

Last updated: 2026-09-21

## Current Focus
#6 and #7 delivered as PRs #24 and #23 (both self-reported PASS), runs cancelled mid-review on quota. Next: pre-merge check of #24, merge, then #23 rebases on main — see In Progress.

## In Progress
- [ ] PR #24 (#6 notes, `claude/issue-6-notes` @ 0f54f2a, 8 commits) — open, body complete (validation PASS 977 tests, deviations listed, DECISIONS wording proposed). Run `c36c7de3…` cancelled 2026-09-21 during its review/fix phase; worktree clean. Not yet checked by the human session.
- [ ] PR #23 (#7 report, `claude/issue-7-report` @ 1625a2a, 4 commits) — open, body complete (validation PASS 891 tests, deviations listed, notes "For the human"). Run `0c92d06f…` cancelled the same way. Branched before #6: must rebase on main after #24 merges (README conflict; its body says one README sentence must turn affirmative once notes exist). Check it carries #14's Known-limits line.
- [ ] Pre-merge check, per PR, done by the session, not the run: re-run `bomreuse evaluate` and `bomreuse run` and match every figure in README + PR body; list each deviation with pro / con / recommendation; re-run `uv run pytest` and `piv-validate` on the branch. Do not `archon workflow resume` — the PRs exist, the remaining work is review.
- [ ] After each merge: STATUS.md, DECISIONS.md with the human's approval, `archon complete <branch>`, push.

## Done (current sprint)
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
