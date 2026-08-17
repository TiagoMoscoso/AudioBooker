"""Converts already-cleaned chapter text into text ready for the TTS engine:
ligature/typography cleanup, abbreviation expansion, number/date/currency
spoken-form conversion, then pronunciation-dictionary substitution.

Runs *after* TextPreprocessor (which is language-agnostic and runs once at
import time) and *after* NarrationLanguage is chosen — this is a distinct
pipeline stage because it needs the language, and because unlike the
import-time cleanup it should be safe to re-run verbatim (it's a pure
function of its inputs) so a resumed session reproduces identical chunk text
without needing extra checkpoint fields."""
from __future__ import annotations

import re

from domain.pronunciation import PronunciationRuleSet
from services.number_normalizer import NumberNormalizer

_LIGATURES = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬆ": "st",
}
_SMART_QUOTES = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "′": "'", "″": '"',
}
_DASH_NORMALIZE = re.compile(r"\s*[–—]\s*")


class SpokenFormNormalizer:
    def __init__(
        self,
        rule_set: PronunciationRuleSet | None = None,
        number_normalizer: NumberNormalizer | None = None,
    ) -> None:
        self._rule_set = rule_set or PronunciationRuleSet()
        self._numbers = number_normalizer or NumberNormalizer()

    def normalize(self, text: str, language: str) -> str:
        text = self._clean_typography(text)
        text = self._rule_set.apply(text, language)
        text = self._numbers.normalize(text, language)
        # A second rule pass lets pronunciation entries override anything a
        # number/abbreviation conversion just produced (e.g. a dictionary
        # entry for a spelled-out word the number pass emitted).
        text = self._rule_set.apply(text, language)
        return text

    def _clean_typography(self, text: str) -> str:
        for src, dst in _LIGATURES.items():
            text = text.replace(src, dst)
        for src, dst in _SMART_QUOTES.items():
            text = text.replace(src, dst)
        # Em/en dashes used as a narrative interruption read naturally as a
        # comma-length pause; a bare "-" glued to neighboring words (as
        # em/en dashes are in running text) would otherwise risk being read
        # as a hyphenated compound.
        text = _DASH_NORMALIZE.sub(", ", text)
        return text
