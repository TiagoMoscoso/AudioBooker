"""Persists user settings (appearance, last chosen narration language, output
format) as a small JSON file in the platform config directory (§38)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir

from infrastructure.persistence.atomic_write import atomic_write_json

APP_NAME = "Audiobooker"


@dataclass
class AppSettings:
    appearance: str = "system"  # "system" | "light" | "dark"
    last_language: str = "pt"
    output_format: str = "mp3"
    ui_language: str = "en"  # "en" | "pt" — interface language, independent of narration language


class SettingsStore:
    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or Path(user_config_dir(APP_NAME))
        self._path = self._dir / "settings.json"

    def load(self) -> AppSettings:
        if not self._path.exists():
            return AppSettings()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return AppSettings(**{**asdict(AppSettings()), **data})
        except Exception:
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        atomic_write_json(self._path, asdict(settings))


def cache_dir() -> Path:
    return Path(user_cache_dir(APP_NAME))


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def library_dir() -> Path:
    return Path(user_config_dir(APP_NAME)) / "library"
