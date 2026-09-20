"""The ground-truth schema accepts what the generator may say, and refuses the rest loudly."""

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from bomreuse.ground_truth import GroundTruth, dump_ground_truth, load_ground_truth, render_ground_truth


def minimal() -> dict[str, Any]:
    """A small ground truth that is valid, and touches every table."""
    diff = {
        "added": [{"true_component_id": "TRUE-0003", "quantity": 2.0, "unit": "pcs"}],
        "removed": [],
        "quantity_changed": [{"true_component_id": "TRUE-0001", "left": 8.0, "right": 6.0, "unit": "pcs"}],
    }
    return {
        "schema_version": "1",
        "spec_version": "1",
        "seed": 7,
        "newest_variant": "C",
        "components": [
            {"true_component_id": "TRUE-0001", "designation": "Hook", "base_unit": "pcs", "raw_references": ["HK-1", "hk 1"]},
            {"true_component_id": "TRUE-0002", "designation": "Rail", "base_unit": "m", "raw_references": ["RL-I"]},
            {"true_component_id": "TRUE-0003", "designation": "Rail mk1", "base_unit": "m", "raw_references": ["RL-1"]},
        ],
        "typo_families": [
            {"family_id": "case", "true_component_id": "TRUE-0001", "within_rules_reach": True, "emitted": ["hk 1"]}
        ],
        "must_not_merge": [
            {
                "id": "rail",
                "left_reference": "RL-I",
                "right_reference": "RL-1",
                "left_true_component": "TRUE-0002",
                "right_true_component": "TRUE-0003",
            }
        ],
        "backtest": [
            {
                "variant_id": "C",
                "sub_assembly_ref": "OCC-SA-0001",
                "sub_assembly_designation": "Bike module",
                "label": "reusable",
                "planted_as": "near_reuse",
                "story_case_id": None,
                "ancestors": [{"variant_id": "B", "sub_assembly_ref": "SA-0001", "diff": diff}],
                "unsafe": [{"true_component_id": "TRUE-0001", "note_id": "N001"}],
            },
            {
                "variant_id": "C",
                "sub_assembly_ref": "OCC-SA-0002",
                "sub_assembly_designation": "Shell",
                "label": "reused",
                "planted_as": "hidden_reuse",
                "story_case_id": None,
                "ancestors": [{"variant_id": "A", "sub_assembly_ref": "SA-0002", "diff": None}],
                "unsafe": [],
            },
            {
                "variant_id": "C",
                "sub_assembly_ref": "OCC-SA-0003",
                "sub_assembly_designation": "Toilet",
                "label": "new",
                "planted_as": "new",
                "story_case_id": None,
                "ancestors": [],
                "unsafe": [],
            },
        ],
        "defects": [
            {
                "defect_type": "duplicate_reference",
                "true_component_id": "TRUE-0001",
                "variant_pair": ["B", "B"],
                "evidence_line_ids": ["L00001", "L00002"],
                "note_id": None,
            },
            {
                "defect_type": "note_contradiction",
                "true_component_id": "TRUE-0001",
                "variant_pair": ["A", "C"],
                "evidence_line_ids": ["L00003"],
                "note_id": "N001",
            },
        ],
        "notes": [
            {
                "note_id": "N001",
                "language": "mixed",
                "facts": [
                    {
                        "fact_type": "obsolescence",
                        "true_component_id": "TRUE-0001",
                        "cited_reference": "hk 1",
                        "replaced_by_true_component_id": None,
                        "effective_date": "2024-01-01",
                        "scope": None,
                    }
                ],
            },
            {"note_id": "N002", "language": "fr", "facts": []},
        ],
    }


# --- what is accepted ------------------------------------------------------------------------


def test_a_valid_ground_truth_round_trips_through_the_file(tmp_path: Path) -> None:
    truth = GroundTruth.model_validate(minimal())
    path = tmp_path / "deep" / "gt.json"
    dump_ground_truth(truth, path)
    assert load_ground_truth(path) == truth


def test_the_same_ground_truth_renders_to_the_same_bytes() -> None:
    first = render_ground_truth(GroundTruth.model_validate(minimal()))
    second = render_ground_truth(GroundTruth.model_validate(minimal()))
    assert first == second
    assert first.endswith("}\n")


def test_a_variant_pair_survives_json_as_a_sorted_pair(tmp_path: Path) -> None:
    """JSON has no tuple: the pair is written as a list and must come back as the same key."""
    path = tmp_path / "gt.json"
    dump_ground_truth(GroundTruth.model_validate(minimal()), path)
    assert load_ground_truth(path).defects[0].variant_pair == ("B", "B")


