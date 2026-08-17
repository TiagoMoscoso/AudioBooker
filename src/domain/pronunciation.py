"""Domain model for pronunciation/abbreviation rules: a small, inspectable
find-and-replace system applied before TTS (never a heavyweight NLP
dependency, consistent with the project's regex-driven text-cleanup style).

Rules serve two purposes depending on category:
  - "abbreviation": short forms like "Dr."/"Sr." — NarrationChunker consults
    `abbreviation_tokens()` to avoid splitting a sentence at the abbreviation's
    period, and SpokenFormNormalizer applies the same rule's `replacement` to
    expand it to a full spoken word ("Dr." -> "Doctor"/"Doutor"). An
    abbreviation with no natural full-word expansion can leave `replacement`
    empty — it still protects sentence splitting, it just isn't expanded.
  - "pronunciation" / "number_exception": plain word/phrase substitutions
    (e.g. "SQL" -> "sequel"), applied only by SpokenFormNormalizer.

`language` is either a NarrationLanguage value ("pt"/"en") or "any" for
rules that apply regardless of narration language (most abbreviations are
short enough that this is safe and matches the original hardcoded set,
which never distinguished PT from EN either).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_WORD_TYPE = "word"
_REGEX_TYPE = "regex"
_ABBREVIATION_CATEGORY = "abbreviation"


@dataclass(frozen=True)
class PronunciationRule:
    language: str
    match: str
    match_type: str = _WORD_TYPE  # "word" | "regex"
    case_sensitive: bool = False
    replacement: str = ""
    category: str = "pronunciation"  # "abbreviation" | "pronunciation" | "number_exception"

    def applies_to(self, language: str) -> bool:
        return self.language == "any" or self.language == language

    def compile(self) -> re.Pattern:
        flags = 0 if self.case_sensitive else re.IGNORECASE
        if self.match_type == _REGEX_TYPE:
            return re.compile(self.match, flags)
        if self.category == _ABBREVIATION_CATEGORY:
            # Abbreviations are matched together with their trailing period,
            # so expansion also removes the now-meaningless period ("Dr." ->
            # "Doctor", not "Doctor.").
            return re.compile(rf"\b{re.escape(self.match)}\.", flags)
        return re.compile(rf"\b{re.escape(self.match)}\b", flags)


@dataclass(frozen=True)
class PronunciationRuleSet:
    rules: tuple[PronunciationRule, ...] = field(default_factory=tuple)

    def abbreviation_tokens(self) -> frozenset[str]:
        """Lowercased abbreviation match strings (no trailing period),
        language-agnostic — used by NarrationChunker's sentence-boundary
        protection, which itself has no notion of narration language."""
        return frozenset(
            rule.match.lower() for rule in self.rules if rule.category == _ABBREVIATION_CATEGORY
        )

    def apply(self, text: str, language: str) -> str:
        """Applies every rule whose replacement is non-empty and whose
        language matches (or is "any"), longest match first so a longer
        phrase rule ("Ph.D.") is not shadowed by a shorter overlapping one."""
        applicable = [
            rule for rule in self.rules if rule.applies_to(language) and rule.replacement
        ]
        applicable.sort(key=lambda r: len(r.match), reverse=True)
        for rule in applicable:
            pattern = rule.compile()
            text = pattern.sub(lambda m, r=rule: r.replacement, text)
        return text

    def merged_with(self, other: "PronunciationRuleSet") -> "PronunciationRuleSet":
        """Merges two rule sets, with `other`'s rules taking precedence on an
        exact (language, match, category) conflict — used to layer bundled
        defaults < global user rules < per-book overrides."""
        by_key: dict[tuple[str, str, str], PronunciationRule] = {
            (r.language, r.match.lower(), r.category): r for r in self.rules
        }
        for rule in other.rules:
            by_key[(rule.language, rule.match.lower(), rule.category)] = rule
        return PronunciationRuleSet(rules=tuple(by_key.values()))

    def to_dicts(self) -> list[dict]:
        return [
            {
                "language": r.language,
                "match": r.match,
                "match_type": r.match_type,
                "case_sensitive": r.case_sensitive,
                "replacement": r.replacement,
                "category": r.category,
            }
            for r in self.rules
        ]

    @staticmethod
    def from_dicts(data: list[dict]) -> "PronunciationRuleSet":
        rules = tuple(
            PronunciationRule(
                language=d["language"],
                match=d["match"],
                match_type=d.get("match_type", _WORD_TYPE),
                case_sensitive=d.get("case_sensitive", False),
                replacement=d.get("replacement", ""),
                category=d.get("category", "pronunciation"),
            )
            for d in data
        )
        return PronunciationRuleSet(rules=rules)
