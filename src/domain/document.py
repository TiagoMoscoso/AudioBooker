"""Domain model for parsed documents. This is the normalized shape every
DocumentParser implementation produces — the rest of the application (and the
UI) never needs to know whether a book came from a PDF, DOCX, MOBI, TXT or
Markdown file."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SectionKind(Enum):
    """Structural role of a section within the source document, used by
    ChapterDetector's explicit-structure tier."""

    TITLE = "title"
    HEADING_1 = "heading_1"
    HEADING_2 = "heading_2"
    HEADING_3 = "heading_3"
    PARAGRAPH = "paragraph"
    PAGE_BREAK = "page_break"
    SCENE_BREAK = "scene_break"


# Sentinel placed as the text of a SCENE_BREAK section so it survives the
# join into a chapter string (AnalyzeDocumentService.build_chapters) as its
# own paragraph, and the full TextPreprocessor pipeline it still passes
# through afterward (NarrationCleaner strips markdown emphasis characters
# like "_"/"*"/"`", so the token deliberately avoids all of them), without
# ever being read aloud. Consumed and discarded by NarrationChunker.
SCENE_BREAK_TOKEN = "⁣SCENEBREAK⁣"


@dataclass(frozen=True)
class DocumentSection:
    """A structural unit extracted from the source document, in original
    reading order."""

    kind: SectionKind
    text: str
    order: int
    source_page: int | None = None


@dataclass(frozen=True)
class DocumentMetadata:
    source_path: str
    source_format: str
    word_count: int = 0
    page_count: int | None = None
    is_scanned_image_only: bool = False


@dataclass
class ParsedDocument:
    title: str
    author: str | None
    sections: list[DocumentSection] = field(default_factory=list)
    metadata: DocumentMetadata = field(
        default_factory=lambda: DocumentMetadata(source_path="", source_format="")
    )
