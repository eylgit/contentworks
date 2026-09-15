"""The command line front end.

This module depends on the rest of the package. Nothing in the package depends
on this module. That is what makes it possible to add a web interface later
without touching a line of the core — and what makes the core testable without
pretending to be a terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contentworks import __version__
from contentworks.checks import check_text
from contentworks.report import PieceResult, render_report
from contentworks.rules import RulesError, load_rules
from contentworks.sources.epub import EpubError, split_epub


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contentworks",
        description="Split source material into pieces, and hold pieces to a written set of rules.",
    )
    parser.add_argument("--version", action="version", version=f"contentworks {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    split = commands.add_parser("split", help="split an EPUB into chapters of plain text")
    split.add_argument("book", type=Path, help="path to the .epub file")
    split.add_argument("-o", "--out", type=Path, default=Path("chapters"), help="output folder")
    split.add_argument(
        "--min-words",
        type=int,
        default=100,
        help="drop sections shorter than this (0 keeps everything). Default: 100",
    )

    check = commands.add_parser("check", help="check text files against a rules file")
    check.add_argument("folder", type=Path, help="folder of .txt or .md files to check")
    check.add_argument("-r", "--rules", type=Path, required=True, help="path to the rules YAML")
    check.add_argument("-o", "--out", type=Path, help="write the report here instead of stdout")

    return parser


def run_split(book: Path, out: Path, min_words: int) -> int:
    chapters = split_epub(book, min_words=min_words)
    if not chapters:
        print(f"No chapters found in {book.name}. Try --min-words 0.", file=sys.stderr)
        return 1

    out.mkdir(parents=True, exist_ok=True)
    for chapter in chapters:
        target = out / f"{chapter.index:02d}-{chapter.slug}.txt"
        target.write_text(chapter.text, encoding="utf-8")

    total = sum(c.word_count for c in chapters)
    print(f"{len(chapters)} chapters, {total:,} words -> {out}/")
    for chapter in chapters:
        print(f"  {chapter.index:02d}  {chapter.word_count:>6,}w  {chapter.title}")
    return 0


def run_check(folder: Path, rules_path: Path, out: Path | None) -> int:
    rules = load_rules(rules_path)

    paths = sorted(p for p in folder.glob("*") if p.suffix in {".txt", ".md"})
    if not paths:
        print(f"No .txt or .md files in {folder}", file=sys.stderr)
        return 1

    results = [
        PieceResult(
            name=path.name,
            findings=tuple(check_text(path.read_text(encoding="utf-8"), rules)),
        )
        for path in paths
    ]

    report = render_report(results, rules)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Report written to {out}")
    else:
        print(report)

    # A non-zero exit code is what lets this run in an automated check later.
    return 1 if any(not r.passed for r in results) else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "split":
            return run_split(args.book, args.out, args.min_words)
        return run_check(args.folder, args.rules, args.out)
    except (EpubError, RulesError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
