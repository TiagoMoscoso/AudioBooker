"""Domain model for chapters: ChapterCandidate is what ChapterDetector
proposes; Chapter is what the user has reviewed and confirmed for narration."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChapterSource(Enum):
    EXPLICIT_STRUCTURE = "explicit_structure"
    TEXT_PATTERN = "text_pattern"
    HEURISTIC = "heuristic"
    MANUAL = "manual"


@dataclass
class ChapterCandidate:
    """A detected chapter boundary, before user review. `start_section_index`
    points at the heading/title section itself within ParsedDocument.sections;
    the chapter's narrated text is everything between this boundary and the
    next one."""

    title: str
    order: int
    start_section_index: int
    source: ChapterSource
    confidence: float = 1.0


@dataclass
class Chapter:
    """A user-confirmed chapter, ready for chunking and narration."""

    id: str
    title: str
    order: int
    text: str
    included: bool = True
