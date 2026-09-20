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

1. **Measure, don't claim.** Every quality statement comes from code that ran — `backtest` for
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
  backtest.py     the one claim: the newest variant vs the exact-reference search, both counted
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
- Two backends through the local Ollama API (`http://localhost:11434`), same prompt, same
  output schema:
  - `glm-5.3-flash:cloud` — high-end reference;
  - `gemma4:12b-mlx` — runs on a 16 GB laptop: the on-prem path.
- Invalid LLM output is logged and counted, never silently dropped.
- One backend is enough for this build; the second model and the latency comparison are cut.

## How we work (the AI trace is a deliverable)

**Refocus of 2026-09-20. The rules below replace the previous PIV plan; the human's line in
`DECISIONS.md` is still to be written.**

The exercise is a ~4 h timebox whose stated criterion is *an imperfect but working,
well-prioritized result*. Four hours went into the synthetic dataset and its measurement
apparatus; the half of the tool that answers the client's question does not exist yet. So:

- **The data layer is frozen.** `generate.py`, `catalogue.py`, `dirt.py`, `spec.py`,
  `ground_truth.py` and their tests are done. No new dataset work, no new planted case, no
  refinement of the dirt, no new invariant. Issues #13 and #14 are closed as won't-do.
- **The remaining budget goes to the missing half only**: `resolve` → `signatures` wired →
  `checks` → `notes` (keyword) + `link` → `report`, behind one `bomreuse run`.
- **Direct implementation.** No PIV full loop, no plan document, no implementation report, no
  self-review of a PR. One commit per module, one test file per module covering the tricky
  logic only. The AI trace is already a deliverable and is already rich.
- **The evaluation shrinks to one claim.** Not precision/recall over eight defect types, not
  two baselines, not regression floors: on the newest variant, how many sub-assemblies the tool
  finds as already existing, against the exact-reference search, both counted by code. One
  table. Everything else about measurement belongs in the meeting — *what the pilot should
  measure* — not in this repo.
- **Priority order, and it is the cut order**: answer the client's question first (resolve +
  signatures, wired end to end), then the inconsistencies, then the notes, then the one-number
  backtest, then the report, then polish. Whatever is not reached goes into the README's
  "Known limits", with the reason. A stage that is not reached is a normal outcome, not a
  failure.
- **The LLM layer is one backend plus the keyword fallback**, and only if the rest is standing.
  The two-model comparison with latency per note is cut; the on-prem path is argued in the
  meeting from the adapter interface.

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
| Backtest | The one value claim is computed, not written | `backtest` runs on the default dataset and prints both counts; a test asserts the tool's count is the one the code produced |

Rules:

- Tests never call a live LLM or the network. Live model runs are manual, never in `pytest`.
- Write the test with the code, in the same commit. For a bug, the failing test comes first.
- No regression floors in this build: the backtest prints its two counts and the README quotes
  them. Floors are a pilot-scale practice, argued in the meeting, not built here.

## Definition of done (per issue)

- Tests in `tests/` pass (`uv run pytest`).
- `uv run bomreuse run` still produces findings end to end; once `backtest` exists, its two
  counts are quoted in the README from the code's own output.
- No new dependency without a line in `DECISIONS.md`.
- `CLAUDE.md` and `README.md` still true.

## Out of scope

Web UI, graph database, a real PLM/ERP connector, a mandatory LLM, generalizing the code for
other clients. The generic version is a later decision, not part of this build.

## Pointers

- `docs/case-brief.md` — the case as given.
- `CONTEXT.md` — pilot context, domain vocabulary, the worked example.
- `DECISIONS.md` — human decisions, dated.
- `.claude/PIV-PROCEDURE.md` — the per-issue checklist: which skill, in which conversation, when to clear.
- `prep/` — local preparation notes, not versioned.
