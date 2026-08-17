"""Domain model for the audiobook library: a finished, playable book with its
per-chapter audio files, an optional custom title/cover, and where playback
last stopped so re-opening a book resumes instead of restarting."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LibraryChapter:
    chapter_id: str
    title: str
    order: int
    file_name: str  # relative to <book_id>/audio/
    duration_ms: int


@dataclass
class PlaybackPosition:
    chapter_id: str | None = None  # None = start of the book
    position_ms: int = 0
    updated_at: str = ""


@dataclass
class LibraryBook:
    id: str
    canonical_title: str
    chapters: list[LibraryChapter]
    total_duration_ms: int
    output_format: str
    source_path: str
    created_at: str
    custom_title: str | None = None
    cover_path: str | None = None  # None => generated placeholder cover
    playback: PlaybackPosition = field(default_factory=PlaybackPosition)

    def display_title(self) -> str:
        return self.custom_title or self.canonical_title
