"""The two commands, end to end.

These also cover the report, because the report only matters as something a
person reads at the end of a run.
"""

from __future__ import annotations

from contentworks.cli import main

RULES = """
name: test rules
rules:
  - id: title-line
    type: first_line_matches
    description: the first line must be a title
    pattern: '^Title: .+$'
  - id: no-urls
    type: forbidden_pattern
    description: no web addresses
    pattern: 'https?://\\S+'
"""


def write_rules(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(RULES, encoding="utf-8")
    return path


def test_split_writes_one_file_per_chapter(epub_factory, long_body, tmp_path, capsys):
    book = epub_factory([("One", long_body), ("Two", long_body)])
    out = tmp_path / "chapters"

    assert main(["split", str(book), "-o", str(out)]) == 0

    files = sorted(p.name for p in out.glob("*.txt"))
    assert files == ["01-one.txt", "02-two.txt"]
    assert "2 chapters" in capsys.readouterr().out


def test_check_passes_and_exits_zero(tmp_path, capsys):
    folder = tmp_path / "drafts"
    folder.mkdir()
    (folder / "ep01.txt").write_text("Title: Episode One\n\nAll fine here.", encoding="utf-8")

    assert main(["check", str(folder), "-r", str(write_rules(tmp_path))]) == 0
    assert "All 1 passed" in capsys.readouterr().out


def test_check_fails_and_exits_non_zero(tmp_path, capsys):
    """The exit code is what lets this run as an automated gate later."""
    folder = tmp_path / "drafts"
    folder.mkdir()
    (folder / "ep01.txt").write_text("No title line\n\nSee https://x.com", encoding="utf-8")

    assert main(["check", str(folder), "-r", str(write_rules(tmp_path))]) == 1

    output = capsys.readouterr().out
    assert "1 of 1 failed" in output
    assert "title-line" in output
    assert "no-urls" in output


def test_report_names_the_file_the_rule_and_the_line(tmp_path):
    folder = tmp_path / "drafts"
    folder.mkdir()
    (folder / "ep02.txt").write_text("Title: Fine\n\nlink https://x.com here", encoding="utf-8")
    report = tmp_path / "report.md"

    main(["check", str(folder), "-r", str(write_rules(tmp_path)), "-o", str(report)])
    text = report.read_text(encoding="utf-8")

    assert "ep02.txt" in text
    assert "no-urls" in text
    assert "line 3" in text


def test_a_bad_rules_file_exits_two_with_a_readable_error(tmp_path, capsys):
    folder = tmp_path / "drafts"
    folder.mkdir()
    (folder / "a.txt").write_text("anything", encoding="utf-8")
    broken = tmp_path / "broken.yaml"
    broken.write_text("name: x\nrules: []\n", encoding="utf-8")

    assert main(["check", str(folder), "-r", str(broken)]) == 2
    assert "error:" in capsys.readouterr().err


def test_an_empty_folder_is_reported_not_passed(tmp_path, capsys):
    """Nothing to check must never render as a clean pass."""
    folder = tmp_path / "empty"
    folder.mkdir()

    assert main(["check", str(folder), "-r", str(write_rules(tmp_path))]) == 1
    assert "No .txt or .md files" in capsys.readouterr().err
