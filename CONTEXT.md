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

Target size: ~500–1,500 BOM lines, 4–6 variants, a few dozen notes.

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
