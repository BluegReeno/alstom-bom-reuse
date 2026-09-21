# Architecture — alstom-bom-reuse

The high-level *how*, decided before implementation. `docs/PRD.md` holds the *what* and *why*;
`CLAUDE.md` holds the standing rules; `DECISIONS.md` holds the human decisions. This document
does not restate any of them — it settles what they left open.

Scope of this session: the seven open calls, plus three minor ones. Module boundaries, the
entity model, the two Ollama backends, the offline default and the five test layers were
already fixed by `CLAUDE.md` and were not reopened.

## Problem & goals

For a given train-car variant, say which of its sub-assemblies already exist in the other
variants — identical, or reusable with a known diff — and flag what would make a reuse unsafe.
The only value claim the build makes is the measured gap between the tool and a naive
exact-reference search on the same data. Every decision below is judged against that: does it
make the gap more honest, more traceable, and more defensible to a lead data engineer.

## Approaches considered

Three structuring calls had more than one viable answer.

**How to measure the distance between two sub-assembly signatures.** A continuous normalized
score (weighted Jaccard, or cosine over the quantity vector) with a threshold around 0.85 gives
one elegant number, but an arbitrary float that Decision 17 forbids tuning is indefensible: it
can neither be explained nor moved. An absolute counting rule speaks the vocabulary the PRD and
`CONTEXT.md` already use — "differing by 1–3 parts", "same seat, different count" — so the
threshold reads as a contract in the domain's own language rather than as a magic constant.
**Counting wins**, with a relative guard so that three parts out of five is not treated like
three out of sixty.

**How to resolve duplicate references.** Rules only (canonical key), rules plus a corroborated
`difflib` pass, or rules plus `rapidfuzz`. The trap is that in a BOM two references differing by
one character are often genuinely different parts, and a false *reused* is the worst error this
tool can make — it is precisely what it claims to find. **Rules only wins**: it is deterministic,
explainable, testable, and it cannot manufacture a false match. Its cost is named and measured
rather than hidden (see the typo families below).

**What counts as a correct answer.** Scoring the class alone inflates the result, since
predicting *reusable* against the wrong ancestor would count as a success. Scoring the class,
the ancestor and the exact diff makes the headline figure depend on a formatting contract.
**Class plus ancestor wins**: an engineer acting on a *reusable* verdict needs the right
ancestor, while diff exactness is a rendering concern that belongs to the test layer.

## Recommended approach

A linear, file-to-file pipeline. Each stage reads the previous stage's JSON artifact from
`out/` and writes its own, so every stage is independently testable and every finding is
traceable back through the chain:

```
data/raw/*.csv ──▶ ingest ──▶ normalize ──▶ resolve ──▶ signatures ──▶ checks ──▶ report
                                               │            │            ▲
                                            notes ──────────┴────────────┘
                                                                          
data/ground_truth/*.json ────────────────────────────────▶ evaluate ◀── predictions
```

