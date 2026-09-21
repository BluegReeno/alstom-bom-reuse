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
   older variants, the tool says which of its sub-assemblies already existed, and is scored
   beside two naive searches on the same data — by exact reference, and by designation. The gap
   between them is the measured value.

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

Answer the question — the whole pipeline, offline:

```bash
uv run bomreuse run --raw data/raw --out out
```

This is the command a client would be shown. It normalizes the raw files, decides which
references are the same component, builds the signature of every sub-assembly and plays the
newest variant as a new tender; it prints the answer as a table and writes
`out/normalized.json`, `out/resolution.json`, `out/findings.json`, `out/signatures.json` and
`out/predictions.json`. Same rule on the paths: `--out` may not be inside `--raw`.

Two references become one component when the stated foldings give them the same key —
uppercase, then `O`→`0`, `I`→`1`, `L`→`1`, then non-alphanumerics dropped. **There is no
string-distance matching anywhere**: in a Bill of Materials two references differing by one
character are often genuinely different parts, and a false *reused* is the worst error this
tool can make. Each group the key forms is then rated on its own coherence:

- *auto* — the rows agree; the group is one component;
- *review* — they share a key but disagree on designation, unit, supplier or cost. Still one
  component, and a finding: a part whose supplier or cost moves between variants is the same
  part, and the divergence is what makes a reuse unsafe;
- *reject* — the designations name different products; the group is split back apart.

On the committed dataset the command reports 160 candidate groups resolving to 163 canonical
components — 144 *auto*, 13 *review*, 3 *reject* — and 44 findings, 31 from resolution and 13
from the inconsistency checks below. Every finding names the rule that produced it, the
confidence that rule declares, and the rows of `bom.csv` it was read from.

### The backtest, on stdout

The signature of a sub-assembly is the multiset of *(canonical component, normalized quantity,
SI unit)* it contains, built on every merged group — `auto` and `review` alike, since a part
whose supplier or cost moves between variants is still that part; only a `reject` splits one.
The newest variant then plays the new tender: given **only the variants designed before it**,
each of its sub-assemblies comes out

- *reused* — an older signature is identical;
- *reusable* — an older signature is within the threshold, and the exact diff is shown;
- *specific* — neither.

The threshold is two numbers in `data/dataset_spec.toml`, written before the data was generated
and never tuned against a score; `run` reads them from `--spec`, which defaults to that
committed file. A sub-assembly whose lines the pipeline could not all read carries the count of
them on its row — an answer resting on part of a sub-assembly is not the claim an answer resting
on all of it makes — and no sub-assembly of the committed dataset is in that case. On the
committed dataset the command reports **8 reused, 5 reusable and 2 specific** of the newest
variant's 15 sub-assemblies, each naming the older sub-assembly the answer rests on:

```
backtest          C (bike car, new region, designed 2025-02-17) against A, B, D, E
  sub-assembly  designation                     class     from          difference
  C:0CCSA0315   bike module                     reusable  B:SA0215      B1KEH00K 8 pcs -> 6 pcs, B1KESTRAP 8 pcs -> 6 pcs
  C:0CCSA0314   floor and wall anchorage        specific
  C:SA0101      carbody shell                   reused    A:SA0101
```

Those counts are what the tool *finds*. How many of them are right, and how the two naive
searches do on the same data, is `evaluate`'s answer, in **Results** below.

### The inconsistencies, on stdout

The second half of the question. Each canonical component — the parts of a split group
included — is checked for rows that disagree on its unit, its supplier or its unit cost, after
normalization: `1000 mm` against `1 m`, or `12,50` against `12.50`, is agreement, and there is
no tolerance on cost because the dataset spec declares none. Each disagreement is one finding
saying which variants carry which value. The part stays merged and stays in the signatures: a
part whose supplier moves is still that part, and the disagreement is what a human must settle.

On the committed dataset the checks report **13 components whose rows disagree — 3 on unit, 5 on
supplier, 5 on cost**, printed by type with the first examples, all of them in
`out/findings.json`. They are the same 13 components resolution rated *review*: that finding
says the merge held despite a disagreement, this one says which value moved where. A *reused*
or *reusable* row of the backtest table whose parts carry one of them names those parts on its
row — 9 of the 13 reuse answers on the committed dataset:

```
  C:SA0104      hvac unit                       reused    A:SA0104      [check: HVACF11TER (supplier)]
inconsistencies   13 components whose rows disagree
  unit            3
    'LIGHT-CABLE' (component 11GHTCAB1E) has 2 different unit values: 'm' in A, B, C, D; 'pcs' in E.
```

### Scoring the answer

```bash
uv run bomreuse evaluate --ground-truth data/ground_truth/ground_truth.json
```

The only command that reads `data/ground_truth/`, and the only argument in the whole tool with no
default: the pipeline never sees that file, a static test over every other module enforces it,
and a runtime one runs the pipeline with the real ground truth laid out beside the raw files to
show it is not even opened. `evaluate` re-runs the pipeline rather than reading `out/`, so its
figures can never be a stale artifact's, and it writes nothing. `--raw` and `--spec` default to
the committed dataset and the committed contract. What it prints is **Results**, below.

The rest of the pipeline is to be written during the build: the notes, and the HTML report.

## Results

The one claim this build makes, measured. `bomreuse evaluate` plays the newest variant as a new
tender and scores the answer against the ground truth — which the pipeline never reads — beside
the two naive searches a sceptic would try first. All three answer the same 15 sub-assemblies,
under the same rule: an answer is right when the class is right **and** the older sub-assembly it
names is one the ground truth lists, any one of them being a valid source to reuse from
(DECISIONS.md 25). Rows carry the ground truth's words; `specific` is the prediction that answers
its `new`, because the tool can only observe that it found no match, never assert that none
exists (DECISIONS.md 30).

