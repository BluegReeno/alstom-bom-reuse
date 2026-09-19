# CLAUDE.md — alstom-bom-reuse

Rules for any AI agent (and any human) working in this repository. Read this file, then
`CONTEXT.md`, then `DECISIONS.md`, before touching code.

## What this is

A small working tool, built in a **4-hour timebox**, for a fictional pilot: Cognyx at Alstom
Valenciennes (regional trains). It ingests a multi-variant Bill of Materials and free-text
technical notes, normalizes them into a simple entity model, and answers one client question:

> Which sub-assemblies are reused — or reusable — across train variants, and where are the
> inconsistencies?

It is a **scouting prototype**, not the pilot deliverable. The pilot itself runs on the Cognyx
platform. This tool shows that the data can be made sense of, that the method is measurable,
and what the pilot should measure. The brief is in `docs/case-brief.md`.

## Non-negotiable rules

1. **Measure, don't claim.** Every quality statement comes from `evaluate`, run against the
   ground truth. No number in the README, report or commit messages that the code did not
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
  generate.py     synthetic dataset + planted defects + ground truth (fixed seed)
  ingest.py       read raw CSVs as-is, keep raw values
  normalize.py    ids, units (to SI, raw kept), text, decimal commas
  model.py        entities: Variant, SubAssembly, Component, Supplier, BomLine (n-ary)
  resolve.py      duplicate references -> canonical component (auto / review / reject)
  signatures.py   sub-assembly signatures: reused (identical) / reusable (near-identical + diff)
  checks.py       inconsistencies: unit, supplier, cost conflicts, note vs BOM contradictions
  notes.py        note extraction: LLM adapter (Ollama) + keyword fallback, schema-validated
  evaluate.py     precision / recall per defect type, against the ground truth
  report.py       static HTML report: sponsor summary first, traceable detail after
  cli.py          one entry point
tests/            all tests live here
data/             generated inputs (synthetic) + ground truth
out/              generated report and findings
```

Entity model: a `BomLine` is an n-ary relation (parent, child, quantity, unit, variant), not
an attribute of a component. Variability is carried by the line, not by duplicating the
product.

## LLM layer

- One task only: extract structured facts from a note (replacement, obsolescence,
  restriction, referenced part), with the source note cited.
- Two backends through the local Ollama API (`http://localhost:11434`), same prompt, same
  output schema:
  - `glm-5.3-flash:cloud` — high-end reference;
  - `gemma4:12b-mlx` — runs on a 16 GB laptop: the on-prem path.
- Invalid LLM output is logged and counted, never silently dropped.
- Both backends are scored by `evaluate` on the same ground truth, with latency per note.

## How we work (the AI trace is a deliverable)

The workflow is PRD → architecture → issues → plan / implement / validate per issue, using the
PIV skills, in a **light** version:

- Planning is capped at 45 minutes: a one-page PRD, one architecture decision, 6 GitHub issues.
- The full PIV loop (plan, implement, validate) only on the 3 risky issues: data generator,
  normalization, resolution plus evaluation.
- The LLM layer, the report and the README get a light or direct loop.
- **Hard stop at 4 hours.** Whatever is not done goes into the README's "Known limits".
- If time runs short, cut scope in this order: report polish, LLM layer extras, then nothing
  else. **Never cut the evaluation.**

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
| Evaluation gate | Quality does not silently regress | `evaluate` runs on the default dataset; precision and recall per defect type stay above floors set once the first numbers are known |

Rules:

- Tests never call a live LLM or the network. Live model runs belong to `evaluate`, not to
  `pytest`.
- Write the test with the code, in the same commit. For a bug, the failing test comes first.
- The evaluation floors are set from the first real measurement and written in
  `DECISIONS.md`; lowering one needs a new line there.

## Definition of done (per issue)

- Tests in `tests/` pass (`uv run pytest`).
- `uv run bomreuse evaluate` still runs and its numbers did not regress without a reason
  written in the commit message.
- No new dependency without a line in `DECISIONS.md`.
- `CLAUDE.md` and `README.md` still true.

## Out of scope

Web UI, graph database, a real PLM/ERP connector, a mandatory LLM, generalizing the code for
other clients. The generic version is a later decision, not part of this build.

## Pointers

- `docs/case-brief.md` — the case as given.
- `CONTEXT.md` — pilot context, domain vocabulary, the worked example.
- `DECISIONS.md` — human decisions, dated.
- `prep/` — local preparation notes, not versioned.
