"""The FR/EN keyword fallback: the reader that makes the pipeline run with no network at all.

The notes below are written for this test file, from the patterns `CONTEXT.md` and the brief
quote. None of them is copied from `data/raw/notes.csv` or from the generator's note catalogue —
that is the whole point of the lexicon, and a test that read the dataset would undo it.

What the fallback gets wrong is tested too, in the last section: a reader whose limits are not
written down reads as a reader that has none.
"""

from datetime import date

import pytest

from bomreuse.model import FactKind, Note, NoteFact, RawDate
from bomreuse.notes import Extraction, KeywordReader, Reading, extract


def a_note(text: str, note_id: str = "N001", row_number: int = 1) -> Note:
    return Note(note_id=note_id, row_number=row_number, variant_id="A", date=RawDate(raw="2024-03-01", normalized=date(2024, 3, 1)), text=text)


def facts(text: str) -> tuple[NoteFact, ...]:
    return KeywordReader().read(a_note(text)).facts


def one_fact(text: str) -> NoteFact:
    found = facts(text)
    assert len(found) == 1, [fact.kind for fact in found]
    return found[0]


# --- the patterns the brief and CONTEXT.md quote ---------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Le joint BGI-2031 est remplacé par BGI-2045 depuis mars 2024.",
        "La grille HVAC-GRILLE-12 a été remplacée par HVAC-GRILLE-14.",
        "Seal BGI-2031 replaced by BGI-2045 on all variants.",
        "Bracket BGI-2031 superseded by BGI-2045.",
    ],
)
def test_a_replacement_names_the_part_and_what_replaces_it(text: str) -> None:
    fact = one_fact(text)
    assert fact.kind is FactKind.REPLACEMENT
    assert (fact.component_ref, fact.replacement_ref) in (("BGI-2031", "BGI-2045"), ("HVAC-GRILLE-12", "HVAC-GRILLE-14"))


@pytest.mark.parametrize(
    "text",
    [
        "Part HVAC-GRILLE-12 is obsolete since 2023.",
        "La référence HVAC-GRILLE-12 est obsolète depuis 2023.",
        "HVAC-GRILLE-12 discontinued by the supplier.",
        "HVAC-GRILLE-12 : ne plus commander, stock épuisé.",
    ],
)
def test_an_obsolescence_names_the_part_it_is_about(text: str) -> None:
    fact = one_fact(text)
    assert fact.kind is FactKind.OBSOLESCENCE
    assert fact.component_ref == "HVAC-GRILLE-12"
    assert fact.replacement_ref == "", "an obsolescence says a part is finished, not what takes its place"


@pytest.mark.parametrize(
    "text",
    [
        "Ne pas utiliser le rail SEAT-RAIL-1 sur les voitures 4 caisses.",
        "Do not use SEAT-RAIL-1 on 4-car trainsets.",
        "SEAT-RAIL-1 interdit sur les rames régionales bi-mode.",
    ],
)
def test_a_restriction_names_the_part_and_quotes_the_sentence_it_was_read_from(text: str) -> None:
    fact = one_fact(text)
    assert fact.kind is FactKind.RESTRICTION
    assert fact.component_ref == "SEAT-RAIL-1"
    assert fact.scope == text.rstrip(".")


def test_a_note_that_switches_language_mid_sentence_is_read_like_any_other() -> None:
    """The lexicon holds both languages in one list, so there is no language to detect."""
    found = facts("Le joint BGI-2031 is obsolete since 2023, ne pas utiliser sur les rames 4 caisses.")
    assert [fact.kind for fact in found] == [FactKind.OBSOLESCENCE, FactKind.RESTRICTION]
    assert {fact.component_ref for fact in found} == {"BGI-2031"}


def test_a_replacement_reads_the_part_before_the_cue_and_the_replacement_after_it() -> None:
    fact = one_fact("Sur la variante B, le joint BGI-2031 a été remplacé par BGI-2045 (fournisseur Artois).")
    assert (fact.component_ref, fact.replacement_ref) == ("BGI-2031", "BGI-2045")


def test_a_replacement_that_names_no_part_before_the_cue_produces_nothing() -> None:
    """A subject that had to be guessed is worse than no fact at all."""
    assert facts("Le joint a été remplacé par BGI-2045.") == ()


