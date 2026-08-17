"""DocumentParser abstraction (§6). The UI and application services depend
only on this Protocol and on ParsedDocument — never on parser internals."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from domain.document import ParsedDocument


class DocumentParser(Protocol):
    def supports(self, path: Path) -> bool: ...

    def parse(self, path: Path) -> ParsedDocument: ...


class UnsupportedDocumentError(Exception):
    """Raised when no registered parser supports the given file."""


class ScannedPdfError(Exception):
    """Raised when a PDF appears to contain only images (no extractable text
    layer). OCR is out of scope for the MVP (§7) — the caller must surface
    this as a clear message, never produce an empty audiobook."""
