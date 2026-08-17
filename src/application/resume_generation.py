"""Detects and prepares resumption of an interrupted generation session
(§26)."""
from __future__ import annotations

from dataclasses import dataclass

from domain.chapter import Chapter
from domain.narration import NarrationSettings
from infrastructure.persistence.checkpoint_store import CheckpointStore, GenerationManifest

_TERMINAL_STATUSES = {"completed", "cancelled"}


@dataclass
class ResumableSession:
    manifest: GenerationManifest
    completed_chunks: int
    total_chunks: int

    @property
    def percent_complete(self) -> int:
        if self.total_chunks == 0:
            return 100
        return round(100 * self.completed_chunks / self.total_chunks)


class ResumeGenerationService:
    def __init__(self, checkpoint_store: CheckpointStore) -> None:
        self._checkpoint_store = checkpoint_store

    def find_incomplete(self) -> list[ResumableSession]:
        results = []
        for manifest in self._checkpoint_store.list_sessions():
            if manifest.status in _TERMINAL_STATUSES:
                continue
            total = len(manifest.chunks)
            completed = sum(1 for c in manifest.chunks.values() if c.completed)
            if total == 0 or completed == total:
                continue
            results.append(ResumableSession(manifest=manifest, completed_chunks=completed, total_chunks=total))
        return results

    def discard(self, session_id: str) -> None:
        self._checkpoint_store.delete(session_id)

    def prepare_resume(self, manifest: GenerationManifest) -> tuple[list[Chapter], NarrationSettings] | None:
        """Reconstructs the exact chapters + narration settings a session was
        started with, so `GenerateAudiobookService.run(...)` can continue it
        after a full app restart without re-importing or asking the user to
        redo their chapter edits. Returns None if the session's chapters.json
        is missing (e.g. a session directory was manually tampered with)."""
        chapters = self._checkpoint_store.load_chapters(manifest.session_id)
        if chapters is None or not manifest.narration_settings:
            return None
        settings = NarrationSettings.from_dict(manifest.narration_settings)
        return chapters, settings
