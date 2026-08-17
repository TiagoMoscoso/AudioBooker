"""Application service: turns chapter candidates + parsed sections into
user-reviewable Chapter objects, and computes the word/chapter/duration
estimate shown after import (§33)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from domain.chapter import Chapter, ChapterCandidate
from domain.document import DocumentSection
from i18n import tr

# Average narrated speech pace, used only for the pre-generation estimate
# shown to the user; actual duration is computed from generated audio.
_WORDS_PER_MINUTE = 150


@dataclass
class DocumentEstimate:
    word_count: int
    chapter_count: int
    estimated_minutes: float


class AnalyzeDocumentService:
    def build_chapters(
        self, sections: list[DocumentSection], candidates: list[ChapterCandidate]
    ) -> list[Chapter]:
        if not candidates:
            return self._single_chapter(sections)

        boundaries = sorted(candidates, key=lambda c: c.start_section_index)
        chapters: list[Chapter] = []
        for i, candidate in enumerate(boundaries):
            start = candidate.start_section_index
            end = (
                boundaries[i + 1].start_section_index
                if i + 1 < len(boundaries)
                else len(sections)
            )
            body_sections = sections[start + 1 : end]
            text = "\n\n".join(s.text for s in body_sections if s.text.strip())
            if not text.strip():
                continue
            chapters.append(Chapter(
                id=str(uuid.uuid4()),
                title=candidate.title,
                order=len(chapters),
                text=text,
            ))

        return chapters or self._single_chapter(sections)

    def estimate(self, chapters: list[Chapter]) -> DocumentEstimate:
        included = [c for c in chapters if c.included]
        word_count = sum(len(c.text.split()) for c in included)
        return DocumentEstimate(
            word_count=word_count,
            chapter_count=len(included),
            estimated_minutes=word_count / _WORDS_PER_MINUTE,
        )

    def _single_chapter(self, sections: list[DocumentSection]) -> list[Chapter]:
        text = "\n\n".join(s.text for s in sections if s.text.strip())
        return [Chapter(id=str(uuid.uuid4()), title=tr("chapters.single_chapter_title"), order=0, text=text)]
