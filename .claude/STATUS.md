# STATUS — alstom-bom-reuse

Last updated: 2026-09-20

## Current Focus
Architecture decided (`docs/ARCHITECTURE.md`). Next: the 6 GitHub issues, then the build.

## In Progress
- [ ] Planning pass — PRD (done), architecture (done), 6 GitHub issues
- [ ] `DECISIONS.md` lines 19-20 to write by hand: pydantic scoped to two boundaries; R5's
      auto/review/reject now rates group coherence

## Done
- [x] Framing committed: rules, problem statement, data requirements, 16 decisions
- [x] `docs/PRD.md` — one page, assumptions marked
- [x] `docs/ARCHITECTURE.md` — 7 open calls settled, 2 spikes named — 2026-09-20

## Backlog
- [ ] #1 Synthetic generator + planted defects + ground truth
- [ ] #2 Ingest + normalize + entity model
- [ ] #3 Resolution + signatures (reused / reusable) + inconsistencies + evaluation
- [ ] #4 LLM note extraction (glm cloud vs gemma local) + keyword fallback
- [ ] #5 HTML report
- [ ] #6 README, fresh-clone check, push

## Note
The build runs in slices across several sessions. This file carries state, not elapsed time.
