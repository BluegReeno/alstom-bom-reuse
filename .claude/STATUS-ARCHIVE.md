# STATUS ARCHIVE — alstom-bom-reuse

History moved out of `.claude/STATUS.md`, verbatim. Newest first. Each entry is the file as it
stood, headings included.

---

Archived 2026-09-21, after PR #19 merged:

# STATUS — alstom-bom-reuse

Last updated: 2026-09-21 — refocus, decisions settled, issues re-cut

## Where this stands

The dataset and its measurement apparatus are built and tested. **The half of the tool that
answers the client's question is not written**: `resolve`, `checks`, `notes`, `link`,
`evaluate`, `report` and the `run` entry point do not exist, and `signatures.py` is wired to
nothing. The CLI has two commands, `generate` and `normalize`, neither of which a client would
look at.

Two thirds of the source is the synthetic-data factory, which the brief asks for in one bullet.
That is the overrun, and it is closed: **the data layer is frozen** (CLAUDE.md, "How we work").

PR #15 (issue #13, the artifact's leaf types) was the last of that layer. It is merged.

## The plan — six issue-to-PR runs, in this order

| # | Issue | Leaves the tool… |
| --- | --- | --- |
| 1 | **#4** resolution, rule catalogue, `bomreuse run` | first end-to-end command |
| 2 | **#16** signatures wired, backtest predictions, stdout summary | **answering the client's question** |
| 3 | **#17** unit, supplier and cost conflicts | answering the second half of it |
| 4 | **#5** evaluate: the backtest vs two naive baselines | carrying its one value claim |
| 5 | **#6** notes: keyword fallback, one LLM backend, linking | flagging unsafe reuse |
| 6 | **#7** HTML report and a true README | presentable |

Cut order is the reverse. Whatever is not reached goes into the README's Known limits with its
reason — a normal outcome, not a failure. From #16 on, `bomreuse run` prints a readable summary,
so a demo never depends on the report having landed.

Each issue carries **Context / Scope / Out of scope / Acceptance criteria / Validation / If
blocked**, so an autonomous run needs no question answered. Procedure:
`.claude/RUN-PROCEDURE.md`. Validation: the `piv-validate` skill, every run, in full.

## Decisions settled on 2026-09-21

- `evaluate` scores the **three reuse classes only**, against both naive baselines. Resolution
  scoring and per-defect-type scoring are cut; inconsistency findings are counted, displayed
  and covered by the end-to-end test.
- The LLM layer is **one backend** (`gemma4:12b-mlx`) plus the FR/EN keyword fallback. No
  backend scoring, no latency table, no `docs/measurements/`.
- The four issues are re-cut into six, each sized for one PR.
- The report lands last, with the stdout summary as the demo's safety net.
- #13 is closed by PR #15, merged 2026-09-21. #14 and #18 are closed won't-do — both are
  inside the frozen layer, and #18 was the layer feeding itself: a review of a PR on it
  produced another issue on it. #18's Known-limits line is written; #14's is owed by #7.
- Plan documents and implementation reports are dropped: the issue is the plan, the PR
  description is the report. The review step stays, inside the run.

Recorded as `DECISIONS.md` 29, written on the human's explicit authorization — the one case
the repo's rule allows.

## Not code, and not started

The email and the 40-minute case narrative. The "something you've built" segment is done. If a
session produces working code and no story, the case still fails — reserve time for it.
