"""Parses .txt files (§10), which have no formal structure: detects encoding
with a safe fallback to UTF-8, splits into paragraphs on blank lines, and
leaves chapter detection entirely to ChapterDetector's heuristic tier."""
from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_path

from domain.document import DocumentMetadata, DocumentSection, ParsedDocument, SectionKind
from i18n import tr


class TextDocumentParser:
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".txt"

    def parse(self, path: Path) -> ParsedDocument:
        text = self._read_with_fallback(path)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        sections = [
            DocumentSection(kind=SectionKind.PARAGRAPH, text=p, order=i)
            for i, p in enumerate(paragraphs)
        ]
        word_count = sum(len(p.split()) for p in paragraphs)
        title = path.stem.replace("_", " ").replace("-", " ").strip() or tr("document.untitled")

        return ParsedDocument(
            title=title,
            author=None,
            sections=sections,
            metadata=DocumentMetadata(
                source_path=str(path),
                source_format="txt",
                word_count=word_count,
            ),
        )

    def _read_with_fallback(self, path: Path) -> str:
        try:
            result = from_path(str(path)).best()
            if result is not None:
                return str(result)
        except Exception:
            pass
        return path.read_text(encoding="utf-8", errors="replace")
