"""Text preprocessing pipeline (§12). Each responsibility is isolated in its
own small class so cleanup behaviour can be reasoned about and tuned
independently instead of living in one monolithic function.

HeaderFooterCleaner works on raw per-page line lists (it needs repetition
across pages to detect running headers/footers) and is invoked by
PdfDocumentParser before paragraphs are assembled. The remaining steps are
format-agnostic and run uniformly over every parser's output via
TextPreprocessor, right after parsing and before chapter detection.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from domain.document import SCENE_BREAK_TOKEN


class WhitespaceNormalizer:
    """Collapses redundant whitespace while preserving paragraph breaks."""

    _TRAILING_SPACE = re.compile(r"[^\S\n]+\n")
    _MULTI_SPACE = re.compile(r"[^\S\n]+")
    _MULTI_BLANK_LINES = re.compile(r"\n{3,}")

    def process(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = self._TRAILING_SPACE.sub("\n", text)
        text = self._MULTI_SPACE.sub(" ", text)
        text = self._MULTI_BLANK_LINES.sub("\n\n", text)
        return text.strip()


class UnicodeNormalizer:
    """Normalizes unicode form (NFC) and removes/rewrites characters that
    read poorly or are invisible when narrated."""

    _REPLACEMENTS = {
        "\u00a0": " ",   # non-breaking space
        "\u200b": "",    # zero-width space
        "\ufeff": "",    # BOM
        "\u2028": "\n",  # line separator
        "\u2029": "\n\n",  # paragraph separator
    }

    def process(self, text: str) -> str:
        text = unicodedata.normalize("NFC", text)
        for src, dst in self._REPLACEMENTS.items():
            text = text.replace(src, dst)
        return text


class HyphenationFixer:
    """Rejoins words split by line-break hyphenation, e.g. 'exam-\\nple' ->
    'example', without touching legitimate hyphenated compounds (those never
    have a bare newline in the middle)."""

    _BROKEN_WORD = re.compile(r"(\w+)-\n(\w+)")

    def process(self, text: str) -> str:
        return self._BROKEN_WORD.sub(lambda m: f"{m.group(1)}{m.group(2)}", text)


class SceneBreakMarker:
    """Recognizes a section whose entire text is a divider-only scene-break
    marker (`***`, `* * *`, `— — —`, a bare em dash line, etc.) and replaces
    it with the shared SCENE_BREAK_TOKEN sentinel, so NarrationChunker can
    turn it into a pause instead of either discarding the narrative signal
    or (worse) narrating the symbols literally ("asterisk asterisk
    asterisk"). Markdown horizontal rules are already turned into this same
    sentinel by MarkdownDocumentParser itself, before this pipeline runs —
    this step exists for PDF/DOCX/TXT/MOBI, which have no equivalent native
    syntax and only ever see the divider as plain extracted text.

    Deliberately narrow: only symbol/whitespace-only lines match, so a real
    sentence that happens to contain a dash or asterisk is never touched."""

    _DIVIDER_ONLY = re.compile(r"^[*\-–—―_•·~=# ]{1,40}$")

    def process(self, text: str) -> str:
        if text == SCENE_BREAK_TOKEN:
            return text
        stripped = text.strip()
        if stripped and self._DIVIDER_ONLY.match(stripped):
            return SCENE_BREAK_TOKEN
        return text


class NarrationCleaner:
    """Strips residual markup/formatting artifacts that should not be spoken
    aloud: leftover markdown emphasis markers, HTML entities, and repeated
    punctuation runs."""

    _MARKDOWN_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|__|_|`)")
    _REPEATED_PUNCT = re.compile(r"([!?.,;:])\1{1,}")
    _HTML_ENTITY = re.compile(r"&(amp|lt|gt|quot|#39|nbsp);")
    _ENTITY_MAP = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "#39": "'", "nbsp": " "}

    def process(self, text: str) -> str:
        text = self._HTML_ENTITY.sub(lambda m: self._ENTITY_MAP[m.group(1)], text)
        text = self._MARKDOWN_EMPHASIS.sub("", text)
        text = self._REPEATED_PUNCT.sub(r"\1", text)
        return text


class HeaderFooterCleaner:
    """Detects lines that repeat across a large share of pages (running
    headers/footers) plus isolated page-number lines, and removes them.
    Operates on raw per-page line lists, before lines are reflowed into
    paragraphs."""

    def __init__(self, min_repetition_ratio: float = 0.4) -> None:
        self._min_repetition_ratio = min_repetition_ratio

    def process(self, pages: list[list[str]]) -> list[list[str]]:
        if len(pages) < 3:
            return pages

        counts: Counter[str] = Counter()
        for page in pages:
            candidates = set()
            if page:
                candidates.add(page[0].strip())
                candidates.add(page[-1].strip())
            for candidate in candidates:
                if candidate:
                    counts[candidate] += 1

        threshold = max(2, int(len(pages) * self._min_repetition_ratio))
        repeated = {line for line, count in counts.items() if count >= threshold}

        cleaned: list[list[str]] = []
        for page in pages:
            new_page = []
            for line in page:
                stripped = line.strip()
                if stripped in repeated:
                    continue
                if re.fullmatch(r"\d{1,4}", stripped):
                    continue
                new_page.append(line)
            cleaned.append(new_page)
        return cleaned


class TextPreprocessor:
    """Runs the universal cleanup pipeline over already-extracted section
    text. Format-specific concerns (header/footer stripping from raw PDF
    pages, DOCX heading styles, Markdown syntax, etc.) are handled by the
    parsers themselves before this pipeline runs."""

    def __init__(self) -> None:
        self._steps = [
            UnicodeNormalizer(),
            # Must run before NarrationCleaner, whose markdown-emphasis
            # stripping would otherwise destroy "* * *" (removing every "*")
            # before it could be recognized as a scene-break divider.
            SceneBreakMarker(),
            HyphenationFixer(),
            NarrationCleaner(),
            WhitespaceNormalizer(),
        ]

    def process(self, text: str) -> str:
        for step in self._steps:
            text = step.process(text)
        return text
