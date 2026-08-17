"""Parses Markdown documents (§9) using ATX headings (#, ##, ...) as
structural signals for title/chapter detection, then strips Markdown syntax
that should not be narrated literally while preserving the textual content."""
from __future__ import annotations

import re
from pathlib import Path

from domain.document import (
    SCENE_BREAK_TOKEN, DocumentMetadata, DocumentSection, ParsedDocument, SectionKind,
)
from i18n import tr

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_CODE_FENCE = re.compile(r"^```")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|___|__|_|~~|`)")
_HORIZONTAL_RULE = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_LIST_MARKER = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
_BLOCKQUOTE = re.compile(r"^\s*>\s?")

_HEADING_KIND = {
    1: SectionKind.TITLE,
    2: SectionKind.HEADING_1,
    3: SectionKind.HEADING_2,
}


class MarkdownDocumentParser:
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in {".md", ".markdown"}

    def parse(self, path: Path) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        lines = raw.split("\n")

        sections: list[DocumentSection] = []
        paragraph_buffer: list[str] = []
        title: str | None = None
        in_code_block = False
        order = 0

        def flush_paragraph() -> None:
            nonlocal order
            if not paragraph_buffer:
                return
            text = self._clean_inline(" ".join(paragraph_buffer).strip())
            paragraph_buffer.clear()
            if text:
                sections.append(DocumentSection(kind=SectionKind.PARAGRAPH, text=text, order=order))
                order += 1

        for line in lines:
            if _CODE_FENCE.match(line):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            if not line.strip():
                flush_paragraph()
                continue
            if _HORIZONTAL_RULE.match(line):
                flush_paragraph()
                # A horizontal rule in prose is a scene-break marker, not
                # narrative content — keep it as a distinct section so
                # NarrationChunker can turn it into a pause instead of either
                # discarding the signal entirely or narrating it literally.
                sections.append(
                    DocumentSection(kind=SectionKind.SCENE_BREAK, text=SCENE_BREAK_TOKEN, order=order)
                )
                order += 1
                continue

            heading_match = _HEADING.match(line)
            if heading_match:
                flush_paragraph()
                level = len(heading_match.group(1))
                text = self._clean_inline(heading_match.group(2).strip())
                if not text:
                    continue
                if title is None and level == 1:
                    title = text
                kind = _HEADING_KIND.get(level, SectionKind.HEADING_3)
                sections.append(DocumentSection(kind=kind, text=text, order=order))
                order += 1
                continue

            cleaned_line = _BLOCKQUOTE.sub("", line)
            cleaned_line = _LIST_MARKER.sub("", cleaned_line)
            paragraph_buffer.append(cleaned_line.strip())
        flush_paragraph()

        word_count = sum(len(s.text.split()) for s in sections)
        return ParsedDocument(
            title=title or path.stem.replace("_", " ").strip() or tr("document.untitled"),
            author=None,
            sections=sections,
            metadata=DocumentMetadata(
                source_path=str(path),
                source_format="markdown",
                word_count=word_count,
            ),
        )

    def _clean_inline(self, text: str) -> str:
        text = _IMAGE.sub("", text)
        text = _LINK.sub(r"\1", text)
        text = _EMPHASIS.sub("", text)
        return text.strip()
