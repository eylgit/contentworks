"""Reading an EPUB.

The tests that matter are the ones about the things that are easy to get wrong:
reading order, paragraph boundaries surviving tag stripping, and junk sections
being dropped without corrupting the numbering.
"""

from __future__ import annotations

import zipfile

import pytest

from contentworks.sources.epub import EpubError, split_epub


def test_reading_order_comes_from_the_spine_not_the_filenames(epub_factory, long_body):
    """The helper numbers files backwards on purpose. Sorting by name would fail here."""
    book = epub_factory(
        [("First", long_body), ("Second", long_body), ("Third", long_body)]
    )
    chapters = split_epub(book)

    assert [c.title for c in chapters] == ["First", "Second", "Third"]
    assert [c.index for c in chapters] == [1, 2, 3]


def test_paragraph_breaks_survive_tag_stripping(epub_factory, long_body):
    book = epub_factory([("Chapter", f"{long_body}\n\nA second paragraph here.")])
    text = split_epub(book)[0].text

    assert "\n\n" in text, "paragraphs must not be run together"
    assert "dog again.A second" not in text, "words must not be glued across the break"


def test_line_breaks_inside_a_paragraph_are_not_paragraph_breaks(epub_factory, long_body):
    """Many real books wrap their HTML at 80 columns. Those newlines are layout."""
    wrapped = long_body.replace(". ", ".\n")
    book = epub_factory([("Chapter", f"{wrapped}\n\nA second paragraph here.")])
    text = split_epub(book)[0].text

    assert text.split("\n\n") == ["Chapter", long_body, "A second paragraph here."]


def test_style_and_script_contents_are_not_treated_as_prose(epub_factory, long_body):
    book = epub_factory([("Chapter", long_body)])
    text = split_epub(book)[0].text

    assert "color: red" not in text


def test_short_sections_are_dropped_and_numbering_stays_contiguous(epub_factory, long_body):
    book = epub_factory(
        [
            ("Copyright", "All rights reserved."),
            ("Chapter One", long_body),
            ("Blank", ""),
            ("Chapter Two", long_body),
        ]
    )
    chapters = split_epub(book)

    assert [c.title for c in chapters] == ["Chapter One", "Chapter Two"]
    assert [c.index for c in chapters] == [1, 2], "no gaps left by the dropped sections"


def test_min_words_zero_keeps_the_front_matter(epub_factory, long_body):
    book = epub_factory([("Copyright", "All rights reserved."), ("One", long_body)])

    assert len(split_epub(book, min_words=0)) == 2
    assert len(split_epub(book)) == 1


def test_title_falls_back_when_a_section_has_no_heading(epub_factory):
    book = epub_factory([("", "word " * 150)])
    assert split_epub(book)[0].title == "Chapter 1"


def test_slug_is_filename_safe(epub_factory, long_body):
    book = epub_factory([("Chapter One: The Beginning!", long_body)])
    assert split_epub(book)[0].slug == "chapter-one-the-beginning"


def test_cjk_text_is_counted_by_character(epub_factory):
    """A whole Chinese paragraph splits into one 'word', so it would be dropped as junk."""
    book = epub_factory([("第一章", "道可道非常道名可名非常名" * 15)])
    chapters = split_epub(book)

    assert len(chapters) == 1
    assert chapters[0].word_count > 100


def test_a_missing_file_is_skipped_rather_than_fatal(epub_factory, long_body, tmp_path):
    """One broken chapter must not cost the reader the rest of the book."""
    book = epub_factory([("One", long_body), ("Two", long_body)])

    rebuilt = tmp_path / "damaged.epub"
    with zipfile.ZipFile(book) as source, zipfile.ZipFile(rebuilt, "w") as target:
        for item in source.namelist():
            if item.endswith("part002.xhtml"):
                continue
            target.writestr(item, source.read(item))

    assert len(split_epub(rebuilt)) == 1


def test_a_file_that_is_not_a_zip_says_so(tmp_path):
    fake = tmp_path / "not-a-book.epub"
    fake.write_text("just some text")

    with pytest.raises(EpubError, match="not a zip archive"):
        split_epub(fake)


def test_a_missing_file_names_the_path(tmp_path):
    with pytest.raises(EpubError, match="no such file"):
        split_epub(tmp_path / "absent.epub")


def test_a_zip_without_a_container_is_not_an_epub(tmp_path):
    path = tmp_path / "plain.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "hi")

    with pytest.raises(EpubError, match="container.xml"):
        split_epub(path)
