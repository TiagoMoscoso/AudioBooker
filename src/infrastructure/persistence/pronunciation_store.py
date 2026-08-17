"""Loads pronunciation/abbreviation rules (domain.pronunciation) from three
layered sources, later ones winning on conflict: bundled defaults shipped
with the app < global user rules (platform config dir, same pattern as
SettingsStore) < optional per-book overrides. Follows the same
platformdirs + JSON + atomic_write_json pattern used everywhere else in
infrastructure/persistence — no new persistence mechanism."""
from __future__ import annotations

import json
from pathlib import Path

from domain.pronunciation import PronunciationRuleSet
from infrastructure.persistence.atomic_write import atomic_write_json

_BUNDLED_DEFAULTS_PATH = Path(__file__).resolve().parent.parent.parent / "services" / "data" / "pronunciation_defaults.json"


class PronunciationStore:
    def __init__(self, config_dir: Path) -> None:
        self._global_path = config_dir / "pronunciation.json"

    def load_bundled_defaults(self) -> PronunciationRuleSet:
        if not _BUNDLED_DEFAULTS_PATH.exists():
            return PronunciationRuleSet()
        data = json.loads(_BUNDLED_DEFAULTS_PATH.read_text(encoding="utf-8"))
        return PronunciationRuleSet.from_dicts(data)

    def load_global(self) -> PronunciationRuleSet:
        if not self._global_path.exists():
            return PronunciationRuleSet()
        try:
            data = json.loads(self._global_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return PronunciationRuleSet()
        return PronunciationRuleSet.from_dicts(data)

    def save_global(self, rule_set: PronunciationRuleSet) -> None:
        atomic_write_json(self._global_path, rule_set.to_dicts())

    def load_book_overrides(self, book_dir: Path) -> PronunciationRuleSet:
        path = book_dir / "pronunciation_overrides.json"
        if not path.exists():
            return PronunciationRuleSet()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return PronunciationRuleSet()
        return PronunciationRuleSet.from_dicts(data)

    def save_book_overrides(self, book_dir: Path, rule_set: PronunciationRuleSet) -> None:
        atomic_write_json(book_dir / "pronunciation_overrides.json", rule_set.to_dicts())

    def load_effective(self, book_dir: Path | None = None) -> PronunciationRuleSet:
        """Merged rule set: bundled defaults < global user rules < per-book
        overrides (when a book directory is given)."""
        effective = self.load_bundled_defaults().merged_with(self.load_global())
        if book_dir is not None:
            effective = effective.merged_with(self.load_book_overrides(book_dir))
        return effective
