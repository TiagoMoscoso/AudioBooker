"""Application service: imports a document, resolves the right parser,
cleans the extracted text, and detects chapter candidates. The presentation
layer depends only on this service — never on parser or preprocessor
internals directly (§6, §41 "UI sem regra de negócio")."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from domain.chapter import ChapterCandidate
from domain.document import ParsedDocument, SectionKind
from infrastructure.parsers.factory import DocumentParserFactory
from services.chapter_detector import ChapterDetector
from services.text_preprocessor import TextPreprocessor


@dataclass
class ImportResult:
    document: ParsedDocument
    chapter_candidates: list[ChapterCandidate]


class ImportDocumentService:
    def __init__(
        self,
        parser_factory: DocumentParserFactory | None = None,
        preprocessor: TextPreprocessor | None = None,
        chapter_detector: ChapterDetector | None = None,
    ) -> None:
        self._parser_factory = parser_factory or DocumentParserFactory()
        self._preprocessor = preprocessor or TextPreprocessor()
        self._chapter_detector = chapter_detector or ChapterDetector()

    def import_document(self, path: Path) -> ImportResult:
        parser = self._parser_factory.resolve(path)
        document = parser.parse(path)

        cleaned_sections = [
            replace(section, text=self._preprocessor.process(section.text))
            for section in document.sections
        ]
        document.sections = [
            section for section in cleaned_sections
            if section.text.strip() or section.kind == SectionKind.PAGE_BREAK
        ]

        candidates = self._chapter_detector.detect(document.sections)
        return ImportResult(document=document, chapter_candidates=candidates)
