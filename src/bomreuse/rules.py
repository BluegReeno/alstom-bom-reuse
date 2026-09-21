"""The rule catalogue: `rule_id -> description -> confidence`, versioned next to the rules.

R11 asks every finding to carry the rule that produced it and a confidence, and [A5] fixes what
that confidence is: **a constant per rule, reported and never thresholded in this build**. It is
a declared property of the rule, not a measurement — nothing here is computed from the data, and
nothing downstream compares it against a cut-off.

The constants form a ladder, and the ladder is the whole justification for their values: a rule
loses confidence as it stops reading exact strings and starts reading free text.

| Reads | Example | Confidence |
| --- | --- | --- |
| a key two rows literally share | duplicate reference | 0.95 |
| a key they share, plus values that literally differ | supplier, cost or unit conflict | 0.90 |
| a key they share, plus a judgement on designations | the group is two products | 0.70 |
| free text, and a reference matched out of it | a note contradicts the BOM | 0.60 |

The bottom rung is where the notes layer lands, and it lands there whichever reader produced the
fact: the confidence is a property of the rule, not a measurement of the reader, and the finding
says which reader ran (#6). A note is free text, read by a keyword lexicon or by a model, and
neither can be trusted the way two rows sharing a key can.

The residual doubt at the top of the ladder is real and named: the folding rules of
`normalize.reference_key` collapse `I`/`1`, `O`/`0` and `L`/`1`, so two references sharing a key
can still be two products (DECISIONS.md 27). That is what the bottom of the ladder is for.

The resolution rules came first, `checks` added the three conflict rules, and the notes layer
added the three contradiction rules. Each issue extends the catalogue and never redefines an
entry already in it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from bomreuse.model import Finding, SourceRow

#: Bumped when a rule's meaning or confidence changes, so a stored finding can be read against
#: the catalogue it was emitted from. Adding a rule does not change what the existing ones say.
CATALOGUE_VERSION: Final[str] = "1"


@dataclass(frozen=True, slots=True)
class Rule:
    """One entry of the catalogue. `confidence` is a constant, not a score."""

    id: str
    description: str
    confidence: float

    def finding(self, subject: str, message: str, source_rows: tuple[SourceRow, ...]) -> Finding:
        """The only way a finding is built, so its id and its confidence cannot drift from the catalogue."""
        return Finding(rule_id=self.id, confidence=self.confidence, subject=subject, message=message, source_rows=source_rows)


DUPLICATE_REFERENCE: Final[Rule] = Rule(
    id="resolution.duplicate_reference",
    description="Several spellings of one reference share a canonical key and are one component.",
    confidence=0.95,
)

GROUP_CONFLICT: Final[Rule] = Rule(
    id="resolution.group_conflict",
    description="Rows sharing a canonical key disagree on designation, unit, supplier or cost; they stay one component.",
    confidence=0.90,
)

GROUP_SPLIT: Final[Rule] = Rule(
    id="resolution.group_split",
    description="Designations sharing a canonical key describe different products; the group is split back apart.",
    confidence=0.70,
)

UNIT_CONFLICT: Final[Rule] = Rule(
    id="checks.unit_conflict",
    description="Rows of one canonical component carry it in different units after normalization: one of them counts something else.",
    confidence=0.90,
)

SUPPLIER_CONFLICT: Final[Rule] = Rule(
    id="checks.supplier_conflict",
    description="Rows of one canonical component name different suppliers.",
    confidence=0.90,
)

COST_CONFLICT: Final[Rule] = Rule(
    id="checks.cost_conflict",
    description="Rows of one canonical component give it different unit costs.",
    confidence=0.90,
)

NOTE_OBSOLESCENCE: Final[Rule] = Rule(
    id="checks.note_obsolescence",
    description="A note declares a component obsolete, and the BOM still carries it.",
    confidence=0.60,
)

NOTE_REPLACEMENT: Final[Rule] = Rule(
    id="checks.note_replacement",
    description="A note says a component has been replaced, and the BOM still carries the one it replaces.",
    confidence=0.60,
)

NOTE_RESTRICTION: Final[Rule] = Rule(
    id="checks.note_restriction",
    description="A note forbids a component on some configuration, and the BOM carries it.",
    confidence=0.60,
)

_RULES: Final[tuple[Rule, ...]] = (
    DUPLICATE_REFERENCE,
    GROUP_CONFLICT,
    GROUP_SPLIT,
    UNIT_CONFLICT,
    SUPPLIER_CONFLICT,
    COST_CONFLICT,
    NOTE_OBSOLESCENCE,
    NOTE_REPLACEMENT,
    NOTE_RESTRICTION,
)

#: The catalogue itself. A finding whose `rule_id` is not a key here is not traceable, and a test
#: says so of every finding the pipeline emits.
CATALOGUE: Final[Mapping[str, Rule]] = {rule.id: rule for rule in _RULES}
