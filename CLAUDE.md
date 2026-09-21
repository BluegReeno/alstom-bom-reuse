# CLAUDE.md — alstom-bom-reuse

Rules for any AI agent (and any human) working in this repository. Read this file, then
`CONTEXT.md`, then `DECISIONS.md`, before touching code.

## What this is

A small working tool, **deliberately small in scope**, for a fictional pilot: Cognyx at Alstom
Valenciennes (regional trains). It ingests a multi-variant Bill of Materials and free-text
technical notes, normalizes them into a simple entity model, and answers one client question:

> Which sub-assemblies are reused — or reusable — across train variants, and where are the
> inconsistencies?

The problem it solves, as stated in `README.md`: **for a given variant, identify every
sub-assembly that already exists in the other variants — identical, or reusable with a known
diff — and flag the inconsistencies that would make reuse unsafe.** The proof is a backtest:
the newest variant plays the new tender, and the tool is compared with a naive exact-reference
search. Decomposing a new design for later reuse is out of scope.

It is a **scouting prototype**, not the pilot deliverable. The pilot itself runs on the Cognyx
platform. This tool shows that the data can be made sense of, that the method is measurable,
and what the pilot should measure. The brief is in `docs/case-brief.md`.

## Non-negotiable rules

1. **Measure, don't claim.** Every quality statement comes from code that ran — `evaluate` for
   the value claim, the findings artifact for the counts. No number in the README, report or commit messages that the code did not
   compute. No invented business figures (time or money saved): those come from the client.
2. **The ground truth is for scoring only.** The pipeline never reads `ground_truth` files.
   Only the evaluation module does. A test enforces it.
3. **Propose, never write.** Inputs are read-only. The tool outputs findings and merge/reuse
   *proposals* with their evidence; a human validates them.
4. **Deterministic first, LLM where it earns its place.** References, units and signatures
   are handled by rules and scores. The LLM only reads free-text notes (FR/EN).
5. **Offline by default.** The full pipeline runs with no network, using a keyword fallback
   for notes. The LLM is an optional adapter behind one interface.
6. **Traceable findings.** Every finding carries its source rows, the rule that produced it,
   and a confidence.
7. **Reproducible.** The synthetic dataset is generated from a fixed seed. Same seed, same
   files, byte for byte.
8. **No real client data, no secrets.** Everything under `data/` is synthetic.

## Language and style

- Everything in English: code, comments, docs, commit messages, file names.
- Python 3.12, managed with `uv`. Dependencies pinned in `uv.lock`; keep them few.
- Type hints everywhere. Small modules, small functions, no clever metaprogramming.
- Comments explain *why*, not what. Match the density of the surrounding code.
- A data engineer must be able to read any module in five minutes and maintain it.

## Intended module boundaries

The architecture decision record may revise this; if it does, update this section in the
same commit.

```
src/bomreuse/
  generate.py     true model -> seeded dirt -> derived ground truth; imports no pipeline module
  catalogue.py    the hand-written, seed-independent story: variants, components, contents, notes
  dirt.py         pure seeded operators: typos by kind, mixed units, decimal commas, case noise
  ground_truth.py pydantic schema of the ground truth (one of the two pydantic boundaries)
  ingest.py       read raw CSVs as-is, keep raw values; structure checked strictly (IngestError)
  normalize.py    reference key (uppercase, then O/I/L folding), units to SI (m, kg, pcs), text,
                  decimal commas; unreadable values kept and counted (NormalizationIssue)
  model.py        raw rows; entities: Variant, SubAssembly, Component (candidate group), Supplier,
                  BomLine (n-ary), Note; JSON round-trip of out/normalized.json
  resolve.py      duplicate references -> canonical component (auto / review / reject)
  signatures.py   sub-assembly signatures: reused (identical) / reusable (near-identical + diff)
  checks.py       inconsistencies: unit, supplier, cost conflicts, note vs BOM contradictions
  notes.py        note extraction: LLM adapter (Ollama) + keyword fallback, schema-validated
  link.py         note facts -> canonical components; only caller of resolve.match_reference
  spec.py         loads data/dataset_spec.toml (thresholds, planted cases) as a frozen dataclass
  evaluate.py     the one claim: the newest variant's reuse classes, tool vs two naive baselines
  baseline.py     exact-reference and same-name searches, reading raw rows only
  report.py       static HTML report: sponsor summary first, traceable detail after
  cli.py          one entry point; every path, the ground truth's included, is an argument
tests/            all tests live here
data/             dataset_spec.toml (the contract), raw/ (the pipeline's only input), ground_truth/
out/              generated report and findings
```

Entity model: a `BomLine` is an n-ary relation (parent, child, quantity, unit, variant), not
an attribute of a component. Variability is carried by the line, not by duplicating the
product.

## LLM layer

- One task only: extract structured facts from a note (replacement, obsolescence,
  restriction, referenced part), with the source note cited.
- One backend through the local Ollama API (`http://localhost:11434`): `gemma4:12b-mlx`, which
  runs on a 16 GB laptop and is therefore the on-prem path. The backend is a constructor
  argument, so a second model is a flag rather than a rewrite — but this build scores neither.
- Invalid LLM output is logged and counted, never silently dropped.
- The FR/EN keyword fallback is not a degraded mode: it is what makes rule 5 hold, and the
  pipeline runs end to end with Ollama unreachable.

## How we work (the AI trace is a deliverable)

**Refocus of 2026-09-21, recorded as `DECISIONS.md` 29. The rules below replace the previous
PIV plan.**

