"""Extracts MOBI ebooks (§11) using the actively-maintained `mobi` package
(a wrapper around KindleUnpack) to obtain an EPUB when possible, falling back
to the unpacked HTML for older/simpler MOBI files. Reuses the EPUB's own
TOC/spine/heading structure when available; otherwise the flat paragraph list
is handed to ChapterDetector's heuristic tier."""
from __future__ import annotations

import shutil
from pathlib import Path

import ebooklib
import mobi
from bs4 import BeautifulSoup
from ebooklib import epub

from domain.document import DocumentMetadata, DocumentSection, ParsedDocument, SectionKind
from i18n import tr

_TAG_KIND = {
    "h1": SectionKind.TITLE,
    "h2": SectionKind.HEADING_1,
    "h3": SectionKind.HEADING_2,
}


class MobiDocumentParser:
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in {".mobi", ".azw", ".azw3"}

    def parse(self, path: Path) -> ParsedDocument:
        tempdir, extracted_path = mobi.extract(str(path))
        try:
            extracted = Path(extracted_path)
            if extracted.suffix.lower() == ".epub":
                return self._parse_epub(extracted, path)
            return self._parse_html(extracted, path)
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def _parse_epub(self, epub_path: Path, original_path: Path) -> ParsedDocument:
        book = epub.read_epub(str(epub_path))
        title_meta = book.get_metadata("DC", "title")
        author_meta = book.get_metadata("DC", "creator")
        title_text = title_meta[0][0] if title_meta else None
        author_text = author_meta[0][0] if author_meta else None

        sections: list[DocumentSection] = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), "lxml")
            sections.extend(self._sections_from_soup(soup, len(sections)))

        word_count = sum(len(s.text.split()) for s in sections)
        return ParsedDocument(
            title=title_text or original_path.stem.replace("_", " ").strip() or tr("document.untitled"),
            author=author_text,
            sections=sections,
            metadata=DocumentMetadata(
                source_path=str(original_path),
                source_format="mobi",
                word_count=word_count,
            ),
        )

    def _parse_html(self, html_path: Path, original_path: Path) -> ParsedDocument:
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "lxml")
        sections = self._sections_from_soup(soup, 0)
        word_count = sum(len(s.text.split()) for s in sections)
        return ParsedDocument(
            title=original_path.stem.replace("_", " ").strip() or tr("document.untitled"),
            author=None,
            sections=sections,
            metadata=DocumentMetadata(
                source_path=str(original_path),
                source_format="mobi",
                word_count=word_count,
            ),
        )

    def _sections_from_soup(self, soup: BeautifulSoup, order_start: int) -> list[DocumentSection]:
        sections: list[DocumentSection] = []
        order = order_start
        for element in soup.find_all(["h1", "h2", "h3", "p"]):
            text = element.get_text(" ", strip=True)
            if not text:
                continue
            kind = _TAG_KIND.get(element.name, SectionKind.PARAGRAPH)
            sections.append(DocumentSection(kind=kind, text=text, order=order))
            order += 1
        return sections
