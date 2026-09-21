# STATUS — alstom-bom-reuse

Last updated: 2026-09-22

## Current Focus
Build complete for the case: code, report and README done, final review applied. Nothing in progress.

## In Progress

## Done (current sprint)
- [x] README: `Maintaining it` section — where the thresholds and rules live, how to add a check, the tests that hold the line; linked from the deck's maintain slide; test count corrected to 1006; follow-up to #7 — 2026-09-22
- [x] Notes prompt: the answer's shape spelled out (an Ollama cloud model ignores `format`), empty list, replacement direction and words-are-not-references rules; schema field descriptions; manual measurement of keyword vs `gemma4:12b-mlx` vs `glm-5.3-flash:cloud` in the README, labelled as one; follow-up to #6 — 2026-09-21
- [x] README trimmed from 649 to 528 lines: How to run said once, Known limits kept to what limits the tool, the N031 stdout excerpt corrected to what `run` prints; follow-up to #7 — 2026-09-21
- [x] #26 — `model.py` split by a pure move: the types stay (565 lines), the JSON round-trip and the artifact names go to `artifacts.py` (615); artifacts, stdout and `evaluate` byte-identical to `main` — 2026-09-21
- [x] Docs pass: `docs/ARCHITECTURE.md`, `CLAUDE.md`, `piv-validate` and three docstrings aligned with the refocus (DECISIONS 29) — 2026-09-21
- [x] Final review before delivery: the HTML report flags the parts a note speaks against, by the rule stdout uses (`checks.flagged_parts`, DECISIONS 34); README excerpt and Known limits corrected; lint clean — 2026-09-21
- [x] README: status line set to scouting prototype, What's next section added — 2026-09-21
- [x] README: the entity model and the bike module followed through (two Mermaid diagrams), N013's shape added to Known limits; PR #25 merged, follow-up to #7 — 2026-09-21
- [x] #7 — the static HTML report written by `bomreuse run`, README complete with Known limits; PR #23 merged — 2026-09-21
- [x] PR #23's rebase deviations settled as-is: the report fixture runs the notes stage like the run it is compared against, README and PR-body figures recomputed (66 findings, 7 artifacts, 999 tests), the stdout flag stays as DECISIONS 34 settled it; logged as DECISIONS 36 — 2026-09-21
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
- [ ] `data/dataset_spec.toml`: two comments still speak of a measured resolution shortfall (cut by DECISIONS 29); left untouched so the contract's history stays the one Decision 17 points at
- [ ] Read each artifact once in `cli._run`
