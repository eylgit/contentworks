"""Split an EPUB file into chapters of clean plain text.

An EPUB is a zip archive containing XHTML files plus an index that says which
order they go in. Nothing here needs a third-party library: the standard
library can open a zip, parse XML, and strip HTML tags.

The work that is not obvious:

* The reading order lives in the *spine*, not in the filenames. Files are often
  named ``part0007.xhtml`` in an order that has nothing to do with the book.
* Paragraph boundaries have to survive tag stripping, or the whole chapter
  arrives as one unbroken wall of text. The newlines in the source do not mark
  them: many books wrap their HTML at 80 columns, inside a single paragraph.
* Real books contain front matter, copyright pages and empty navigation stubs.
  Those are chapters as far as the file format is concerned and noise as far as
  a reader is concerned, so very short sections are dropped by default.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

CONTAINER_PATH = "META-INF/container.xml"

# Tags that end a block of text. Anything else is inline and must not introduce
# a break, or words get split apart mid-sentence.
BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "blockquote", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6",
}

# Tags whose contents are never readable text.
SKIP_TAGS = {"script", "style", "head", "title"}

HEADING_TAGS = ("h1", "h2", "h3", "h4")

# Marks where a block tag opened or closed. Not "\n", because a newline in the
# source is only layout. The ASCII record separator never appears in prose.
BLOCK_BREAK = "\x1e"


class EpubError(Exception):
    """The file could not be read as an EPUB."""


@dataclass
class Chapter:
    """One readable section of a book, in reading order."""

    index: int
    title: str
    text: str
    source_href: str

    @property
    def word_count(self) -> int:
        """Words, counting a run of CJK characters as one word each.

        A plain ``split()`` reports 1 for an entire Chinese paragraph, because
        Chinese is not written with spaces between words.
        """
        latin = len(re.findall(r"[A-Za-z0-9']+", self.text))
        cjk = len(re.findall(r"[㐀-鿿豈-﫿]", self.text))
        return latin + cjk

    @property
    def slug(self) -> str:
        """A filename-safe form of the title, for writing the chapter to disk."""
        cleaned = re.sub(r"[^\w\s-]", "", self.title, flags=re.UNICODE).strip()
        cleaned = re.sub(r"[\s_-]+", "-", cleaned)
        return cleaned.lower()[:60] or f"chapter-{self.index:02d}"


class _TextExtractor(HTMLParser):
    """Collect readable text, keeping paragraph boundaries and the first heading."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._heading_depth = 0
        self._heading_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in HEADING_TAGS and not self._heading_parts:
            self._heading_depth += 1
        if tag in BLOCK_TAGS:
            self._parts.append(BLOCK_BREAK)

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in HEADING_TAGS and self._heading_depth:
            self._heading_depth -= 1
        if tag in BLOCK_TAGS:
            self._parts.append(BLOCK_BREAK)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._parts.append(data)
        if self._heading_depth:
            self._heading_parts.append(data)

    @property
    def heading(self) -> str:
        return normalise_whitespace("".join(self._heading_parts))

    @property
    def text(self) -> str:
        raw = "".join(self._parts)
        paragraphs = [normalise_whitespace(block) for block in raw.split(BLOCK_BREAK)]
        return "\n\n".join(p for p in paragraphs if p)


def normalise_whitespace(text: str) -> str:
    """Collapse runs of whitespace and trim. Non-breaking spaces count as spaces."""
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def _strip_namespace(tag: str) -> str:
    """``{http://www.idpf.org/2007/opf}manifest`` becomes ``manifest``."""
    return tag.rsplit("}", 1)[-1]


def _find_opf_path(archive: zipfile.ZipFile) -> str:
    """Read the container index to find the file that describes the book."""
    try:
        container = archive.read(CONTAINER_PATH)
    except KeyError as exc:
        raise EpubError(f"not an EPUB: {CONTAINER_PATH} is missing") from exc

    root = ElementTree.fromstring(container)
    for element in root.iter():
        if _strip_namespace(element.tag) == "rootfile":
            full_path = element.get("full-path")
            if full_path:
                return full_path
    raise EpubError(f"{CONTAINER_PATH} does not name a rootfile")


@dataclass
class _Spine:
    """The reading order, as hrefs relative to the archive root."""

    hrefs: list[str] = field(default_factory=list)
    title: str = ""


def _read_spine(archive: zipfile.ZipFile, opf_path: str) -> _Spine:
    root = ElementTree.fromstring(archive.read(opf_path))
    base = posixpath.dirname(opf_path)

    manifest: dict[str, str] = {}
    order: list[str] = []
    title = ""

    for element in root.iter():
        name = _strip_namespace(element.tag)
        if name == "item":
            item_id, href = element.get("id"), element.get("href")
            if item_id and href:
                manifest[item_id] = posixpath.normpath(posixpath.join(base, href))
        elif name == "itemref":
            idref = element.get("idref")
            if idref:
                order.append(idref)
        elif name == "title" and not title and element.text:
            title = normalise_whitespace(element.text)

    hrefs = [manifest[idref] for idref in order if idref in manifest]
    if not hrefs:
        raise EpubError("the EPUB spine is empty, so there is no reading order to follow")
    return _Spine(hrefs=hrefs, title=title)


def split_epub(path: str | Path, *, min_words: int = 100) -> list[Chapter]:
    """Return the chapters of an EPUB, in reading order.

    Sections shorter than ``min_words`` are dropped — in practice these are
    copyright pages, navigation stubs and half-empty title pages. Pass
    ``min_words=0`` to keep everything.
    """
    path = Path(path)
    if not path.is_file():
        raise EpubError(f"no such file: {path}")

    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise EpubError(f"{path.name} is not a zip archive, so it is not an EPUB") from exc

    chapters: list[Chapter] = []
    with archive:
        spine = _read_spine(archive, _find_opf_path(archive))
        for href in spine.hrefs:
            try:
                raw = archive.read(href)
            except KeyError:
                # The spine named a file that is not in the archive. Skip it
                # rather than failing: a missing chapter should not cost the
                # reader the other three hundred pages.
                continue

            extractor = _TextExtractor()
            extractor.feed(raw.decode("utf-8", errors="replace"))
            text = extractor.text
            if not text:
                continue

            index = len(chapters) + 1
            chapter = Chapter(
                index=index,
                title=extractor.heading or f"Chapter {index}",
                text=text,
                source_href=href,
            )
            if chapter.word_count >= min_words:
                chapters.append(chapter)
            else:
                # Renumber so the indexes stay contiguous after a drop.
                continue

    for position, chapter in enumerate(chapters, start=1):
        chapter.index = position
    return chapters