def test_a_replacement_with_nothing_after_the_cue_still_names_the_part_it_is_about() -> None:
    fact = one_fact("Le joint BGI-2031 sera remplacé par la nouvelle génération.")
    assert (fact.component_ref, fact.replacement_ref) == ("BGI-2031", "")


# --- what is not a fact, and what is not a reference -------------------------------------------------


def test_a_note_that_asserts_nothing_produces_nothing() -> None:
    assert facts("Contrôle qualité effectué sur le module vélo de la variante B, RAS.") == ()


def test_a_note_carrying_a_cue_but_no_reference_produces_nothing() -> None:
    assert facts("Ne pas utiliser les anciens joints sur les rames 4 caisses.") == ()


@pytest.mark.parametrize("text", ["Ce sous-ensemble est obsolète.", "Cette pièce est non-conforme et obsolète.", "Pièce obsolète depuis mars 2024."])
def test_a_hyphenated_word_or_a_date_is_not_read_as_a_reference(text: str) -> None:
    """`sous-ensemble` has the shape of a reference and `mars 2024` has the shape of another."""
    assert facts(text) == ()


def test_a_reference_is_carried_exactly_as_the_note_writes_it() -> None:
    """Raw, always: `notes.py` extracts and never matches, and `link.py` needs the characters the file holds."""
    fact = one_fact("Part Bgi-2031 is obsolete since 2023.")
    assert fact.component_ref == "Bgi-2031"


def test_a_fact_cites_the_note_it_was_read_from() -> None:
    fact = KeywordReader().read(a_note("BGI-2031 is obsolete since 2023.", note_id="N027", row_number=27)).facts[0]
    assert (fact.note_id, fact.row_number) == ("N027", 27)


def test_the_scope_of_a_long_restriction_is_cut_rather_than_pasted_whole() -> None:
    long_reason = "parce que " * 30
    fact = one_fact(f"Do not use SEAT-RAIL-1 on 4-car trainsets {long_reason}.")
    assert len(fact.scope) <= 120 and fact.scope.endswith("…")


# --- where the fallback is wrong, written down rather than patched -------------------------------------


def test_a_question_that_cites_a_part_next_to_a_cue_is_read_as_an_assertion() -> None:
    """The known false positive: a cue phrase and a reference in one sentence look like a fact.

    Reading this one correctly means reading the sentence, not the words in it — which is where
    an LLM earns its place. Extending the lexicon to catch it would fit the lexicon to the notes.
    """
    fact = one_fact("BGI-2031 obsolète ? Question ouverte, pas de décision à ce stade.")
    assert fact.kind is FactKind.OBSOLESCENCE, "the fallback asserts what the note only asks"


def test_a_fact_stated_in_words_the_lexicon_does_not_hold_is_missed() -> None:
    """The known false negative, and the other half of the same limit."""
    assert facts("Le fournisseur arrête la production de BGI-2031 fin 2025.") == ()


# --- reading every note -----------------------------------------------------------------------------


def test_every_note_is_read_and_counted_even_when_it_says_nothing() -> None:
    extraction = extract(
        [
            a_note("Le joint BGI-2031 est remplacé par BGI-2045.", note_id="N001", row_number=1),
            a_note("Contrôle qualité, RAS.", note_id="N002", row_number=2),
        ],
        KeywordReader(),
    )
    assert extraction == Extraction(
        reader="keyword",
        notes_read=2,
        invalid_outputs=0,
        facts=(NoteFact(note_id="N001", row_number=1, kind=FactKind.REPLACEMENT, component_ref="BGI-2031", replacement_ref="BGI-2045", scope=""),),
    )


def test_the_fallback_produces_nothing_it_has_to_throw_away() -> None:
    """It cannot emit an invalid output: what it reads, it built itself. The counter is for the model reader."""
    assert KeywordReader().read(a_note("BGI-2031 is obsolete.")).invalid_outputs == 0


def test_a_reader_is_asked_for_one_note_at_a_time() -> None:
    """A batch that a single invalid output poisons loses the other thirty-nine (docs/ARCHITECTURE.md A6)."""
    seen: list[str] = []

    class Counting:
        name = "counting"

        def read(self, note: Note) -> Reading:
            seen.append(note.note_id)
            return Reading(facts=(), invalid_outputs=0)

    extract([a_note("x", note_id="N001"), a_note("y", note_id="N002")], Counting())
    assert seen == ["N001", "N002"]
