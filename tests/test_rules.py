"""A broken rules file must fail with a message that says what to fix.

These tests are mostly about failure. When rules are data, the person writing
them is not the person who wrote the code, so the error message is the only
documentation they will ever read.
"""

from __future__ import annotations

import pytest

from contentworks.rules import RulesError, load_rules

GOOD = """
name: example
description: a small rule set
rules:
  - id: title-line
    type: first_line_matches
    description: the first line must be a title
    pattern: '^Title: .+$'
  - id: no-urls
    type: forbidden_pattern
    description: no web addresses
    pattern: 'https?://'
    severity: warning
"""


def write(tmp_path, text, name="rules.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_a_valid_file(tmp_path):
    rules = load_rules(write(tmp_path, GOOD))
    assert rules.name == "example"
    assert len(rules) == 2
    assert rules.rules[0].severity == "error", "severity defaults to error"
    assert rules.rules[1].severity == "warning"


def test_missing_file_names_the_path(tmp_path):
    with pytest.raises(RulesError, match="no such rules file"):
        load_rules(tmp_path / "absent.yaml")


def test_broken_yaml_is_reported_as_yaml(tmp_path):
    with pytest.raises(RulesError, match="not valid YAML"):
        load_rules(write(tmp_path, "name: x\nrules: [ unclosed"))


def test_unknown_rule_type_lists_the_known_ones(tmp_path):
    text = """
name: example
rules:
  - id: mystery
    type: does_not_exist
    description: something
"""
    with pytest.raises(RulesError) as exc:
        load_rules(write(tmp_path, text))
    assert "does_not_exist" in str(exc.value)
    assert "first_line_matches" in str(exc.value), "the message must list valid types"


def test_rule_without_description_is_rejected(tmp_path):
    text = """
name: example
rules:
  - id: silent
    type: forbidden_pattern
    pattern: 'x'
"""
    with pytest.raises(RulesError, match="description"):
        load_rules(write(tmp_path, text))


def test_duplicate_ids_are_rejected(tmp_path):
    text = """
name: example
rules:
  - id: same
    type: forbidden_pattern
    description: one
    pattern: 'a'
  - id: same
    type: forbidden_pattern
    description: two
    pattern: 'b'
"""
    with pytest.raises(RulesError, match="share the id"):
        load_rules(write(tmp_path, text))


def test_unknown_setting_is_rejected_not_ignored(tmp_path):
    """A silently ignored setting is the worst case: the report claims a pass."""
    text = """
name: example
rules:
  - id: typo
    type: max_sentence_length
    description: too long
    limitt: 50
"""
    with pytest.raises(RulesError, match="limitt"):
        load_rules(write(tmp_path, text))


def test_invalid_regex_is_caught_at_load_time(tmp_path):
    text = """
name: example
rules:
  - id: bad
    type: forbidden_pattern
    description: broken pattern
    pattern: '([unclosed'
"""
    with pytest.raises(RulesError, match="not valid"):
        load_rules(write(tmp_path, text))


def test_the_shipped_example_file_loads():
    """The example in the README must actually work."""
    rules = load_rules("examples/podcastize-rules.yaml")
    assert rules.name == "podcastize"
    assert len(rules) >= 5
