"""Note extraction: what a free-text note asserts about a component, in the note's own words.

One task, and one only (docs/ARCHITECTURE.md A6): turn a note into zero or more `NoteFact`s —
a replacement, an obsolescence, a restriction — each citing the note it was read from. Nothing
here matches a reference against the BOM: the facts carry the **raw** string the note writes,
and `link.py` is the only module that turns one into a canonical component (A7).

Two readers implement the same protocol:

- `KeywordReader`, below, is what makes CLAUDE.md rule 5 hold: the whole pipeline runs with no
  network at all. It is the default, and it is not a degraded mode — it is the offline path.
- `ModelReader` reads the same notes through one local model. It is opt-in, because a tool whose
  demo needs a server running is a tool that does not demo.

**The lexicon below was written from the note patterns the brief and `CONTEXT.md` quote** —
*remplacé par…*, *obsolete since…*, *ne pas utiliser sur…*, *do not use on 4-car* — and from
nothing else. `data/raw/notes.csv` and the generator's note catalogue were not opened while
writing it, deliberately: a lexicon fitted to the forty synthetic notes would score whatever the
build asked of it and would measure nothing. What it misses on the committed dataset is a
result, reported in the README, not a bug to patch.

What it cannot do is the honest part of the answer to "where does an LLM earn its place?". It
reads cue phrases and reference-shaped tokens; it does not read a sentence. A note citing a part
next to a stock phrase while asserting nothing — a proposal that was refused, a question still
open — looks exactly like a note asserting it.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Protocol

from bomreuse.model import FactKind, Note, NoteFact


@dataclass(frozen=True, slots=True)
class Reading:
    """What a reader made of one note.

    `invalid_outputs` counts what the reader produced and could not use. It is zero for a reader
    that cannot produce anything unusable, and the point of the field is the one that can.
    """

    facts: tuple[NoteFact, ...]
    invalid_outputs: int


class NoteReader(Protocol):
    """One note per call (A6). A batch that a single invalid output poisons loses the other thirty-nine."""

    #: How the reader is named in the artifact and on a finding: a reviewer must know which one ran.
    name: str

    def read(self, note: Note) -> Reading: ...


@dataclass(frozen=True, slots=True)
class Extraction:
    """Every fact the reader found in the notes, and what it cost to find them."""

    reader: str
    notes_read: int
    invalid_outputs: int
    facts: tuple[NoteFact, ...]


def extract(notes: Iterable[Note], reader: NoteReader) -> Extraction:
    """Read every note, one call at a time, and keep what each one asserts."""
    facts: list[NoteFact] = []
    invalid = 0
    read = 0
    for note in notes:
        read += 1
        reading = reader.read(note)
        facts.extend(reading.facts)
        invalid += reading.invalid_outputs
    return Extraction(reader=reader.name, notes_read=read, invalid_outputs=invalid, facts=tuple(facts))


# --- the FR/EN keyword fallback ------------------------------------------------------------------

#: The cue phrases of each kind, French and English side by side in one list per kind: a note may
#: switch language inside one sentence, so there is no language to detect and nothing to branch on.
_CUES: Final[dict[FactKind, tuple[str, ...]]] = {
    FactKind.REPLACEMENT: (
        "remplacé par",
        "remplacée par",
        "remplacés par",
        "remplacées par",
        "remplacer par",
        "remplacement par",
        "replaced by",
        "replaced with",
        "superseded by",
    ),
    FactKind.OBSOLESCENCE: (
        "obsolète",
        "obsolete",
        "ne plus utiliser",
        "ne plus commander",
        "ne plus approvisionner",
        "fin de vie",
        "discontinued",
        "end of life",
        "no longer available",
        "no longer ordered",
    ),
    FactKind.RESTRICTION: (
        "ne pas utiliser",
        "ne pas monter",
        "interdit sur",
        "interdite sur",
        "do not use",
        "not to be used",
        "must not be used",
        "not allowed on",
    ),
}

#: Each cue as a pattern over the raw text, so a match keeps the offsets of the characters the
#: note actually holds — the references a fact carries are raw, and an offset into a case-folded
#: copy would not point at them. A space in a cue matches any run of whitespace: an export wraps.
_CUE_PATTERNS: Final[dict[FactKind, re.Pattern[str]]] = {
    kind: re.compile("|".join(re.escape(cue).replace(r"\ ", r"\s+") for cue in cues), re.IGNORECASE)
    for kind, cues in _CUES.items()
}

#: What a reference looks like in running text: a hyphenated or underscored token (`BGI-2031`,
#: `HVAC-GRILLE-12`, `BRK-CTRL-VALVE`), or letters run into digits (`SA0101`, `BGI 2031`).
#: The second branch is uppercase-only on purpose: `mars 2024` has the shape of the first and is
#: a date. A lower-cased reference written with a space is out of reach, and stays out of reach.
_REFERENCE: Final[re.Pattern[str]] = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)+\b|\b[A-Z]{2,}[ ]?[0-9]{2,}\b")

#: Where a sentence ends, for the fragment a restriction is quoted with.
_SENTENCE_END: Final[re.Pattern[str]] = re.compile(r"[.;!?\n]")

#: How much of that sentence is quoted. Long enough for "sur les rames 4 caisses", short enough
#: that the fragment stays a label on a row rather than the note pasted twice.
_SCOPE_LIMIT: Final[int] = 120


class KeywordReader:
    """Cue phrases and reference-shaped tokens, and no interpretation beyond that.

    One fact per kind at most, per note. The subject of an obsolescence or a restriction is the
    **first** reference the note names, and the subject of a replacement is the last reference
    before the cue, its replacement the first one after: that is the whole of the reasoning, and
    saying more about it would be describing a sentence parser this is not.

    A token that only looks like a reference — a hyphenated French word carrying a digit — costs
    nothing: `link.py` finds it in no BOM and the fact is kept unlinked, which is visible in the
    artifact. What does cost is a note that cites a real part while asserting nothing.
    """

    name: Final[str] = "keyword"

    def read(self, note: Note) -> Reading:
        references = [match for match in _REFERENCE.finditer(note.text) if _reference_shaped(match.group())]
        facts = [fact for kind in FactKind if (fact := self._fact(note, kind, references)) is not None]
        return Reading(facts=tuple(facts), invalid_outputs=0)

    def _fact(self, note: Note, kind: FactKind, references: list[re.Match[str]]) -> NoteFact | None:
        cue = _CUE_PATTERNS[kind].search(note.text)
        if cue is None or not references:
            return None
        if kind is FactKind.REPLACEMENT:
            return _replacement(note, cue, references)
        scope = _sentence_around(note.text, cue.start()) if kind is FactKind.RESTRICTION else ""
        return NoteFact(
            note_id=note.note_id,
            row_number=note.row_number,
            kind=kind,
            component_ref=references[0].group(),
            replacement_ref="",
            scope=scope,
        )


def _replacement(note: Note, cue: re.Match[str], references: list[re.Match[str]]) -> NoteFact | None:
    """`X remplacé par Y`: the part is what stands before the cue, the replacement what follows it.

    No reference before the cue means the note names no part to replace, and a fact whose subject
    had to be guessed is worse than no fact.
    """
    before = [match for match in references if match.end() <= cue.start()]
    after = [match for match in references if match.start() >= cue.end()]
    if not before:
        return None
    return NoteFact(
        note_id=note.note_id,
        row_number=note.row_number,
        kind=FactKind.REPLACEMENT,
        component_ref=before[-1].group(),
        replacement_ref=after[0].group() if after else "",
        scope="",
    )


def _reference_shaped(token: str) -> bool:
    """A digit somewhere, or nothing but capitals: enough to keep `sous-ensemble` out of the catalogue."""
    return any(character.isdigit() for character in token) or token == token.upper()


def _sentence_around(text: str, position: int) -> str:
    """The sentence the cue sits in, whitespace collapsed, for a human to read on the finding."""
    end = _SENTENCE_END.search(text, position)
    start = max((match.end() for match in _SENTENCE_END.finditer(text, 0, position)), default=0)
    sentence = " ".join(text[start : end.start() if end else len(text)].split())
    return sentence if len(sentence) <= _SCOPE_LIMIT else sentence[: _SCOPE_LIMIT - 1].rstrip() + "…"
