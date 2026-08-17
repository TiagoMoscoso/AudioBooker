"""Splits chapter text into TTS-safe chunks (§21): chapter -> paragraphs ->
sentences -> chunks bounded by ChunkingSettings, never breaking mid-sentence,
mid-abbreviation, or in the middle of a quoted line. Every chunk also carries
the type of narrative boundary that precedes it (plain continuation, new
paragraph, or scene break), which AudioPostProcessor uses to choose how long
a pause to insert before it (§ pausas inteligentes).

On chunk length limits: Chatterbox's public documentation does not state a
hard maximum input length (checked README + model card, see
AUDIOBOOKER_SPECS.md §21, §53 "documentar a decisão"). Its T3
text-to-speech-token backbone, like other autoregressive single-utterance TTS
models, tends to drift in pace or drop/garble the tail end on very long single
generations. ChunkingSettings defaults therefore keep each chunk to roughly
one short paragraph (~280 characters target, ~400 hard ceiling) as a
conservative, empirically-safe choice — not an arbitrary number — and expose
both as configuration so they can be tuned once more precise guidance is
available.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from domain.document import SCENE_BREAK_TOKEN

# Fallback default so NarrationChunker() stays usable standalone without any
# wiring. In normal operation the composition root injects the fuller,
# externally-editable set merged from services/data/pronunciation_defaults.json
# + user overrides (domain.pronunciation.PronunciationRuleSet.abbreviation_tokens),
# which is why abbreviation text/spelling itself lives there now, not here.
_DEFAULT_ABBREVIATIONS = frozenset({
    "sr", "sra", "srta", "dr", "dra", "prof", "profa", "eng", "exa", "exmo",
    "exma", "ltda", "vol", "pág", "pag", "art", "no", "nº", "gov", "av",
    "mr", "mrs", "ms", "st", "vs", "etc", "jr", "ave", "capt",
})

# Split right before a capital/number that follows sentence-ending punctuation
# and whitespace, so we don't cut abbreviations like "Dr." mid-name.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])(?=\s+[\"'“”)]*[A-ZÀ-Ú0-9])")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_CLAUSE_SPLIT = re.compile(r"(?<=[,;:])\s+")
_TRAILING_WORD = re.compile(r"[A-Za-zÀ-ÿ]+$")
_WHITESPACE = re.compile(r"\s+")


class ChunkBoundary(Enum):
    """What kind of narrative boundary precedes a chunk — consulted only for
    the gap *before* this chunk, never for the chunk's own contents."""

    CHUNK = "chunk"            # mid-paragraph continuation of the same sentence-packing run
    PARAGRAPH = "paragraph"    # first chunk of a new source paragraph
    SCENE_BREAK = "scene_break"  # first chunk right after a detected scene break


@dataclass(frozen=True)
class NarrationChunk:
    text: str
    boundary_before: ChunkBoundary
    # Reserved for a future multi-speaker/dialogue-attribution pass; no
    # detection populates this today (out of scope for this iteration).
    speaker_hint: str | None = None


@dataclass(frozen=True)
class ChunkingSettings:
    target_length: int = 280
    max_length: int = 400


def _hard_wrap_words(text: str, max_length: int) -> list[str]:
    """Word-boundary hard wrap: the last-resort splitter for a clause with no
    internal punctuation to break on. Unlike a raw character slice, this
    never drops text — every word from `text` ends up in the returned
    chunks, even if a single pathological word forces one chunk past
    max_length (an oversized chunk is preferable to silently losing text)."""
    words = [w for w in _WHITESPACE.split(text.strip()) if w]
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_length:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


class NarrationChunker:
    def __init__(
        self,
        settings: ChunkingSettings | None = None,
        abbreviation_tokens: frozenset[str] | None = None,
    ) -> None:
        self._settings = settings or ChunkingSettings()
        self._abbreviations = (
            abbreviation_tokens if abbreviation_tokens is not None else _DEFAULT_ABBREVIATIONS
        )

    def chunk_chapter(self, chapter_text: str) -> list[NarrationChunk]:
        chunks: list[NarrationChunk] = []
        pending_boundary = ChunkBoundary.PARAGRAPH
        for paragraph in self._split_paragraphs(chapter_text):
            if paragraph == SCENE_BREAK_TOKEN:
                pending_boundary = ChunkBoundary.SCENE_BREAK
                continue
            sentences = self._split_sentences(paragraph)
            for i, text in enumerate(self._pack_sentences(sentences)):
                boundary = pending_boundary if i == 0 else ChunkBoundary.CHUNK
                chunks.append(NarrationChunk(text=text, boundary_before=boundary))
            pending_boundary = ChunkBoundary.PARAGRAPH
        return [c for c in chunks if c.text.strip()]

    def _split_paragraphs(self, text: str) -> list[str]:
        return [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]

    def _split_sentences(self, paragraph: str) -> list[str]:
        raw_parts = _SENTENCE_BOUNDARY.split(paragraph)
        sentences: list[str] = []
        buffer = ""
        for part in raw_parts:
            # The split point sits right before the whitespace that follows
            # sentence-ending punctuation, so `part` already carries its own
            # leading space when it's a continuation — concatenate directly
            # instead of inserting another space (which would double it up).
            candidate = (buffer + part).strip() if buffer else part.strip()
            stripped_end = candidate.rstrip(".!?…\"'”)")
            last_word_match = _TRAILING_WORD.search(stripped_end)
            ends_in_abbreviation = (
                last_word_match is not None
                and last_word_match.group(0).lower() in self._abbreviations
                and not candidate.endswith(("...", "…"))
            )
            if ends_in_abbreviation:
                buffer = candidate
                continue
            buffer = ""
            sentences.append(candidate)
        if buffer:
            sentences.append(buffer)
        return [s for s in sentences if s.strip()]

    def _pack_sentences(self, sentences: list[str]) -> list[str]:
        settings = self._settings
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if len(sentence) > settings.max_length:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(self._split_long_sentence(sentence))
                continue

            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= settings.target_length:
                current = candidate
            elif not current:
                current = candidate
            else:
                chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
        return chunks

    def _split_long_sentence(self, sentence: str) -> list[str]:
        settings = self._settings
        parts = _CLAUSE_SPLIT.split(sentence)
        chunks: list[str] = []
        current = ""
        for part in parts:
            candidate = f"{current} {part}".strip() if current else part
            if len(candidate) <= settings.max_length:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""
            if len(part) > settings.max_length:
                # A single clause longer than max_length is rare but
                # possible (e.g. no internal punctuation); hard-wrap on word
                # boundaries as a last resort — never truncate (§ bug fix:
                # the previous `part[:max_length]` slice silently dropped
                # everything past the cut).
                chunks.extend(_hard_wrap_words(part, settings.max_length))
            else:
                current = part
        if current:
            chunks.append(current)
        return chunks
