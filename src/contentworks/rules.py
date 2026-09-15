"""Load and validate a rules file.

The rules live in a YAML file, not in this code. That is the central design
decision of the package: a new kind of content becomes a new rules file, and
nothing here changes.

The cost of that decision is this module. When rules are data, a person can
write a broken rule, and a broken rule must fail with a message that says which
rule, what is wrong with it, and what was expected — not with a stack trace
three layers down.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SEVERITIES = ("error", "warning")

# Every rule type, with the settings it requires and the ones it merely allows.
# A rule type that is not in here is rejected at load time rather than silently
# ignored — a rule that is quietly skipped is worse than no rule, because the
# report then claims a clean pass.
RULE_TYPES: dict[str, tuple[set[str], set[str]]] = {
    # type: (required, optional)
    "first_line_matches": ({"pattern"}, set()),
    "forbidden_pattern": ({"pattern"}, {"skip_lines"}),
    "required_pattern": ({"pattern"}, set()),
    "max_sentence_length": ({"limit"}, set()),
    "word_count_between": (set(), {"min", "max"}),
    "blank_line_after": ({"characters"}, set()),
}


class RulesError(Exception):
    """The rules file could not be used. The message says why."""


@dataclass(frozen=True)
class Rule:
    """One thing a piece of text must or must not do."""

    id: str
    type: str
    description: str
    severity: str = "error"
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def compiled_pattern(self) -> re.Pattern[str] | None:
        pattern = self.settings.get("pattern")
        return re.compile(pattern, re.MULTILINE) if pattern else None


@dataclass(frozen=True)
class RuleSet:
    """A named collection of rules, loaded from one file."""

    name: str
    rules: tuple[Rule, ...]
    description: str = ""

    def __len__(self) -> int:
        return len(self.rules)

    def __iter__(self):
        return iter(self.rules)


def load_rules(path: str | Path) -> RuleSet:
    """Read a rules file and check it makes sense before anything uses it."""
    path = Path(path)
    if not path.is_file():
        raise RulesError(f"no such rules file: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RulesError(f"{path.name} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise RulesError(f"{path.name} must contain a mapping at the top level")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RulesError(f"{path.name} needs a 'name' field naming this rule set")

    entries = raw.get("rules")
    if not isinstance(entries, list) or not entries:
        raise RulesError(f"{path.name} needs a 'rules' list with at least one rule")

    rules: list[Rule] = []
    seen: set[str] = set()
    for position, entry in enumerate(entries, start=1):
        rule = _build_rule(entry, position, path.name)
        if rule.id in seen:
            raise RulesError(
                f"{path.name}: two rules share the id '{rule.id}'. "
                "Ids appear in the report, so they must be unique."
            )
        seen.add(rule.id)
        rules.append(rule)

    return RuleSet(
        name=name.strip(),
        description=str(raw.get("description", "")).strip(),
        rules=tuple(rules),
    )


def _build_rule(entry: Any, position: int, filename: str) -> Rule:
    where = f"{filename}: rule {position}"

    if not isinstance(entry, dict):
        raise RulesError(f"{where} is not a mapping")

    rule_id = entry.get("id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise RulesError(f"{where} has no 'id'. Every rule needs one so the report can name it.")

    rule_type = entry.get("type")
    if rule_type not in RULE_TYPES:
        known = ", ".join(sorted(RULE_TYPES))
        raise RulesError(
            f"{where} ('{rule_id}') has type '{rule_type}', which does not exist. "
            f"Known types: {known}"
        )

    description = entry.get("description")
    if not isinstance(description, str) or not description.strip():
        raise RulesError(
            f"{where} ('{rule_id}') has no 'description'. "
            "The description is what a reader sees when the rule is broken, "
            "so a rule without one produces an unusable report."
        )

    severity = entry.get("severity", "error")
    if severity not in SEVERITIES:
        raise RulesError(
            f"{where} ('{rule_id}') has severity '{severity}'. "
            f"Use one of: {', '.join(SEVERITIES)}"
        )

    required, optional = RULE_TYPES[rule_type]
    reserved = {"id", "type", "description", "severity"}
    settings = {key: value for key, value in entry.items() if key not in reserved}

    unknown = set(settings) - required - optional
    if unknown:
        accepts = sorted(required | optional)
        raise RulesError(
            f"{where} ('{rule_id}') has settings {sorted(unknown)}, which "
            f"type '{rule_type}' does not use. It accepts: {accepts or 'none'}"
        )

    missing = required - set(settings)
    if missing:
        raise RulesError(
            f"{where} ('{rule_id}') is missing {sorted(missing)}, "
            f"which type '{rule_type}' requires"
        )

    if "pattern" in settings:
        try:
            re.compile(str(settings["pattern"]))
        except re.error as exc:
            raise RulesError(
                f"{where} ('{rule_id}') has a pattern that is not valid: {exc}"
            ) from exc

    return Rule(
        id=rule_id.strip(),
        type=rule_type,
        description=description.strip(),
        severity=severity,
        settings=settings,
    )
