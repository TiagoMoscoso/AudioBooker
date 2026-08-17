"""Parses DOCX documents (§8) using their semantic structure — heading
styles, paragraphs, page breaks — rather than treating the file as flat
text."""
from __future__ import annotations

from pathlib import Path

import docx
from docx.oxml.ns import qn

from domain.document import DocumentMetadata, DocumentSection, ParsedDocument, SectionKind
from i18n import tr

_HEADING_STYLE_KIND = {
    "Title": SectionKind.TITLE,
    "Heading 1": SectionKind.HEADING_1,
    "Heading 2": SectionKind.HEADING_2,
    "Heading 3": SectionKind.HEADING_3,
}


def _has_page_break(paragraph) -> bool:
    for run in paragraph.runs:
        for br in run._element.findall(qn("w:br")):
            if br.get(qn("w:type")) == "page":
                return True
    return False


class DocxDocumentParser:
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".docx"

    def parse(self, path: Path) -> ParsedDocument:
        document = docx.Document(str(path))
        core_props = document.core_properties

        sections: list[DocumentSection] = []
        order = 0
        title: str | None = (core_props.title or "").strip() or None

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                if _has_page_break(paragraph):
                    sections.append(DocumentSection(kind=SectionKind.PAGE_BREAK, text="", order=order))
                    order += 1
                continue

            style_name = paragraph.style.name if paragraph.style else ""
            kind = _HEADING_STYLE_KIND.get(style_name, SectionKind.PARAGRAPH)
            if kind == SectionKind.TITLE and title is None:
                title = text
            sections.append(DocumentSection(kind=kind, text=text, order=order))
            order += 1

        word_count = sum(len(s.text.split()) for s in sections)
        return ParsedDocument(
            title=title or path.stem.replace("_", " ").strip() or tr("document.untitled"),
            author=(core_props.author or "").strip() or None,
            sections=sections,
            metadata=DocumentMetadata(
                source_path=str(path),
                source_format="docx",
                word_count=word_count,
            ),
        )
