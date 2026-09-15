"""contentworks — turn source material into a checked series.

The shape of the package:

    sources/   where material comes from (epub today, more later)
    rules      load and validate a rules file
    checks     apply the rules to a piece of text
    report     turn findings into something readable

Nothing in here knows about the command line or any other interface.
That separation is deliberate: see ``cli.py``, which depends on this
package and is depended on by nothing.
"""

from contentworks.checks import Finding, check_text
from contentworks.report import render_report
from contentworks.rules import Rule, RuleSet, load_rules
from contentworks.sources.epub import Chapter, split_epub

__version__ = "0.1.0"

__all__ = [
    "Chapter",
    "Finding",
    "Rule",
    "RuleSet",
    "check_text",
    "load_rules",
    "render_report",
    "split_epub",
]
