# STATUS — alstom-bom-reuse

Last updated: 2026-09-20 — **refocus session**

## Where this stands

The dataset and its measurement apparatus are built and tested. The half of the tool that
answers the client's question is not written: `resolve`, `checks`, `notes`, `link`, `report`
and the `run` entry point do not exist, and `signatures.py` is not wired to anything. The CLI
has two commands, `generate` and `normalize`, neither of which a client would look at.

Two thirds of the source (2 437 of 3 710 lines) and most of the tests are the synthetic-data
factory, which the brief asks for in one bullet. That is the overrun, and it is now closed:
**the data layer is frozen** (CLAUDE.md, "How we work").

## Tomorrow, in this order

Each step leaves the repo demoable. Stop wherever the time runs out and write the rest into the
README's "Known limits" — that is a normal outcome, not a failure.

1. **`resolve.py` + `bomreuse run`** — candidate groups to canonical components, `auto` /
   `review` / `reject` per Decision 20, and a `findings.json` carrying the duplicate-reference
   findings. First end-to-end command.
2. **Wire `signatures.py` into `run`** — classify every sub-assembly of the newest variant as
   *reused* / *reusable* (with the diff) / *specific*, against the older variants only.
   **This is the minimum viable demo: the client's question is answered here.** Everything
   after it is upside.
3. **`checks.py`** — unit, supplier and cost conflicts across variants. Cheap, and it is the
   second half of the client's question ("where are the inconsistencies").
4. **`notes.py` (keyword only) + `link.py`** — a note declaring a part obsolete, linked to a
   sub-assembly classified reusable, is the unsafe-reuse finding. The moment that makes the
   demo land.
5. **`backtest.py`** — two numbers: how many of the newest variant's sub-assemblies the tool
   finds as already existing, and how many the exact-reference search finds. Nothing else.
6. **`report.py`** — one static HTML: five numbers for Bruno at the top, the findings table
   with its evidence for Thomas below.
7. **README** — Results filled from the code's own output, Known limits filled honestly.

Reserve the last half hour, whatever state the code is in, for the email and the 40-minute
narrative. They are half the deliverable and neither is started.

## Cut, explicitly

- Issues #13 and #14 — won't do. Both are dataset-factory polish.
- Precision / recall per defect type, the same-name baseline, regression floors: replaced by
  step 5's two counts.
- The two-LLM comparison with latency per note: one backend, or none, plus the keyword
  fallback. The on-prem path is argued in the meeting from the adapter interface.
- PIV full loops, plan documents, implementation reports, self-reviews of own PRs. Direct
  implementation, one commit per module.

## What does not change

The non-negotiable rules of CLAUDE.md: inputs read-only, the pipeline never reads the ground
truth, findings carry their evidence, offline by default, no number that the code did not
compute.
