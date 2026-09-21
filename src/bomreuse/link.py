"""Note facts to canonical components: the one place a note's raw reference is matched.

`notes.py` extracts and never matches; `checks.py` consumes facts already linked. This module
sits between them, and it is **the only caller of `resolve.match_reference` outside `resolve`
itself** (docs/ARCHITECTURE.md A7). A test asserts it, so the day a second matcher is written it
shows up as a failing test rather than as a quiet divergence — one folding rule, one place.

The matching is the resolution's, whole: a note writing `bgi 2031` reaches the component the BOM
spells `BGI-2031`, because `normalize.reference_key` folds both to one key (DECISIONS.md 27).
Nothing is added here — no string distance, no nearest match. A reference this pipeline does not
carry stays unlinked, and so does a word that merely had the shape of one: the fact is kept, with
an empty component list, and the count is on the screen `bomreuse run` prints.
"""

from bomreuse.model import LinkedFact, NoteFacts, Resolution
from bomreuse.notes import Extraction
from bomreuse.resolve import match_reference


def link(extraction: Extraction, resolution: Resolution) -> NoteFacts:
    """Every extracted fact, with the canonical components its raw reference reached.

    A split group hands back its parts rather than one of them (`resolve.Candidate`): the note
    cites a reference two products share, and choosing between them here would be the guess
    `resolve` refused to make.
    """
    facts = tuple(LinkedFact(fact=fact, components=_components(resolution, fact.component_ref)) for fact in extraction.facts)
    return NoteFacts(
        reader=extraction.reader,
        notes_read=extraction.notes_read,
        invalid_outputs=extraction.invalid_outputs,
        facts=facts,
    )


def _components(resolution: Resolution, raw_token: str) -> tuple[str, ...]:
    candidate = match_reference(resolution, raw_token)
    return () if candidate is None else tuple(component.id for component in candidate.components)


def linked_components(note_facts: NoteFacts) -> int:
    """How many facts reached at least one component: the other half of what the artifact counts."""
    return sum(1 for linked in note_facts.facts if linked.components)
