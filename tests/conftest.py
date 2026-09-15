"""Shared test helpers.

Building a real EPUB in a temporary folder is better than checking in a sample
file: the test then states what an EPUB *is*, and a reader can see which part
of the format each test is about.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
  </metadata>
  <manifest>
{manifest}
  </manifest>
  <spine>
{spine}
  </spine>
</package>
"""


def make_epub(path: Path, sections: list[tuple[str, str]], *, title: str = "Test Book") -> Path:
    """Write an EPUB containing ``sections`` as (heading, body) pairs.

    The spine is written in the order given, and the filenames are deliberately
    numbered *against* that order, so a test that passes by sorting filenames
    would fail here.
    """
    manifest_lines = []
    spine_lines = []
    documents = []

    count = len(sections)
    for position, (heading, body) in enumerate(sections):
        # Reverse-numbered filenames: reading order must come from the spine.
        filename = f"part{count - position:03d}.xhtml"
        item_id = f"item{position}"
        manifest_lines.append(
            f'    <item id="{item_id}" href="{filename}" media-type="application/xhtml+xml"/>'
        )
        spine_lines.append(f'    <itemref idref="{item_id}"/>')
        paragraphs = "\n".join(f"<p>{line}</p>" for line in body.split("\n\n"))
        documents.append(
            (
                filename,
                "<?xml version='1.0' encoding='utf-8'?>\n"
                '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
                f"<title>{heading}</title><style>p {{ color: red }}</style></head>"
                f"<body><h1>{heading}</h1>\n{paragraphs}</body></html>",
            )
        )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr(
            "OEBPS/content.opf",
            OPF.format(
                title=title,
                manifest="\n".join(manifest_lines),
                spine="\n".join(spine_lines),
            ),
        )
        for filename, content in documents:
            archive.writestr(f"OEBPS/{filename}", content)
    return path


@pytest.fixture
def epub_factory(tmp_path):
    def build(sections, name="book.epub", **kwargs):
        return make_epub(tmp_path / name, sections, **kwargs)

    return build


@pytest.fixture
def long_body():
    """A body comfortably over the default 100-word minimum."""
    sentence = "The quick brown fox jumped over the lazy dog again and again. "
    return (sentence * 12).strip()