```bash
uv run bomreuse evaluate --ground-truth data/ground_truth/ground_truth.json
```

```
ground truth      data/ground_truth/ground_truth.json
backtest          C played as the new tender against A, B, D, E
  sub-assemblies  15 (reused 9, reusable 4, new 2)
  rows            the ground truth's labels; the prediction that answers 'new' is 'specific'
  a hit           the class is right, and the older sub-assembly named is one the ground truth lists

tool              signatures over the canonical components, against the variants designed earlier
  reused          precision 8/8       recall 8/9
  reusable        precision 4/5       recall 4/4
  new             precision 2/2       recall 2/2
  correct         14/15

exact reference   the raw reference matches an older variant's, character for character
  reused          precision 4/5       recall 4/9
  reusable        precision 0/0       recall 0/4
  new             precision 2/10      recall 2/2
  correct         6/15

same name         the raw designation matches an older variant's, case and spacing aside
  reused          precision 9/15      recall 9/9
  reusable        precision 0/0       recall 0/4
  new             precision 0/0       recall 0/2
  correct         9/15
```

**Reading it.** The tool answers 14 of the 15 correctly; the exact-reference search 6, the
same-name search 9.

- **Exact reference** is the search the client already has. It recovers 4 of the 9
  sub-assemblies that already existed and misses the other 5 — the ones the newest variant
  renumbered (`OCC-SA-0302`) or typo'd (`SA-O107`). Worse for a tender, it answers "not there"
  10 times and is right twice: 8 sub-assemblies it declares new are sitting in an older variant.
- **Same name** is the first objection a data engineer raises. On this data the designation is a
  near-perfect join key, so it finds every existing sub-assembly (recall 9/9) — and it finds one
  everywhere, including for the 4 that changed and the 2 that are genuinely new. Precision 9/15,
  and nothing at all on the two classes that decide what an engineer actually does: it cannot
  tell *identical* from *changed*, and it would propose reusing a toilet module and a floor
  anchorage that do not exist.
- **The tool** is the only one of the three that answers *reusable* at all, with the exact diff
  on every one of the 4 (4/4), and the only one that finds both genuinely new sub-assemblies
  (2/2) instead of inventing an ancestor for them.
- **Its one miss** is honest and worth keeping: `OCC-SA-0309`, floor and wall panels, is a
  *reused* sub-assembly reported as *reusable*. Variant C spells one of its parts
  `SEAT-FIX-KIT-447` where every other variant writes `SEAT-FIX-KIT-4471`, a dropped character no
  folding rule can reach and no string distance is allowed to guess at. The engineer is still
  pointed at the right older sub-assembly, with a one-part difference to check — which is what
  *reusable* means. Closing that gap would mean fuzzy matching, and a false *reused* is the worst
  error this tool can make.

No threshold was moved to produce these figures, and there is no regression floor in this build:
`evaluate` prints them and this section quotes them (DECISIONS.md 17, 29).

## Known limits

To be completed when the build lands: what was dropped, and why. Known so far:

- **A reference the folding rules cannot reach stays a second component.** The rules fold case,
  `O`/`I`/`L` and non-alphanumerics, and nothing else (DECISIONS.md 27): a dropped or transposed
  character — `SEAT-FIX-KIT-447` where every other variant writes `SEAT-FIX-KIT-4471` — leaves two
  components where there is one part. That is why one *reused* sub-assembly of the backtest comes
  out *reusable*, described in **Results**. How much resolution misses in total is not measured in
  this build (DECISIONS.md 29); it is the accepted cost of having no string distance anywhere,
  since a false *reused* is the worst error this tool can make.
- **A lone separator is always the decimal mark.** `1,500` and `1.500` are both read as `1.5`,
  never as fifteen hundred: the comma is the decimal mark of the export (DECISIONS.md 24), and
  the dot is read the same way. `1.234,56` is refused as ambiguous rather than guessed, so the
  tool is stricter with two separators than with one. No value of the committed dataset is
  affected; an export that uses a thousands separator would be misread without an issue being
  raised.
- **A transposition or a missing character is out of reach of resolution.** `BGI-2013` for
  `BGI-2031`, or `SEAT-FIX-KIT-447` for `SEAT-FIX-KIT-4471`, stay two components: no folding
  rule undoes them, and only string-distance matching would. That would also merge references
  that differ by one character and are genuinely different parts — the three `must_not_merge`
  pairs of `data/dataset_spec.toml` are exactly that case, and a false *reused* is the worst
  error this tool can make (`docs/ARCHITECTURE.md` A2). So the cost is accepted: the dataset
  plants both families on purpose, and since resolution scoring was cut on 2026-09-21
  (`DECISIONS.md` 29) the shortfall is named here rather than counted.
- **Two different products behind one key are told apart by their designations only.** The
  `reject` rule reads the words of the designation, so a key collision whose two products are
  described with the same words would still be merged. No case of the committed dataset is
  affected: the three planted pairs are described differently, which is what the pairs exist to
  test.
- **A cost too small for a float is read as zero.** In `normalize`, a positive `unit_cost_eur`
  whose value underflows a float becomes `0.0` with no issue raised, where the string `"0"` is
  refused. Reaching it takes a cost written with some four hundred leading zeros, so no value of
  the committed dataset is affected and no realistic export carries one. The same underflow on
  quantities is caught and counted (#13); the cost path was left alone when the refocus of
  2026-09-21 froze the data layer (DECISIONS.md 29, issue #18, closed won't-do).

## How this was built

See `CLAUDE.md` (rules for the AI agents), `DECISIONS.md` (human decisions) and the commit
history.
