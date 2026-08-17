"""Extracts text from PDFs with a text layer (§7): reflows wrapped lines
within each paragraph block (fixing PDF-style hyphenation as it goes), strips
repeated running headers/footers and isolated page-number lines via
HeaderFooterCleaner, and refuses to silently produce an empty audiobook from
scanned/image-only PDFs — OCR is out of scope for this MVP."""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf as fitz  # PyMuPDF's current import name is `pymupdf`; `fitz` is a deprecated alias.

from domain.document import DocumentMetadata, DocumentSection, ParsedDocument, SectionKind
from i18n import tr
from infrastructure.parsers.base import ScannedPdfError
from services.text_preprocessor import HeaderFooterCleaner

_TRAILING_HYPHEN = re.compile(r"-\s*$")
_TEXT_BLOCK_TYPE = 0  # PyMuPDF block[6] == 0 means a text block (not image)


class PdfDocumentParser:
    def __init__(self, header_footer_cleaner: HeaderFooterCleaner | None = None) -> None:
        self._header_footer_cleaner = header_footer_cleaner or HeaderFooterCleaner()

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> ParsedDocument:
        doc = fitz.open(str(path))
        try:
            if self._looks_scanned(doc):
                raise ScannedPdfError(tr("error.scanned_pdf"))

            page_raw_lines: list[list[str]] = []
            page_paragraphs: list[list[str]] = []
            for page in doc:
                blocks = sorted(
                    page.get_text("blocks"),
                    key=lambda b: (round(b[1], 1), round(b[0], 1)),
                )
                raw_lines: list[str] = []
                paragraphs: list[str] = []
                for block in blocks:
                    if block[6] != _TEXT_BLOCK_TYPE:
                        continue
                    lines = [line for line in block[4].split("\n") if line.strip()]
                    raw_lines.extend(lines)
                    paragraph = self._reflow(lines)
                    if paragraph:
                        paragraphs.append(paragraph)
                page_raw_lines.append(raw_lines)
                page_paragraphs.append(paragraphs)

            removed_lines = self._compute_removed_lines(page_raw_lines)

            sections: list[DocumentSection] = []
            order = 0
            title = (doc.metadata.get("title") or "").strip() or None
            author = (doc.metadata.get("author") or "").strip() or None

            for page_number, paragraphs in enumerate(page_paragraphs, start=1):
                for paragraph in paragraphs:
                    if paragraph.strip() in removed_lines:
                        continue
                    sections.append(DocumentSection(
                        kind=SectionKind.PARAGRAPH,
                        text=paragraph,
                        order=order,
                        source_page=page_number,
                    ))
                    order += 1

            word_count = sum(len(s.text.split()) for s in sections)
            return ParsedDocument(
                title=title or path.stem.replace("_", " ").strip() or tr("document.untitled"),
                author=author,
                sections=sections,
                metadata=DocumentMetadata(
                    source_path=str(path),
                    source_format="pdf",
                    word_count=word_count,
                    page_count=doc.page_count,
                ),
            )
        finally:
            doc.close()

    def _compute_removed_lines(self, page_raw_lines: list[list[str]]) -> set[str]:
        cleaned = self._header_footer_cleaner.process(page_raw_lines)
        removed: set[str] = set()
        for original, kept in zip(page_raw_lines, cleaned):
            kept_stripped = {line.strip() for line in kept}
            for line in original:
                stripped = line.strip()
                if stripped and stripped not in kept_stripped:
                    removed.add(stripped)
        return removed

    def _reflow(self, lines: list[str]) -> str:
        result = ""
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if not result:
                result = line
            elif _TRAILING_HYPHEN.search(result) and line[:1].islower():
                result = _TRAILING_HYPHEN.sub("", result) + line
            else:
                result = f"{result} {line}"
        return result.strip()

    def _looks_scanned(self, doc: "fitz.Document") -> bool:
        if doc.page_count == 0:
            return False
        sample_pages = list(doc)[: min(5, doc.page_count)]
        text_chars = sum(len(page.get_text("text").strip()) for page in sample_pages)
        has_images = any(page.get_images(full=True) for page in sample_pages)
        return text_chars < 20 and has_images