def test_a_pair_may_name_the_same_variant_twice() -> None:
    """Two spellings of one part inside one variant is still a duplicate reference."""
    truth = GroundTruth.model_validate(minimal())
    assert truth.defects[0].key == ("duplicate_reference", "TRUE-0001", ("B", "B"))


# --- what is refused -------------------------------------------------------------------------


def _shared_raw_string(data: dict[str, Any]) -> None:
    data["components"][1]["raw_references"].append("HK-1")


def _new_with_an_ancestor(data: dict[str, Any]) -> None:
    data["backtest"][2]["ancestors"] = [{"variant_id": "A", "sub_assembly_ref": "SA-9", "diff": None}]


def _reusable_without_diff(data: dict[str, Any]) -> None:
    data["backtest"][0]["ancestors"][0]["diff"] = None


def _reused_with_a_diff(data: dict[str, Any]) -> None:
    data["backtest"][1]["ancestors"][0]["diff"] = data["backtest"][0]["ancestors"][0]["diff"]


def _reused_without_ancestor(data: dict[str, Any]) -> None:
    data["backtest"][1]["ancestors"] = []


def _unsorted_pair(data: dict[str, Any]) -> None:
    data["defects"][1]["variant_pair"] = ["C", "A"]


def _duplicate_defect_key(data: dict[str, Any]) -> None:
    data["defects"].append(copy.deepcopy(data["defects"][0]))


def _unknown_id_in_a_defect(data: dict[str, Any]) -> None:
    data["defects"][0]["true_component_id"] = "TRUE-9999"


def _bad_id_format(data: dict[str, Any]) -> None:
    data["components"][0]["true_component_id"] = "TRUE-42"


def _unknown_extra_key(data: dict[str, Any]) -> None:
    data["components"][0]["canonical_key"] = "HK1"


def _unknown_note_in_a_defect(data: dict[str, Any]) -> None:
    data["defects"][1]["note_id"] = "N404"


def _contradiction_without_note(data: dict[str, Any]) -> None:
    data["defects"][1]["note_id"] = None


def _pair_reference_never_emitted(data: dict[str, Any]) -> None:
    data["must_not_merge"][0]["left_reference"] = "RL-l"


def _family_string_never_emitted(data: dict[str, Any]) -> None:
    data["typo_families"][0]["emitted"] = ["HK_1"]


def _note_cites_a_foreign_string(data: dict[str, Any]) -> None:
    data["notes"][0]["facts"][0]["cited_reference"] = "RL-1"


def _label_on_an_older_variant(data: dict[str, Any]) -> None:
    data["backtest"][2]["variant_id"] = "A"


def _stale_schema(data: dict[str, Any]) -> None:
    data["schema_version"] = "0"


def _unknown_base_unit(data: dict[str, Any]) -> None:
    data["components"][1]["base_unit"] = "mm"


def _date_not_iso(data: dict[str, Any]) -> None:
    data["notes"][0]["facts"][0]["effective_date"] = "01/01/2024"


VIOLATIONS: list[tuple[Callable[[dict[str, Any]], None], str]] = [
    (_shared_raw_string, "injective"),
    (_new_with_an_ancestor, "labelled 'new'"),
    (_reusable_without_diff, "carries no diff"),
    (_reused_with_a_diff, "must not carry a diff"),
    (_reused_without_ancestor, "lists no ancestor"),
    (_unsorted_pair, "not sorted"),
    (_duplicate_defect_key, "appears twice"),
    (_unknown_id_in_a_defect, "TRUE-9999"),
    (_bad_id_format, "TRUE-42"),
    (_unknown_extra_key, "canonical_key"),
    (_unknown_note_in_a_defect, "N404"),
    (_contradiction_without_note, "must name its note"),
    (_pair_reference_never_emitted, "RL-l"),
    (_family_string_never_emitted, "HK_1"),
    (_note_cites_a_foreign_string, "RL-1"),
    (_label_on_an_older_variant, "not the newest"),
    (_stale_schema, "schema_version"),
    (_unknown_base_unit, "base_unit"),
    (_date_not_iso, "01/01/2024"),
]


@pytest.mark.parametrize(("break_it", "names"), VIOLATIONS, ids=[v[0].__name__.lstrip("_") for v in VIOLATIONS])
def test_each_rule_refuses_its_violation_and_names_the_offender(
    break_it: Callable[[dict[str, Any]], None], names: str
) -> None:
    data = minimal()
    break_it(data)
    with pytest.raises(ValidationError) as caught:
        GroundTruth.model_validate(data)
    assert names in str(caught.value)


def test_a_loaded_ground_truth_cannot_be_edited_in_place() -> None:
    truth = GroundTruth.model_validate(minimal())
    with pytest.raises(ValidationError):
        truth.seed = 8  # type: ignore[misc]
