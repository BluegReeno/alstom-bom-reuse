# CONTEXT — alstom-bom-reuse

Working context for this repository. Kept current as the build progresses.

## The pilot (fictional)

- **Client**: Alstom, Valenciennes cluster, regional trains. In reality the regional
  double-deck trains (Regio 2N / Omneo) are built at the Crespin plant.
- **Pilot**: 3 weeks on the Cognyx platform. Scope: help engineering teams reuse existing
  sub-assemblies across train variants instead of re-designing and re-costing them at every
  tender.
- **Stakeholders**: Bruno Maréchal, Engineering Director and pilot sponsor — short on time,
  wants a value story, allergic to jargon. Thomas Lindqvist, lead data engineer — knows the
  data inside out, scrutinizes quality and maintainability, including of AI-written code.
- **Constraint**: eventually nothing leaves Alstom's network. The tool must run offline.

## What the data looks like (and what we plant)

Multi-variant BOM + free-text technical notes, "dirtier than advertised":

- duplicated references with typos (`BGI-2031` / `BG1-2031` / `bgi 2031`, trailing spaces);
- mixed units (mm / m, kg / g, pcs / units / "u") and decimal commas (`1,5`);
- notes switching between French and English, sometimes inside one note;
- the same component with different suppliers or costs across variants;
- notes contradicting the BOM ("remplacé par…", "obsolete since…", "do not use on 4-car");
- near-identical sub-assemblies differing by 1–3 parts: the "reusable" case;
- the newest variant re-designs sub-assemblies that already existed in older ones — a
  miniature of the pilot's main success criterion (backtest on a past tender).

Target size: 4–6 variants of a regional-train intermediate car, ~100–250 BOM lines each
(~500–1,500 in total), ~40 notes.

- **What a variant is**: one intermediate-car configuration (standard, bike car, bi-mode, other
  regions), not a whole trainset.
- **The story**: A (standard), B (bike car), C (newest: a bike car for a new region). The other
  1–3 variants make the reuse statistics meaningful.
- **C is an eBOM**, as designed. Its spec (region, seats, bike spaces, date) is variant
  metadata, used for the story and optionally for the 2 % bike-space rule; the tool matches
  sub-assemblies, not requirements.
- **No engineer review in the build**: the pilot's loop where rejected matches become test
  cases is replaced by the ground truth.

## What the data must let us prove

The problem (see README): for a given variant, find every sub-assembly that already exists in
the other variants. The generator is designed backwards from it:

- **Chronology**: each variant has a design date and a context (region, seats, bike spaces,
  electric / bi-mode). The newest is the "new tender" for the backtest.
- **Hidden reuse**: some sub-assemblies of the newest variant are identical in content to older
  ones but carry new or typo'd references, so an exact-reference search misses them.
- **Near-reuse**: some differ from an older sub-assembly by 1–3 parts (e.g. the bike module
  with 2 fewer hooks).
- **Genuinely new**: some are new (e.g. a new anchorage). These negatives make precision mean
  something.
- **Unsafe reuse**: at least one matched older sub-assembly contains a part a note declares
  obsolete or replaced: "reusable, but check".
- **Backtest ground truth**: for each sub-assembly of the newest variant, the expected answer —
  existing equivalent (with its id), reusable (with the diff), or new.
- **Baseline**: `evaluate` compares the tool with a naive exact-reference search on the same
  data. The gap is the measured value; no invented figure.

## Domain vocabulary

Regional train car sub-assemblies: carbody shell, motor and trailer bogies, traction
converter, pantograph, braking unit, auxiliary converter, HVAC unit, passenger doors,
couplers and gangways, seating module, toilet module, passenger information system (PIS),
lighting, floor and wall panels, bike module.

## The worked example: standard car vs bike car

Two variants of the same intermediate car:

| Sub-assembly | Standard car (A) | Bike / multi-purpose car (B) | Reuse status |
| --- | --- | --- | --- |
| Shell, bogies, doors, HVAC, traction | Standard | Same | Identical: reuse as is |
| Seating module | Fixed seats | Fewer fixed seats + tip-up seats | Reusable: same seat, different count |
| Floor and wall anchorage | Seat rails | Seat rails + bike-hook anchor points | Variant-specific |
| Bike module (hooks, racks) | — | 4–8 spaces | Variant-specific, reusable next time |
| PIS signage, pictograms | Standard | Bike pictograms | Same part, small change |

Real-world grounding: French regional trains ordered after March 2021 need bike spaces equal
to 2 % of fixed seats (min 4, max 8), so each region's seat count gives a different bike zone.
A new variant C (bike car for another region) should come out as: most sub-assemblies reused
from A and B, the bike module reused from B, only the anchorage new.

## Pilot success criteria (what the tool stages in miniature)

1. Backtest on a past tender: given only older variants, which sub-assemblies of the newest
   one were re-done although an equivalent existed?
2. Engineer validation: acceptance rate of proposals reviewed by the client's engineers.
3. Optional: time to answer "do we already have this?" on a live tender.

## Status

- 2026-09-19 — directory prepared: CLAUDE.md, CONTEXT.md, DECISIONS.md, case brief. No git
  repository yet: `git init` and the first commit start the 4-hour build clock.
