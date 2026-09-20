# PIV procedure — one issue, start to merge

The checklist to follow for every issue of this repo. For the human and for the agent: a new
session that is asked "what is the next step?" answers from this file and from
`.claude/STATUS.md`, not from memory.

**The rule behind the clears.** Start a new conversation whenever a file carries everything the
next step needs; stay in the same one when the next step needs what this one learned and no file
holds it. Three clears per issue, one prime. Where each rule comes from (the PIV video, a
skill's `SKILL.md`, or an inference) is recorded in `prep/procedure.md`, which is local.

```
conversation 1   prime-codebase -> piv-plan-implementation
conversation 2   piv-implement <plan> -> own review -> piv-create-pr
conversation 3   piv-review-pr <n> ( -> piv-fix-review-findings )
human            approve, merge, STATUS
```

## 0. Pick the issue

- [ ] Next issue and its loop (`piv-full` or `piv-direct`) come from `.claude/STATUS.md`, order
      of execution included. Check it against `gh issue list` before trusting it.
- [ ] Cut the branch **before planning**, so the plan commit rides into the PR:
      `claude/issue-<n>-<slug>` (a worktree is fine).

## Conversation 1 — prime, then plan (same conversation)

- [ ] `/skills:prime-codebase`, pointed at the issue.
- [ ] `/skills:piv-plan-implementation <issue>` — answer its gate questions.
- [ ] A gate answer that is a **human decision** goes into `DECISIONS.md`: the human words it,
      the agent never writes it on its own, and reminds the human when one is owed.
- [ ] Plan committed on the branch: `.claude/plans/<slug>.md`, `docs: plan — … (#n)`.
- [ ] **Clear.**

`piv-direct` issues (#6, #7): the prime stays; the plan may be a few lines or skipped. Everything
from conversation 2 on is unchanged.

## Conversation 2 — implement, review, open the PR (no prime)

- [ ] `/skills:piv-implement .claude/plans/<slug>.md` — the plan is the only context it needs.
      One commit per task, each ending with `(#n)`, tests in the same commit, never two issues
      in one commit, no squash.
- [ ] Each task's own VALIDATE passes before the next task starts.
- [ ] `/piv-validate` (this project's own skill): tests under 30 s and offline, the evaluation
      gate once #5 exists, the named invariants, no new dependency without a `DECISIONS.md` line,
      `CLAUDE.md` and `README.md` still true — no number the code did not compute.
- [ ] Report written and committed: `.claude/reports/<slug>-report.md`. **Deviations from the
      plan are listed with their reason** — the PR reviewer treats a documented deviation as
      intentional and an undocumented one as a finding.
- [ ] `STATUS.md`, `CONTEXT.md` status line, `CLAUDE.md` module boundaries updated in the same
      session.
- [ ] Your own read of the diff, and a manual run of the command.
- [ ] `/skills:piv-create-pr` — **same conversation, no clear, no prime.** It needs a clean tree
      (an untracked file stops it; `prep/` and `out/` are ignored), commits ahead of `main`, and
      no existing PR. `piv-commit` is only needed if something is still uncommitted.
- [ ] **Clear.**

## Conversation 3 — review the PR (no prime)

- [ ] `/skills:piv-review-pr <number>` — **never in the conversation that wrote the code**: it
      rationalizes instead of scrutinizing. The skill loads the rules, the plan and the report
      itself. Its review lands in `.claude/code-reviews/pr-<n>-review.md` and on the PR.
- [ ] Findings: `/skills:piv-fix-review-findings`, one at a time with its test, then
      `/piv-validate` again, commit, push.

## Human — approve and merge

- [ ] Read the PR, settle anything marked "to be confirmed by the human", approve, merge
      (merge commit, no squash: the history is a deliverable).
- [ ] After the merge: `.claude/STATUS.md` — the issue under Done with its date, Current Focus on
      the next one, the handover note rewritten for it. Remove stale lines against their source
      (`gh issue list`), not against the file.
- [ ] Delete the branch and the worktree — after moving out anything kept in its `prep/`.
- [ ] **Clear**, and back to step 0.

## What never moves

- The evaluation is never cut; the cut order is report polish, then LLM extras, then the pipeline.
- The pipeline never reads the ground truth; `tests/test_pipeline_invariants.py` scans every new
  module by itself — do not add a module to its `NOT_PIPELINE` list to make it pass.
- Tests never call a model or the network.