The evaluation is deliberately outside that chain: **one scorer, two predictors.** The tool and
the naive baseline both emit the same prediction shape, and a single scoring function consumes
both. The baseline reads the *raw* ingested rows, never the normalized ones — otherwise it
inherits our normalization and the measured gap closes artificially. A second baseline, *same
name*, was added after the project review (PRD [A3], issue #5): it goes through the same scorer,
so "two predictors" now reads "one tool, two baselines".

## Key decisions

### A1 — Signature, distance and threshold

The signature of a sub-assembly is the multiset of `(canonical component, normalized quantity,
SI unit)` it contains. The distance is two counters over the symmetric difference:

- `n_parts_diff` — canonical components added or removed;
- `n_qty_diff` — components present on both sides with a different quantity.

Both counters are judged against the same budget, so the rule stays symmetric — three quantity
differences out of five components are no more acceptable than three missing parts:

```
budget = min(max_abs_diff, ceil(diff_ratio * min(len(a), len(b))))
```

| Verdict | Rule |
| --- | --- |
| `identical` | `n_parts_diff == 0` and `n_qty_diff == 0` |
| `reusable` | `n_parts_diff <= budget` and `n_qty_diff <= budget` |
| `specific` | otherwise |

The diff itself — added, removed, quantity changed — is the evidence attached to the finding,
produced by the same comparison at no extra cost.

`max_abs_diff` (3) and `diff_ratio` (0.25) both live in `data/dataset_spec.toml`, read through
`tomllib` (standard library in 3.12, so no dependency) and parsed into a frozen dataclass by
`spec.py`. `generate.py` and `signatures.py` both go through that loader; `evaluate.py` reports
against it and never moves it. The file is written before the dataset is generated and the git
history shows it (Decision 17).

The budget degenerates at the bottom of the size range: with `min(len) == 1`,
`ceil(0.25 * 1) == 1`, so a one-component sub-assembly and a two-component one would come out
*reusable*. The fix belongs to the data, not to the rule — `data/dataset_spec.toml` sets a
**minimum sub-assembly size of 4 components** and the generator honours it. A special case in
the verdict rule would be a threshold bent around a degenerate input, which is exactly what
Decision 17 exists to prevent.

### A2 — Reference resolution: rules only

A canonical key is derived from the raw reference: uppercase, whitespace and separators
collapsed, homoglyphs folded (`O`↔`0`, `I`/`l`↔`1`), non-alphanumerics dropped. Rows sharing a
canonical key form one canonical component. No string-distance matching anywhere in the
pipeline.

This changes what R5's `auto / review / reject` verdict means. It no longer rates the confidence
of a fuzzy match — there is none. It rates the **coherence of the group** the canonical key
formed:

| Verdict | Meaning |
| --- | --- |
| `auto` | the group is homogeneous; it feeds the signatures |
| `review` | the rows share a key but diverge on designation, unit, supplier or cost — grouped, reported as a finding, **and it feeds the signatures too** (Decision 26) |
| `reject` | the designations clearly describe two different products; the group is split back apart |

The consequence of rules-only is that transpositions (`BGI-2031` → `BGI-2013`) and missing
characters are out of reach by construction. `data/dataset_spec.toml` therefore declares the
typo families it plants, **including one or two the rules cannot catch**. The resolution recall
comes out below 1, `evaluate` measures the shortfall, and the README's "Known limits" carries a
figure instead of a caveat. A dataset that only plants defects the tool catches proves nothing.

Rules-only resolution carries a symmetric risk on precision, and the dataset must be able to
expose it. If the spec plants only defects the folding rules catch — plus the few they cannot —
then nothing in the data can produce a **false merge**, and `evaluate` reports a resolution
precision of 1.0 that measures nothing, while this document holds that a false *reused* is the
worst error the tool can make. So `data/dataset_spec.toml` plants **at least two pairs of
genuinely different references separated by exactly one character the folding rules collapse** —
an `O` against a `0`, an `I` against a `1`, a separator against none — and the ground truth
declares them **must-not-merge**. If the rules merge them, precision drops below 1 and the miss
is shown on purpose in the report; if they hold, the 1.0 is a result rather than an artefact of
the dataset.

### A3 — Evaluation semantics

Two different shapes, scored separately, never merged into one headline figure.

**Reuse classification (the backtest).** Each sub-assembly of the newest variant is one item,
with a ground-truth label in `{reused (+ ancestor id), reusable (+ diff), new}`. A true positive
for *reused* and *reusable* requires the predicted class **and** the predicted ancestor id to
match. The diff is displayed in the report and asserted by the end-to-end test, but it is not
scored. `evaluate` scores decisions; `pytest` guards the evidence.

**Inconsistency findings.** A set comparison per defect type, matched on a **stable key** that
the emitted finding must reproduce exactly.

That key must contain nothing the pipeline produces. A key built on `canonical_component_id`
would be circular: the canonical id comes out of `resolve.py`'s folding rules, while the ground
truth is written by `generate.py` before any resolution exists. Either `generate` imports
`resolve`'s key function — and the ground truth becomes definitionally aligned with the
implementation, so resolution recall is 1 by construction — or it reimplements it and the two
drift apart. Both make the score circular.

The identity is therefore owned by the generator and knows nothing about the rules:

- `generate` invents a **true component** (`TRUE-0042`), then emits the raw reference strings
  that stand for it across the variants, planted typos included;
- the ground truth records `true_component_id -> {raw reference strings emitted}`;
- the stable defect key is `(defect_type, true_component_id, variant_pair)`.

`evaluate` then scores resolution as a **clustering** problem against that mapping, sharing no
code with the side it scores:

- **recall** — all the raw strings of one true component landed in one canonical group;
- **precision** — a canonical group holds strings from only one true component.

Typo families beyond the reach of the folding rules — transpositions, missing characters — then
come out as genuine **misses**, measured rather than defined away. That is the whole reason for
declaring them in the spec.

Precision and recall are reported per type, plus the baseline gap. No aggregate F1 (Decision 3).

### A4 — Data carriage: standard library

`csv` from the standard library, into frozen dataclasses carrying `raw` and `normalized` side by
side. No pandas. The reason is not size — at ~1,500 rows everything works — it is R3: pandas
coerces on read. `0031` becomes `31`, `1,5` becomes `NaN` or a string depending on inference,
trailing spaces vanish. That is exactly the class of corruption this tool exists to detect;
delegating it to the parser would be self-defeating.

Those dataclasses are the project's **single set of types**. Every stage passes them, and the
JSON artifacts in `out/` are serialized from them and read back into them. No schema library
mirrors them (see A8).

### A5 — Ground-truth isolation, made structural

`data/raw/` is the pipeline's only input. `data/ground_truth/` is read by `evaluate` alone.

The ground-truth path is **not a constant anywhere**. It is a CLI argument: `generate` writes it
where told, `evaluate` reads it where told, and the pipeline's entry function has no parameter
that could carry it. The invariant is not a promise kept by discipline — violating it requires
changing a signature.

Two cheap tests back it up: a runtime one (copy `data/raw/` to a temporary directory with no
ground truth in sight, run the full pipeline, assert it completes) and a static one (AST scan of
`src/bomreuse/*.py`, asserting no module other than `evaluate.py` mentions the ground truth).

### A6 — LLM adapter

One note per call. R8 requires per-note latency, and a batch that a single invalid output
poisons loses the other thirty-nine. HTTP through `urllib.request` from the standard library,
with a per-call timeout and one retry — a single POST to localhost does not justify a client
library. `format=json` on the Ollama side, then strict validation with pydantic into a typed
model. Invalid output is logged and counted, never silently dropped.

Responses are cached on disk, keyed by `(model, prompt hash, note id)`, and the cache is
**gitignored**: it is a local accelerator, not a deliverable.

That leaves a gap the README would otherwise fall into. It will carry a cloud-versus-local
comparison table while promising a clone that runs in one command — and a fresh clone has no
cache. So the **scored results** are committed, as a thing distinct from the cache: a few KB of
JSON at `docs/measurements/llm-comparison-<YYYY-MM-DD>.json`, written by `evaluate`, holding the
two model ids, the dataset spec it was measured against, per-note validity and latency, and the
resulting precision and recall. The README cites that file by name and date. The cache makes a
re-run cheap; the committed artifact makes the published figures checkable by someone who has
neither Ollama nor the network.

On a fresh clone without Ollama the pipeline still runs end to end on the keyword fallback, so
R10 holds. What cannot be *recomputed* there is the comparison itself, and the README says so
next to the table.

### A7 — Note-to-component linking

One rule, and it removes the duplication: **only `resolve.py` knows how to turn a string into a
canonical component.** It exposes `match_reference(resolution, raw_token) -> Candidate | None`:
the module holds no state, so the resolution to look in is a parameter, and `link.py` reads
`out/resolution.json` as its second input.

The linking step is a module of its own, `link.py`, sitting between `notes.py` and `checks.py`:

- `notes.py` extracts facts carrying **raw** reference strings, and never matches;
- `link.py` resolves those raw strings to canonical components, and is the only caller of
  `resolve.match_reference` outside `resolve` itself;
- `checks.py` consumes already-linked facts and confronts them with the BOM.

`CLAUDE.md`'s "Intended module boundaries" block is updated in the same commit as this document,
as that file requires.

### A8 — Report, artifacts, confidence

- **Report**: `string.Template` from the standard library, one self-contained HTML file with
  inline CSS, written to `out/`, plus `out/findings.json` for the reviewer. A template engine is
  not worth a dependency for one template.
- **Artifacts**: one JSON per stage in `out/` (`normalized`, `resolution`, `signatures`,
  `findings`, `predictions`), serialized from the A4 dataclasses and read back into them. No
  pydantic mirror of the internal model: a second set of types describing the same entities is
  two things to keep in step, and the data crossing these files is ours, not untrusted.
  pydantic guards the two boundaries where data arrives from outside — the LLM output and the
  ground-truth schema — and nothing else.
- **Confidence** ([A5] in the PRD): a constant per rule, declared next to the rule in a
  versioned `rule_id -> confidence` table. Reported, never thresholded, in this build.

### Stack & libraries

Python 3.12 with `uv`. Standard library for CSV, TOML, HTTP, string distance-free normalization
and templating; frozen dataclasses for every internal entity. **pydantic is the single new
runtime dependency**, scoped to the two untrusted boundaries — the LLM output and the
ground-truth schema. Everything internal stays on dataclasses. It requires a line in
`DECISIONS.md`, written by the human. `pytest` for tests.

The deployment answer that follows — "what do we need to run this inside your network?" —
is: Python 3.12, pydantic, and Ollama only if the LLM layer is wanted.

### Boundaries & contracts

- **Network**: the only outbound call is to `http://localhost:11434`. Nothing else, ever. Tests
  never call it.
- **Secrets**: none. No API keys, no credentials, no `.env`.
- **Inputs are read-only**, enforced by a hash-before/hash-after test.
- **No write-back** to any source system; the tool emits proposals (Decision 8).
- **Data**: everything under `data/` is synthetic and generated from a fixed seed.

## Missing pieces

These do not exist yet and the approach depends on them:

- `data/dataset_spec.toml` — the planted-case table, the typo families (in and out of reach of
  the rules), the must-not-merge pairs, the minimum sub-assembly size, and the two threshold
  parameters. Written before the generator.
- `spec.py` — the single loader `generate.py` and `signatures.py` both read that contract
  through.
- The ground-truth schema: the `true_component_id -> {raw reference strings}` mapping, the
  must-not-merge declarations, and the stable defect key A3 matches on.
- The note-extraction prompt and its output model, plus the FR/EN keyword fallback lexicon.

## Spikes & experiments

**S1 — Does the threshold agree with the story?**
The threshold is written before generation and never tuned, so a disagreement between it and the
planted cases has only one honest resolution, and it must be found early.
*Spike*: write the 5–10 story cases by hand (bike module with two fewer hooks, seating module
with tip-up seats, the new anchorage) and run the A1 verdict rule against them as a unit test,
before generating anything.
*Decision rule*: if a case the story calls *reusable* fails the rule, the **dataset spec**
changes — the part counts — never the threshold.

**S2 — Does the local model return usable JSON?**
G4, the on-prem path, collapses if `gemma4:12b-mlx` cannot produce valid structured output on
mixed FR/EN notes.
*Spike*: five hand-written notes, both backends, `format=json`, before building the adapter.
*Decision rule*: if the local model returns fewer than three valid outputs out of five, simplify
the extraction schema — fewer fields, one fact per call — before building, rather than
discovering it at evaluation time.

## Open questions

- ~~Does the `review` lane feed the catalogue?~~ **Settled by Decision 26: yes.** Signatures
  are built on every merged group, `auto` and `review`; only `reject` splits. Identity and
  attribute coherence are separate questions, and the dataset plants a conflict on 13 components
  touching 9 of the newest variant's 15 sub-assemblies — reading `auto` groups only would blind
  the backtest exactly where the data is dirty. The `review`-lane ceiling this question also
  raised has no object any more.
- **Regression floors.** Set from the first real measurement and written into `DECISIONS.md`,
  per `CLAUDE.md`. They cannot be chosen before a number exists.
- **Nested sub-assemblies.** Out of scope by [A1]; the signature would need to become recursive.
  Named here so the limit is deliberate rather than discovered.
