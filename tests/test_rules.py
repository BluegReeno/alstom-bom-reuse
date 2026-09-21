"""The rule catalogue is what makes a finding traceable, so it is checked like a contract.

R11 and [A5]: every finding names a rule, the rule carries a constant confidence, and the
catalogue is the one place both are declared. A duplicate id or a confidence outside 0-1 would
be discovered in the report, weeks later.
"""

import pytest

from bomreuse.rules import CATALOGUE, CATALOGUE_VERSION, Rule


def test_the_catalogue_is_keyed_by_the_rules_own_ids() -> None:
    assert CATALOGUE
    for rule_id, rule in CATALOGUE.items():
        assert rule_id == rule.id


@pytest.mark.parametrize("rule", sorted(CATALOGUE.values(), key=lambda rule: rule.id), ids=lambda rule: rule.id)
def test_every_rule_is_declared_in_full(rule: Rule) -> None:
    assert rule.id.strip() == rule.id and rule.id
    assert rule.description.strip().endswith("."), "a description a reader can put in a report, not a label"
    assert 0.0 < rule.confidence <= 1.0


def test_the_catalogue_is_versioned() -> None:
    assert CATALOGUE_VERSION.strip()


def test_the_resolution_rules_are_the_ones_this_issue_declares() -> None:
    """Named one by one: a rule silently disappearing would make its findings untraceable."""
    assert set(CATALOGUE) == {"resolution.duplicate_reference", "resolution.group_conflict", "resolution.group_split"}


def test_the_confidence_ladder_holds() -> None:
    """The ladder of the module docstring: exact strings first, free-text judgement last."""
    assert CATALOGUE["resolution.duplicate_reference"].confidence > CATALOGUE["resolution.group_conflict"].confidence
    assert CATALOGUE["resolution.group_conflict"].confidence > CATALOGUE["resolution.group_split"].confidence
