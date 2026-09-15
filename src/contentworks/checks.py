"""Apply a rule set to a piece of text.

This is the quality gate. Everything here is deterministic: no model is
called, nothing is judged, the same text and the same rules always give the
same answer.

That is a deliberate first layer. Rules that can be decided by reading the text
should never cost a model call, and a check that can be wrong in an interesting
way should not sit underneath one that cannot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from contentworks.rules import Rule, RuleSet

# Sentence ends, for both Latin and CJK punctuation. A Latin full stop only
# ends a sentence when whitespace or the end of the text follows it, so "3.5"
# and "example.com" stay in one piece. Full-width marks always end one. So does
# a blank line: a title or heading has no full stop, but it is not part of the
# sentence that follows it.
SENTENCE_END = re.compile(r"[.!?](?=\s|$)|[。！？]|\n\s*\n")


@dataclass(frozen=True)
class Finding:
    """One place where a rule was broken."""

    rule_id: str
    severity: str
    message: str
    line: int | None = None
    excerpt: str = ""

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


def check_text(text: str, rules: RuleSet) -> list[Finding]:
    """Run every rule against one piece of text and return what it broke."""
    findings: list[Finding] = []
    for rule in rules:
        findings.extend(_CHECKS[rule.type](text, rule))
    return findings


def passes(text: str, rules: RuleSet) -> bool:
    """True when nothing of severity 'error' was found. Warnings do not block."""
    return not any(f.is_error for f in check_text(text, rules))


def iter_sentences(text: str) -> list[tuple[int, str]]:
    """Return ``(offset, sentence)`` pairs, offsets into the original text.

    The offset is kept because a finding without a line number makes someone
    search the file by hand, which is the work the tool was meant to do.
    """
    found: list[tuple[int, str]] = []
    start = 0
    for match in SENTENCE_END.finditer(text):
        found.append((start, text[start : match.end()]))
        start = match.end()
    found.append((start, text[start:]))

    result: list[tuple[int, str]] = []
    for offset, chunk in found:
        stripped = chunk.strip()
        if stripped:
            result.append((offset + len(chunk) - len(chunk.lstrip()), stripped))
    return result


def split_sentences(text: str) -> list[str]:
    """Split into sentences. Blank results are dropped."""
    return [sentence for _, sentence in iter_sentences(text)]


def _line_of(text: str, position: int) -> int:
    """Turn a character offset into a 1-based line number."""
    return text.count("\n", 0, position) + 1


def _excerpt(text: str, limit: int = 60) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _first_line_matches(text: str, rule: Rule) -> list[Finding]:
    pattern = rule.compiled_pattern
    first_line = text.lstrip("\n").split("\n", 1)[0].strip()
    if pattern and pattern.search(first_line):
        return []
    return [
        Finding(
            rule_id=rule.id,
            severity=rule.severity,
            message=rule.description,
            line=1,
            excerpt=_excerpt(first_line),
        )
    ]


def _forbidden_pattern(text: str, rule: Rule) -> list[Finding]:
    pattern = rule.compiled_pattern
    if not pattern:
        return []

    # ``skip_lines`` exists because a title line can legitimately look like the
    # thing a rule forbids. "Series: Episode 01 - Title" is a title to a reader
    # and a speaker label to a regular expression, and no amount of tightening
    # the pattern tells those apart — the difference is where the line sits.
    skip = int(rule.settings.get("skip_lines", 0))
    return [
        Finding(
            rule_id=rule.id,
            severity=rule.severity,
            message=rule.description,
            line=line,
            excerpt=_excerpt(match.group(0)),
        )
        for match in pattern.finditer(text)
        # Count from where the matched *text* starts, not where its leading
        # whitespace does. A pattern beginning "^\s*" can start its match on the
        # blank line above, which would report the wrong line and let a skipped
        # line swallow the one after it.
        if (line := _line_of(text, _content_start(match))) > skip
    ]


def _content_start(match: re.Match[str]) -> int:
    matched = match.group(0)
    return match.start() + len(matched) - len(matched.lstrip())


def _required_pattern(text: str, rule: Rule) -> list[Finding]:
    pattern = rule.compiled_pattern
    if pattern and pattern.search(text):
        return []
    return [Finding(rule_id=rule.id, severity=rule.severity, message=rule.description)]


def _max_sentence_length(text: str, rule: Rule) -> list[Finding]:
    limit = int(rule.settings["limit"])
    return [
        Finding(
            rule_id=rule.id,
            severity=rule.severity,
            message=f"{rule.description} ({len(sentence)} characters, limit {limit})",
            line=_line_of(text, offset),
            excerpt=_excerpt(sentence),
        )
        for offset, sentence in iter_sentences(text)
        if len(sentence) > limit
    ]


def _word_count_between(text: str, rule: Rule) -> list[Finding]:
    latin = len(re.findall(r"[A-Za-z0-9']+", text))
    cjk = len(re.findall(r"[㐀-鿿豈-﫿]", text))
    count = latin + cjk

    minimum = rule.settings.get("min")
    maximum = rule.settings.get("max")

    if minimum is not None and count < int(minimum):
        return [
            Finding(
                rule_id=rule.id,
                severity=rule.severity,
                message=f"{rule.description} ({count} words, minimum {minimum})",
            )
        ]
    if maximum is not None and count > int(maximum):
        return [
            Finding(
                rule_id=rule.id,
                severity=rule.severity,
                message=f"{rule.description} ({count} words, maximum {maximum})",
            )
        ]
    return []


def _blank_line_after(text: str, rule: Rule) -> list[Finding]:
    characters = str(rule.settings["characters"])
    findings: list[Finding] = []
    for position, character in enumerate(text):
        if character not in characters:
            continue
        rest = text[position + 1 :]
        if not rest.strip():
            continue  # End of the piece. Nothing is required to follow it.
        if not rest.startswith("\n\n"):
            findings.append(
                Finding(
                    rule_id=rule.id,
                    severity=rule.severity,
                    message=rule.description,
                    line=_line_of(text, position),
                    excerpt=_excerpt(text[max(0, position - 25) : position + 15]),
                )
            )
    return findings


_CHECKS = {
    "first_line_matches": _first_line_matches,
    "forbidden_pattern": _forbidden_pattern,
    "required_pattern": _required_pattern,
    "max_sentence_length": _max_sentence_length,
    "word_count_between": _word_count_between,
    "blank_line_after": _blank_line_after,
}
