"""Resolves the right DocumentParser implementation for a given file (§6), so
the rest of the application depends only on the DocumentParser abstraction —
never on which concrete parser handled a given format."""
from __future__ import annotations

from pathlib import Path

from i18n import tr
from infrastructure.parsers.base import DocumentParser, UnsupportedDocumentError
from infrastructure.parsers.docx_parser import DocxDocumentParser
from infrastructure.parsers.markdown_parser import MarkdownDocumentParser
from infrastructure.parsers.mobi_parser import MobiDocumentParser
from infrastructure.parsers.pdf_parser import PdfDocumentParser
from infrastructure.parsers.text_parser import TextDocumentParser

SUPPORTED_EXTENSIONS = {".pdf", ".mobi", ".azw", ".azw3", ".txt", ".md", ".markdown", ".docx"}


class DocumentParserFactory:
    def __init__(self) -> None:
        self._parsers: list[DocumentParser] = [
            PdfDocumentParser(),
            MobiDocumentParser(),
            DocxDocumentParser(),
            MarkdownDocumentParser(),
            TextDocumentParser(),
        ]

    def resolve(self, path: Path) -> DocumentParser:
        for parser in self._parsers:
            if parser.supports(path):
                return parser
        raise UnsupportedDocumentError(tr("error.unsupported_format", suffix=path.suffix))
