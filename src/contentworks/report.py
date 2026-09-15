"""Turn findings into a report a person will actually read.

The report answers three questions in order: did it pass, which pieces failed,
and exactly where. A report that only says "3 errors" makes someone open every
file to find them, which is the work the tool was supposed to do.
"""

from __future__ import annotations

from dataclasses import dataclass

from contentworks.checks import Finding
from contentworks.rules import RuleSet


@dataclass(frozen=True)
class PieceResult:
    """The findings for one piece of text."""

    name: str
    findings: tuple[Finding, ...]

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.is_error)

    @property
    def warnings(self) -> int:
        return len(self.findings) - self.errors

    @property
    def passed(self) -> bool:
        return self.errors == 0


def render_report(results: list[PieceResult], rules: RuleSet) -> str:
    """Render a Markdown report."""
    total_errors = sum(r.errors for r in results)
    total_warnings = sum(r.warnings for r in results)
    failed = [r for r in results if not r.passed]

    lines: list[str] = [
        f"# Check report — {rules.name}",
        "",
        f"Checked **{len(results)}** pieces against **{len(rules)}** rules.",
        "",
    ]

    if not results:
        lines.append("Nothing to check.")
        return "\n".join(lines) + "\n"

    if total_errors == 0:
        lines.append(f"**All {len(results)} passed.**")
        if total_warnings:
            lines.append(f" {total_warnings} warnings, which do not block.")
    else:
        lines.append(
            f"**{len(failed)} of {len(results)} failed** — "
            f"{total_errors} errors, {total_warnings} warnings."
        )
    lines.append("")

    lines += ["| Piece | Errors | Warnings | Result |", "|---|---|---|---|"]
    for result in results:
        mark = "pass" if result.passed else "FAIL"
        lines.append(f"| {result.name} | {result.errors} | {result.warnings} | {mark} |")
    lines.append("")

    detailed = [r for r in results if r.findings]
    if detailed:
        lines += ["## What went wrong", ""]
        for result in detailed:
            lines.append(f"### {result.name}")
            lines.append("")
            for finding in result.findings:
                where = f"line {finding.line}" if finding.line else "whole piece"
                lines.append(
                    f"- **{finding.rule_id}** ({finding.severity}, {where}) — {finding.message}"
                )
                if finding.excerpt:
                    lines.append(f"  - `{finding.excerpt}`")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
