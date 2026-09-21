# alstom-bom-reuse

> Status: work in progress. Built for the Cognyx FDE case study (fictional pilot at Alstom
> Valenciennes), scoped small on purpose. All data is synthetic.

## The problem

When a new tender comes in, engineers cannot tell which of the sub-assemblies it needs already
exist in past train variants. The data does not let anyone recognize that a part or a
sub-assembly is the same from one variant to the next: duplicated references with typos, mixed
units, free-text notes in French and English that sometimes contradict the Bill of Materials.
So what already exists is re-designed and re-costed.

**The problem this tool solves: for a given variant, identify every sub-assembly that already
exists in the other variants — identical, or reusable with a known diff — and flag the
inconsistencies that would make reuse unsafe.**

## How it answers it

1. **The foundation.** A deduplicated catalogue of sub-assemblies across all existing variants,
   each with where it is used, classified:
   - *reused* — identical across variants;
   - *reusable* — near-identical, with the exact diff;
   - *specific* — used by one variant only;

   plus the list of inconsistencies (duplicate references, unit conflicts, supplier or cost
   conflicts, notes contradicting the BOM). This answers the brief's question: *which
   sub-assemblies are reused — or reusable — across variants, and where are the
   inconsistencies?*
2. **The proof of use (backtest).** The newest variant plays "the new tender". Given only the
   older variants, the tool says which of its sub-assemblies already existed, and compares
   itself with a naive search by exact reference on the same data. The gap between the two is
   the measured value.

| In scope | Out of scope |
| --- | --- |
| Finding what already exists for a given variant, with evidence | Decomposing a new design to make it reusable later (CAD and engineering work, not data) |
| Flagging inconsistencies that make a reuse unsafe | Fixing the data in the PLM: the tool only proposes |
| Measuring how much an exact-reference search misses | Estimating time or money saved: defined with the client |

Primary user: the design engineer preparing a tender.

## What the synthetic data contains, and why

The dataset is designed backwards from the problem: each property exists so that one claim can
be measured.

- 4–6 variants of a regional-train **intermediate car** (standard, bike car, bi-mode, other
  regions), ~100–250 BOM lines each, with a chronology (design date, region, seats, bike
  spaces, traction). Three carry the story: A (standard), B (bike car) and C, the newest — a
  bike car for a new region, playing the "new tender".
- C is a full eBOM, as designed. Its spec (region, seats, bike spaces, date) is variant
  metadata: the tool matches sub-assemblies, not requirements.
- Costs and suppliers per component, with conflicts across variants; ~40 technical notes in
  French and English.
- Hidden reuse: sub-assemblies of the newest variant identical in content to older ones, under
  new or typo'd references.
- Near-reuse: sub-assemblies differing from an older one by 1–3 parts.
- Genuinely new sub-assemblies, so the tool cannot claim that everything already exists.
- Unsafe reuse: a matched older sub-assembly containing a part a note declares obsolete.
- A ground truth, read only by the evaluation, never by the pipeline.

As generated: 5 variants (A, B, D, E and C), 696 BOM lines (135 to 145 per variant) and 40
notes, in three `;`-separated UTF-8 files under `data/raw/` — `variants.csv`, `bom.csv`,
`notes.csv`. `data/dataset_spec.toml` is the contract they are generated from.

## How to run

Python 3.12 and [`uv`](https://docs.astral.sh/uv/). Everything runs offline.

```bash
uv sync
uv run pytest
```

Regenerate the synthetic dataset (the committed one uses the default seed, and a test checks
that it is byte-identical to a fresh generation):

```bash
uv run bomreuse generate --out data/raw --ground-truth data/ground_truth/ground_truth.json
```

Both paths are required arguments: the ground-truth location is never a constant in the code,
and the pipeline only ever reads `data/raw/`. The seed (`--seed`) moves the dirt — spellings,
units, decimal commas — never the story: every seed yields the same backtest answers.

Read the raw files and write the normalized dataset:

```bash
uv run bomreuse normalize --raw data/raw --out out
```

This is the first stage of the pipeline. It reads the three CSV files exactly as they are —
nothing is stripped or cast on read — and writes `out/normalized.json`, where every value keeps
its raw characters next to what the tool made of them (line `L00052`: `42000` `mm` next to
`42.0` `m`). A value it cannot read keeps its row, is stored as `null`, and is counted as an
issue; a file that does not have the expected structure stops the run. `--out` may not be inside `--raw`: inputs are
read-only. A component here is a *candidate group* — every reference sharing one key — not yet a
resolved component.

The rest of the pipeline (`run`, `evaluate`, `report`) is to be written during the build.

## Results

To be filled from `evaluate` output only.

## Known limits

To be completed when the build lands: what was dropped, and why. Known so far:

- **A lone separator is always the decimal mark.** `1,500` and `1.500` are both read as `1.5`,
  never as fifteen hundred: the comma is the decimal mark of the export (DECISIONS.md 24), and
  the dot is read the same way. `1.234,56` is refused as ambiguous rather than guessed, so the
  tool is stricter with two separators than with one. No value of the committed dataset is
  affected; an export that uses a thousands separator would be misread without an issue being
  raised.
- **A cost too small for a float is read as zero.** In `normalize`, a positive `unit_cost_eur`
  whose value underflows a float becomes `0.0` with no issue raised, where the string `"0"` is
  refused. Reaching it takes a cost written with some four hundred leading zeros, so no value of
  the committed dataset is affected and no realistic export carries one. The same underflow on
  quantities is caught and counted (#13); the cost path was left alone when the refocus of
  2026-09-21 froze the data layer (DECISIONS.md 29, issue #18, closed won't-do).

## How this was built

See `CLAUDE.md` (rules for the AI agents), `DECISIONS.md` (human decisions) and the commit
history.
