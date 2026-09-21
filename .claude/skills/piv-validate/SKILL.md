---
name: piv-validate
description: Runs this project's real validation suite — pytest, the evaluation gate, and the non-negotiable invariants — then reports one PASS/FAIL verdict. Use before committing, before opening a PR, or after finishing an issue, to confirm the definition of done holds.
---

# Validate — alstom-bom-reuse

Run every check this project actually has and report a single PASS/FAIL verdict.

This is the project's own checker, not the generic template: the commands below are the ones
`CLAUDE.md` and the issues' definition of done name. Keep it true — if a command changes, change
it here in the same commit.

Run the checks in order. **Keep going after a failure** so the report covers everything, and
capture the output of any command that fails.

---

## Gate 0 — What exists yet

The toolchain landed with issue #1 and the pipeline arrives one stage at a time. A command that
does not exist yet is `N/A`, never PASS: a check that did not run is not a check that passed.
Say which issue is due to create it.

---

## 1. Tests

```bash
uv run pytest
```

**Expected:** all tests pass, offline, **and the whole suite stays under 30 s** so it can be run
live. Time it and say so:

```bash
time uv run pytest
```

If the suite creeps past 30 s, that is a FAIL even when every test is green — `CLAUDE.md` makes
the budget part of the contract, not a nicety.

**No test may call a live LLM or the network.** Live model runs are manual (`bomreuse run --notes
llm`), never part of `pytest`. If a test needed Ollama to pass, that is a FAIL regardless of the result.

---

## 2. Evaluation gate

```bash
uv run bomreuse evaluate --ground-truth data/ground_truth/ground_truth.json
```

The ground-truth path has no default and never will (docs/ARCHITECTURE.md A5); `--raw` and
`--spec` do, and point at the committed dataset and contract. From issue #5 on:

- it must run, offline, on the default dataset;
- it must print precision and recall on the **three reuse classes**, for the tool and for both
  naive baselines, with **counts next to every ratio**;
- **the figures it prints must be the ones the README's Results section quotes.** A figure that
  moved is not a FAIL by itself — there are **no regression floors** in this build (settled
  2026-09-21) and none is to be invented — but a README left quoting the old one is: report
  both, and the commit that moved it.

---

## 3. The non-negotiable invariants

These are `pytest` tests, so check 1 already ran them. Name them explicitly in the report, because
they are the ones whose silent disappearance would matter most:

- **Determinism** — same seed, byte-identical dataset.
- **Ground-truth isolation** — the runtime test (pipeline runs from a copy of `data/raw/` with no
  ground truth in sight) and the static AST test (no module but `evaluate.py` mentions the ground
  truth).
- **Inputs read-only** — hash before / hash after a run.
- **Traceable findings** — every finding carries source rows, a `rule_id` present in the
  catalogue, and a confidence.

If any of these tests is missing rather than failing, say so. A deleted invariant test reads as
green and is worse than a red one.

---

## 3 bis. The demo still runs

From issue #4 on, the tool has one command a client would see. Run it:

```bash
uv run bomreuse run --raw data/raw --out <tmp>
```

**Expected:** exit 0 offline, the artifacts the issue names written, and — from the signatures
issue on — a readable summary on stdout: each sub-assembly of the newest variant as *reused*,
*reusable* (with its diff) or *specific*. A pipeline that only writes JSON is a FAIL from that
issue on: the demo must never depend on the HTML report having landed.

---

## 4. Definition of done — the paperwork

Cheap, and it is half of what the issues ask for.

```bash
git diff origin/main --stat -- pyproject.toml uv.lock
```

- **A new dependency?** It needs a line in `DECISIONS.md`. Check that the line is there.
  **Agents never write that line** — if it is missing, stop and ask the human for the wording.
- **`CLAUDE.md` still true?** Module boundaries, the test-layer table, the issue and loop counts.
- **`README.md` still true?** In particular: every number in its Results section is one
  `evaluate` computed. No invented time or money figure, anywhere (`DECISIONS.md` 3).

---

## Checks this project deliberately does not run

No `mypy`, no `ruff`. Type hints are required everywhere by `CLAUDE.md`, but a type checker or a
linter would be a new dependency, and a new dependency needs a human decision in `DECISIONS.md`.
Do not add one to make this skill look fuller. If either ever appears in `pyproject.toml`, add it
here in the same commit.

---

## Report

```
VALIDATION — <issue or branch>

1. Tests .................... PASS / FAIL / N/A     (<n> tests, <t>s of a 30s budget)
2. Evaluation gate .......... PASS / FAIL / N/A     (regression? reason?)
3. Invariants ............... PASS / FAIL / MISSING (name any missing one)
3b. Demo command ............ PASS / FAIL / N/A     (`bomreuse run`, summary on stdout)
4. Definition of done ....... PASS / FAIL           (dependency lines, CLAUDE.md, README.md)

VERDICT: PASS / FAIL
```

On FAIL, quote the failing output rather than summarizing it, and say which issue's definition of
done is not met. Do not fix anything from inside this skill — report, and let the loop decide.