Four hours of a ~4 h exercise produced the synthetic dataset and its measurement apparatus —
two thirds of the source — while the half of the tool that answers the client's question did
not exist. The correction is a cut in **scope**, not in process: a coherent, validated path
from issue to PR is part of what this build demonstrates, and it costs machine time rather
than the human's.

### One issue, one run, one PR

Each issue is sized to fit a single PR and is written to be executed by an autonomous
`issue → PR` run. An autonomous run cannot ask a question, so **every open call is settled in
the issue before the run starts**. Each issue therefore carries, always in this order:

1. **Context** — which files to read first, and the handover facts it needs.
2. **Scope** — what to build, with every call already made.
3. **Out of scope for this run** — the explicit do-not list. This is what keeps the run from
   rebuilding the dataset layer or inventing a measurement.
4. **Acceptance criteria** — checkable, as commands wherever possible.
5. **Validation** — the `piv-validate` skill, and the demo command that must still work.
6. **If blocked** — stop, write what is missing in the PR description, do not widen the scope
   and do not decide for the human. A genuinely undecided call is a stop, not a guess.

Plan documents and implementation reports are dropped: the issue is the plan and the PR
description is the report. The review step stays, inside the run.

### Scope, settled on 2026-09-21

- **The data layer is frozen.** `generate.py`, `catalogue.py`, `dirt.py`, `spec.py`,
  `ground_truth.py` and their tests are done. No new dataset work, no new planted case, no
  refinement of the dirt. Issue #13 is closed by PR #15 and is the last of it; #14 is closed
  won't-do, and the guard it describes becomes a line in Known limits.
- **`evaluate` scores the backtest and nothing else**: the three reuse classes on the newest
  variant, against the two naive baselines (exact reference, same name), with counts next to
  every ratio. Resolution scoring and per-defect-type scoring are cut; inconsistency findings
  are counted and displayed, and the end-to-end test asserts the planted ones are found.
- **The LLM layer is one backend** (`gemma4:12b-mlx`, the on-prem path) behind the adapter
  interface, plus the FR/EN keyword fallback that keeps the pipeline offline. No backend
  scoring, no latency table, no `docs/measurements/`. If both models are run by hand at the
  end, their figures go in the README as a manual measurement, labelled as one.
- **Six issues, in this order**: #4 resolve + rule catalogue + `run` → #16 signatures wired +
  backtest predictions → #17 checks → #5 evaluate → #6 notes + link → #7 report + README.
- **Every run leaves the tool demoable.** From #15 on, `bomreuse run` prints a readable summary
  to stdout — reused / reusable / specific with the diffs — so a demo never depends on the HTML
  report having landed.
- **Cut order is the reverse of the build order.** Whatever is not reached goes into the
  README's "Known limits", with the reason. A stage that is not reached is a normal outcome.

Commits:

- Conventional prefixes (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), each referencing its
  issue (`#3`). No squashing: the history is part of the deliverable.
- A commit never mixes two issues.

`DECISIONS.md`:

- One line per **human** decision: what, why, and whether it overruled an AI proposal.
- Agents do not write decisions on the human's behalf. When an agent proposes something the
  human rejects, the agent reminds the human to log it.

## Testing

Two different things, never confused: **tests** prove the code does what it says;
**evaluation** measures how good the results are against the ground truth. Both run in CI-like
fashion locally, and the whole test suite must stay under 30 seconds so it can run live.

| Layer | What it checks | Examples |
| --- | --- | --- |
| Unit | Pure functions, one behaviour per test | ID variants (`BGI-2031`, `BG1-2031`, `bgi 2031 `) normalize together; `1,5 m` = `1500 mm`; `g` → `kg`; signature of a sub-assembly; diff between two signatures |
| Invariants | The non-negotiable rules above hold | Same seed → byte-identical dataset; no pipeline module imports or opens the ground truth; input files unchanged after a run (hash before/after); every finding has source rows, rule and confidence |
| LLM adapter | Behaviour without calling a model | A fake backend returns canned outputs; malformed output is logged and counted, not dropped; the FR/EN keyword fallback extracts the expected facts |
| End-to-end | The pipeline on a small generated dataset | Generate with a test seed, run, and assert every planted "reused" and "re-designed in the newest variant" case is found |
| Backtest | The one value claim is computed, not written | `evaluate` runs on the default dataset and prints the three reuse classes for the tool and for both naive baselines, counts next to ratios |

Rules:

- Tests never call a live LLM or the network. Live model runs are manual, never in `pytest`.
- Write the test with the code, in the same commit. For a bug, the failing test comes first.
- No regression floors in this build: `evaluate` prints its figures and the README quotes them.
  Floors are a pilot-scale practice, argued in the meeting, not built here.

## Definition of done (per issue)

- Tests in `tests/` pass (`uv run pytest`).
- `uv run bomreuse run` still produces findings end to end and prints its summary; once
  `evaluate` exists, its figures are quoted in the README from the code's own output.
- No new dependency without a line in `DECISIONS.md`.
- `CLAUDE.md` and `README.md` still true.

## Out of scope

Web UI, graph database, a real PLM/ERP connector, a mandatory LLM, generalizing the code for
other clients. The generic version is a later decision, not part of this build.

## Pointers

- `docs/case-brief.md` — the case as given.
- `CONTEXT.md` — pilot context, domain vocabulary, the worked example.
- `DECISIONS.md` — human decisions, dated.
- `.claude/RUN-PROCEDURE.md` — the per-issue checklist for an autonomous issue → PR run.
- `prep/` — local preparation notes, not versioned.
