# DECISIONS

One line per human decision: what was decided, why, and whether it overruled a proposal made
by the AI. Newest last. Agents do not write here on the human's behalf.

| # | Date | Decision | Why | Overruled AI? |
| --- | --- | --- | --- | --- |
| 1 | 2026-09-19 | Generate a synthetic dataset; no client CSV is expected | The brief asks for it; planted defects give a ground truth to measure against | No |
| 2 | 2026-09-19 | The tool is a scouting prototype, not the pilot deliverable | The pilot runs on the Cognyx platform; the build shows the data can be made sense of and sets what the pilot measures | No — the human questioned the initial framing, which was then clarified |
| 3 | 2026-09-19 | No invented time or money savings anywhere; business value is defined with the client | A days-per-tender estimate had no basis; the only numbers shown are measured ones | **Yes** — the AI had proposed an illustrative engineer-days-per-tender range |
| 4 | 2026-09-19 | Pilot's main success criterion: backtest on a past tender; staged in miniature in the dataset | It is the only strong proof achievable in 3 weeks; tenders take months | No |
| 5 | 2026-09-19 | Use an LLM, and compare a cloud model with a local one on the same task | Shows the on-prem path already runs, and what it costs in quality and time | No |
| 6 | 2026-09-19 | Models: `glm-5.3-flash:cloud` and `gemma4:12b-mlx` | Picked from the hal-benchmark v3 campaign (2026-09-08, M4 16 GB): best cloud candidate on stall and French; best local one on run errors and French | No |
| 7 | 2026-09-19 | Deterministic rules for references, units and signatures; LLM for free-text notes only | Traceable, testable core; the LLM only where rules cannot read | No |
| 8 | 2026-09-19 | Propose, never write back to source data | Validation, licensing and liability sit with the client | No |
| 9 | 2026-09-19 | Worked example: standard car vs bike / multi-purpose car | Real, documented case of costly regional customization; most of the car is reused, one zone changes | No — the human's idea, confirmed by research |
| 10 | 2026-09-19 | PIV workflow in a light version: 45 min planning cap, full loop on 3 risky issues only, hard stop at 4 h | Keep the AI trace without letting process eat the timebox | No |
| 11 | 2026-09-19 | Do not generalize the code for other clients in this build | Two examples show the shape; a third client is the moment to extract a generic brick | No |
| 12 | 2026-09-19 | Prepare the directory now; `git init` and the first commit only when the build starts | The first commit starts the 4-hour clock | No |
| 13 | 2026-09-19 | Problem statement: for a given variant, identify every sub-assembly that already exists in the other variants (identical or reusable with a diff) and flag unsafe reuse. Decomposing a new design for later reuse is out of scope | The pilot scope sentence allowed two readings; the brief's question is about what already exists. The PRD session was started before this was settled and paused | No — the human raised the ambiguity during the PRD session |
| 14 | 2026-09-19 | The synthetic data is designed backwards from the problem: chronology, hidden reuse, near-reuse, genuinely new sub-assemblies, unsafe reuse, backtest ground truth, exact-reference baseline | A dataset that cannot show the problem cannot prove the tool solves it | No |
| 15 | 2026-09-19 | A variant is an intermediate-car configuration; 4–6 variants with A (standard), B (bike car) and C (newest bike car) as the story; C is a full eBOM with its spec as metadata | Matching needs C's sub-assemblies, not its requirements (matching a spec would be option B or a configurator); two older variants are too few for a meaningful catalogue | No — the AI flagged both gaps, the human validated the fix |
