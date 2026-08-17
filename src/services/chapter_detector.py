"""Chapter detection with a three-tier priority system (§13):

1. Explicit structure — headings/titles already identified by the parser
   from TOC, DOCX styles, PDF outline, Markdown headings, MOBI structure.
2. Textual patterns — recognized chapter/part/prologue/epilogue markers.
3. Structural heuristics — short standalone lines surrounded by blank space,
   capitalization, relative length vs. neighboring paragraphs.

Each tier is tried in order; the first tier that yields any candidates wins,
per §13's stated priority (a document with real headings should never fall
through to the noisier heuristic tier).
"""
from __future__ import annotations

import re

from domain.chapter import ChapterCandidate, ChapterSource
from domain.document import SCENE_BREAK_TOKEN, DocumentSection, SectionKind

_KEYWORDS_PT = [
    r"cap[íi]tulo\s+[\divxlc]+",
    r"cap[íi]tulo\s+\w+",
    r"parte\s+[\divxlc]+",
    r"parte\s+\w+",
    r"pr[óo]logo",
    r"ep[íi]logo",
    r"introdu[çc][ãa]o",
]
_KEYWORDS_EN = [
    r"chapter\s+[\divxlc]+",
    r"chapter\s+\w+",
    r"part\s+[\divxlc]+",
    r"part\s+\w+",
    r"prologue",
    r"epilogue",
    r"introduction",
]
_TEXT_PATTERN = re.compile(
    r"^\s*(" + "|".join(_KEYWORDS_PT + _KEYWORDS_EN) + r")\s*[:.\-–—]?\s*.{0,60}$",
    re.IGNORECASE,
)

_LOW_SIGNAL_TITLES = {
    "notas", "referências", "referencias", "notes", "references",
    "índice", "indice", "index", "sumário", "sumario", "contents",
}

_EXPLICIT_HEADING_KINDS = {SectionKind.TITLE, SectionKind.HEADING_1, SectionKind.HEADING_2}


class ChapterDetector:
    def detect(self, sections: list[DocumentSection]) -> list[ChapterCandidate]:
        explicit = self._detect_explicit(sections)
        if explicit:
            return explicit
        pattern = self._detect_by_pattern(sections)
        if pattern:
            return pattern
        return self._detect_heuristic(sections)

    def _detect_explicit(self, sections: list[DocumentSection]) -> list[ChapterCandidate]:
        candidates: list[ChapterCandidate] = []
        for i, section in enumerate(sections):
            if section.kind in _EXPLICIT_HEADING_KINDS and section.text.strip():
                candidates.append(ChapterCandidate(
                    title=section.text.strip(),
                    order=len(candidates),
                    start_section_index=i,
                    source=ChapterSource.EXPLICIT_STRUCTURE,
                    confidence=1.0,
                ))
        return candidates

    def _detect_by_pattern(self, sections: list[DocumentSection]) -> list[ChapterCandidate]:
        candidates: list[ChapterCandidate] = []
        for i, section in enumerate(sections):
            text = section.text.strip()
            if not text or len(text) > 80:
                continue
            if _TEXT_PATTERN.match(text):
                candidates.append(ChapterCandidate(
                    title=text,
                    order=len(candidates),
                    start_section_index=i,
                    source=ChapterSource.TEXT_PATTERN,
                    confidence=0.9,
                ))
        return candidates

    def _detect_heuristic(self, sections: list[DocumentSection]) -> list[ChapterCandidate]:
        candidates: list[ChapterCandidate] = []
        for i, section in enumerate(sections):
            text = section.text.strip()
            if not text:
                continue
            confidence = self._score(text, sections, i)
            if confidence >= 0.55:
                candidates.append(ChapterCandidate(
                    title=text,
                    order=len(candidates),
                    start_section_index=i,
                    source=ChapterSource.HEURISTIC,
                    confidence=confidence,
                ))
        return candidates

    def _score(self, text: str, sections: list[DocumentSection], index: int) -> float:
        if text == SCENE_BREAK_TOKEN:
            # A scene-break marker (services.text_preprocessor.SceneBreakMarker
            # / MarkdownDocumentParser) is short, isolated by blank-ish
            # neighbors, and often reads as all-uppercase to str.isupper() —
            # exactly the shape this heuristic otherwise rewards — so it
            # would be misdetected as a chapter heading without this guard.
            return 0.0
        lowered = text.lower().strip(" .:-–—")
        if lowered in _LOW_SIGNAL_TITLES:
            return 0.0
        if re.fullmatch(r"\d{1,4}", text) or re.fullmatch(r"(19|20)\d{2}", text):
            return 0.0

        score = 0.0
        word_count = len(text.split())
        if word_count <= 8:
            score += 0.3
        if text.isupper() and word_count <= 8:
            score += 0.25
        elif text.istitle():
            score += 0.15

        prev_blank = index == 0 or not sections[index - 1].text.strip()
        next_blank = index == len(sections) - 1 or not sections[index + 1].text.strip()
        if prev_blank and next_blank:
            score += 0.2

        if index + 1 < len(sections):
            next_len = len(sections[index + 1].text.split())
            if word_count and next_len > word_count * 3:
                score += 0.15

        return min(score, 1.0)
