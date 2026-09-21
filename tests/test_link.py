"""Linking: a note's raw reference becomes a canonical component, or stays where it is.

Every case goes through the real path — raw CSV cells, `normalize`, `resolve` — so that no test
hands `link` a reference key of its own making.
"""

from datetime import date

import pytest

from bomreuse.link import link, linked_components
from bomreuse.model import FactKind, Note, NoteFact, RawDate
from bomreuse.notes import Extraction, KeywordReader, extract
from bomreuse.resolve import resolve
from test_resolve import dataset_of

Row = tuple[str, str, str, str, str, str]

_SEAL: Row = ("BGI-2031", "Gangway door seal", "4", "pcs", "Artois Polymères", "81,00")


def a_fact(reference: str, kind: FactKind = FactKind.OBSOLESCENCE) -> NoteFact:
    return NoteFact(note_id="N001", row_number=1, kind=kind, component_ref=reference, replacement_ref="", scope="")


def an_extraction(*facts: NoteFact) -> Extraction:
    return Extraction(reader="keyword", notes_read=1, invalid_outputs=0, facts=facts)


def components_of(reference: str, *rows: Row) -> tuple[str, ...]:
    resolution, _ = resolve(dataset_of(*rows))
    return link(an_extraction(a_fact(reference)), resolution).facts[0].components


@pytest.mark.parametrize("reference", ["BGI-2031", "bgi 2031", "BG1-2O31", " Bgi-2031 "])
def test_a_note_reaches_the_component_through_any_spelling_the_resolution_folds(reference: str) -> None:
    """The folding is `normalize`'s and the matching is `resolve`'s: this module adds nothing to either."""
    assert components_of(reference, _SEAL) == ("BG12031",)


def test_a_reference_the_bom_does_not_carry_stays_unlinked() -> None:
    assert components_of("BGI-9999", _SEAL) == ()


def test_a_word_that_only_looked_like_a_reference_costs_nothing() -> None:
    """The fallback's false candidates end here, unlinked and visible, rather than in a finding."""
    assert components_of("sous-ensemble", _SEAL) == ()


def test_a_split_group_hands_back_its_parts_rather_than_one_of_them() -> None:
    """`resolve` refused to choose between two products sharing a key; `link` does not choose either."""
    assert components_of(
        "SEAT-RAIL-1",
        ("SEAT-RAIL-I", "Floor rail, stainless steel", "6", "pcs", "Atelier Lys Métal", "312.00"),
        ("SEAT-RAIL-1", "Mounting rail, aluminium, mark 1", "2", "pcs", "Atelier Lys Métal", "121,00"),
    ) == ("SEATRA111#1", "SEATRA111#2")


def test_what_the_reader_said_of_itself_travels_with_the_facts() -> None:
    """A finding read off the artifact must say which reader produced the fact behind it."""
    resolution, _ = resolve(dataset_of(_SEAL))
    extraction = Extraction(reader="llm:gemma4:12b-mlx", notes_read=40, invalid_outputs=3, facts=(a_fact("BGI-2031"),))
    linked = link(extraction, resolution)
    assert (linked.reader, linked.notes_read, linked.invalid_outputs) == ("llm:gemma4:12b-mlx", 40, 3)


def test_every_fact_survives_linking_in_the_order_it_was_read() -> None:
    resolution, _ = resolve(dataset_of(_SEAL))
    facts = (a_fact("BGI-2031"), a_fact("BGI-9999"), a_fact("BGI-2031", FactKind.RESTRICTION))
    linked = link(an_extraction(*facts), resolution)
    assert tuple(entry.fact for entry in linked.facts) == facts
    assert linked_components(linked) == 2


def test_the_whole_path_from_a_note_to_a_component_holds() -> None:
    """The fallback reads the note, `link` places it: the two halves, joined once.

    `Bgi-2031` is a spelling neither half handles alone — the reader keeps the characters the
    note holds, and the resolution's key folds them onto the component the BOM writes `BGI-2031`.
    """
    note = Note(
        note_id="N001",
        row_number=1,
        variant_id="A",
        date=RawDate(raw="2024-03-01", normalized=date(2024, 3, 1)),
        text="Le joint Bgi-2031 est obsolète depuis 2023, ne pas utiliser sur les rames 4 caisses.",
    )
    resolution, _ = resolve(dataset_of(_SEAL))
    linked = link(extract([note], KeywordReader()), resolution)
    assert [(entry.fact.kind, entry.components) for entry in linked.facts] == [
        (FactKind.OBSOLESCENCE, ("BG12031",)),
        (FactKind.RESTRICTION, ("BG12031",)),
    ]
