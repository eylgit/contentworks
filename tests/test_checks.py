"""Every rule type, checked both ways: it fires when it should, and stays quiet when it should not.

A check that only ever fires is as useless as one that never does, so each
test has a passing case as well as a failing one.
"""

from __future__ import annotations

from contentworks.checks import check_text, passes, split_sentences
from contentworks.rules import Rule, RuleSet


def ruleset(*rules: Rule) -> RuleSet:
    return RuleSet(name="test", rules=rules)


def test_first_line_matches():
    rule = Rule(
        id="title",
        type="first_line_matches",
        description="needs a title line",
        settings={"pattern": r"^Series: Episode \d{2} - .+$"},
    )
    good = "Series: Episode 01 - The Beginning\n\nOnce upon a time."
    bad = "Once upon a time.\n\nMore text."

    assert check_text(good, ruleset(rule)) == []
    findings = check_text(bad, ruleset(rule))
    assert len(findings) == 1
    assert findings[0].line == 1
    assert "Once upon a time." in findings[0].excerpt


def test_forbidden_pattern_reports_every_occurrence_with_line_numbers():
    rule = Rule(
        id="no-labels",
        type="forbidden_pattern",
        description="no speaker labels",
        settings={"pattern": r"^\s*[A-Z][A-Za-z ]{0,20}:\s"},
    )
    text = "Narrator: hello\nplain line\nAlice: goodbye"
    findings = check_text(text, ruleset(rule))

    assert len(findings) == 2
    assert [f.line for f in findings] == [1, 3]


def test_skip_lines_exempts_the_title_line():
    """A title line can legitimately look like the thing a rule forbids."""
    rule = Rule(
        id="no-labels",
        type="forbidden_pattern",
        description="no speaker labels",
        settings={"pattern": r"^\s*[A-Z][A-Za-z ]{0,20}:\s", "skip_lines": 1},
    )
    good = "Series: Episode 01 - The Beginning\n\nPlain narration here."
    bad = "Series: Episode 01 - The Beginning\n\nNarrator: hello"

    assert check_text(good, ruleset(rule)) == []
    findings = check_text(bad, ruleset(rule))
    assert len(findings) == 1
    assert findings[0].line == 3


def test_a_full_stop_inside_a_word_does_not_end_a_sentence():
    """Otherwise 'example.com' and '3.5' each split a sentence in two."""
    assert split_sentences("Visit example.com today. Then stop.") == [
        "Visit example.com today.",
        "Then stop.",
    ]


def test_required_pattern_has_no_line_number():
    """Something missing has no location, so the report must not invent one."""
    rule = Rule(
        id="needs-outro",
        type="required_pattern",
        description="every episode needs a sign-off",
        settings={"pattern": r"Thanks for listening"},
    )
    assert check_text("Thanks for listening.", ruleset(rule)) == []

    findings = check_text("No sign-off here.", ruleset(rule))
    assert len(findings) == 1
    assert findings[0].line is None


def test_max_sentence_length_counts_characters_not_sentences():
    rule = Rule(
        id="len",
        type="max_sentence_length",
        description="too long to follow by ear",
        settings={"limit": 20},
    )
    text = "Short one. " + "x" * 40 + ". Another short."
    findings = check_text(text, ruleset(rule))

    assert len(findings) == 1
    # 40 x's plus the full stop: the punctuation is part of the sentence.
    assert "41 characters" in findings[0].message
    assert "limit 20" in findings[0].message


def test_word_count_between_reports_the_actual_count():
    rule = Rule(
        id="length",
        type="word_count_between",
        description="episode length",
        settings={"min": 5, "max": 10},
    )
    assert check_text("one two three four five six", ruleset(rule)) == []

    short = check_text("one two", ruleset(rule))
    assert "2 words" in short[0].message and "minimum 5" in short[0].message

    long = check_text(" ".join(["w"] * 20), ruleset(rule))
    assert "20 words" in long[0].message and "maximum 10" in long[0].message


def test_word_count_treats_each_cjk_character_as_a_word():
    """A plain split() reports 1 for a whole Chinese paragraph."""
    rule = Rule(
        id="length",
        type="word_count_between",
        description="episode length",
        settings={"min": 4},
    )
    assert check_text("今日講道德經第一章", ruleset(rule)) == []
    assert check_text("今日", ruleset(rule)) != []


def test_blank_line_after_allows_the_end_of_the_text():
    """Nothing is required to follow the final sentence."""
    rule = Rule(
        id="spacing",
        type="blank_line_after",
        description="a blank line must follow a full stop",
        settings={"characters": "。"},
    )
    assert check_text("第一句。\n\n第二句。", ruleset(rule)) == []
    assert check_text("第一句。第二句。", ruleset(rule)) != []


def test_warnings_do_not_block_but_are_still_reported():
    rule = Rule(
        id="brackets",
        type="forbidden_pattern",
        description="stage direction",
        severity="warning",
        settings={"pattern": r"\(pause\)"},
    )
    text = "He waited (pause) and then spoke."

    assert len(check_text(text, ruleset(rule))) == 1
    assert passes(text, ruleset(rule)), "warnings must not fail the piece"


def test_split_sentences_handles_both_punctuation_families():
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert split_sentences("第一句。第二句！") == ["第一句。", "第二句！"]


def test_no_rules_means_no_findings():
    assert check_text("anything at all", RuleSet(name="empty", rules=())) == []
