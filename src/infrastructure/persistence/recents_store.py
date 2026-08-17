"""Persists a small list of recently opened/generated books (§37) — metadata
only, never a copy of the source file itself."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from infrastructure.persistence.atomic_write import atomic_write_json

_MAX_RECENTS = 10


@dataclass
class RecentEntry:
    title: str
    source_path: str
    status: str  # e.g. "Gerado ontem", "42% concluído"
    updated_at: str
    session_id: str | None = None


class RecentsStore:
    def __init__(self, config_dir: Path) -> None:
        self._path = config_dir / "recents.json"

    def load(self) -> list[RecentEntry]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return [RecentEntry(**e) for e in data]
        except Exception:
            return []

    def add_or_update(self, entry: RecentEntry) -> None:
        entries = [e for e in self.load() if e.source_path != entry.source_path]
        entries.insert(0, entry)
        entries = entries[:_MAX_RECENTS]
        atomic_write_json(self._path, [asdict(e) for e in entries])
