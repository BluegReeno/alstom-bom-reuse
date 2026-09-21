# Run procedure — one issue, start to merge

The checklist for every issue of this repo, from the refocus of 2026-09-21 on. It replaces the
three-conversation PIV loop: each issue is now executed as one autonomous `issue → PR` run.
A new session asked "what is the next step?" answers from this file and from
`.claude/STATUS.md`, not from memory.

## What the run is given

Everything it needs, and nothing it has to infer:

- the issue, which carries its own **Context / Scope / Out of scope / Acceptance criteria /
  Validation / If blocked** sections;
- `CLAUDE.md`, `CONTEXT.md`, `DECISIONS.md`, read in that order before any code;
- a branch of its own, `claude/issue-<n>-<slug>`, cut from `main`.

No plan file and no implementation report: the issue is the plan, the PR description is the
report. Deviations from the issue are listed in the PR description with their reason — a
documented deviation reads as intentional, an undocumented one is a review finding.

## The run

1. **Read** the issue and the three files above. Do not open the dataset layer
   (`generate.py`, `catalogue.py`, `dirt.py`, `spec.py`, `ground_truth.py`) unless the issue
   names it: it is frozen.
2. **Implement**, one commit per coherent step, each ending with `(#n)`, tests in the same
   commit, never two issues in one commit, no squash.
3. **Validate** — the `piv-validate` skill, in full, and the demo command the issue names. A
   check that did not run is not a check that passed.
4. **Review** the diff adversarially before opening the PR: what would a lead data engineer
   who knows this data object to? Fix it, or name it in the PR description.
5. **Open the PR** with the validation report in it, the deviations, and the
   `DECISIONS.md` wording it proposes but does not write.
6. **Human** — read, settle anything marked for the human, approve, merge (merge commit, no
   squash), update `.claude/STATUS.md`, delete the branch.

## If blocked

Stop and say so in the PR description. Do not widen the scope, do not decide for the human,
do not invent a threshold, a figure or a defect type. A genuinely undecided call is a stop.
An issue that turns out bigger than one PR is also a stop: land what is coherent, say what is
left, and let the human cut the next issue.

## What never moves

- The pipeline never reads the ground truth; `tests/test_pipeline_invariants.py` scans every
  new module by itself — never add a module to its `NOT_PIPELINE` list to make it pass.
- Inputs are read-only. Tests never call a model or the network.
- Every finding carries its source rows, a `rule_id` from the catalogue, and a confidence.
- Agents never write in `DECISIONS.md`: propose the wording, wait for the human.
- No number in the README, the report or a commit message that the code did not compute.
