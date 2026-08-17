"""GenerationSession persistence + CheckpointStore (§26): tracks generation
progress so long books can resume after interruption. Workspace layout:

  sessions/
    session_xxx/
      manifest.json
      chapters.json
      chunks/
        <chapter_id>/
          0000.wav
          0001.wav

chapters.json holds the exact reviewed Chapter list (id/title/order/text/
included) a session was started with. This is what makes resume after a full
app restart actually work: chunk_ids in manifest.json are keyed by chapter_id,
and chapter_id used to be a fresh random UUID minted on every import — so a
second import of the same file (after restart) could never line back up with
an old manifest, and any manual chapter edits (rename/merge/reorder/exclude)
made before generation would be lost. Persisting the reviewed chapters
verbatim avoids re-deriving them and keeps resume exact.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from domain.chapter import Chapter
from infrastructure.persistence.atomic_write import atomic_write_json


@dataclass
class ChunkCheckpoint:
    chunk_id: str
    chapter_id: str
    index_in_chapter: int
    text_hash: str
    completed: bool = False
    # NarrationChunk.ChunkBoundary.value ("chunk" | "paragraph" |
    # "scene_break") — the type of pause AudioPostProcessor.concatenate
    # should insert before this chunk. Additive default so a manifest
    # written before this field existed still deserializes and resumes
    # cleanly (falling back to the old flat pause everywhere).
    boundary: str = "chunk"


@dataclass
class ChapterCheckpoint:
    chapter_id: str
    title: str
    order: int
    chunk_ids: list[str] = field(default_factory=list)


@dataclass
class GenerationManifest:
    session_id: str
    book_title: str
    language: str
    settings_hash: str
    output_settings: dict
    chapters: list[ChapterCheckpoint]
    chunks: dict[str, ChunkCheckpoint]
    status: str
    created_at: str
    updated_at: str
    source_path: str = ""
    # Serialized NarrationSettings (style/exaggeration/cfg_weight/voice
    # reference path), so a session can resume with the exact same narration
    # configuration after a full app restart, not just within one run.
    narration_settings: dict = field(default_factory=dict)


class CheckpointStore:
    def __init__(self, sessions_root: Path) -> None:
        self._sessions_root = sessions_root

    def session_dir(self, session_id: str) -> Path:
        return self._sessions_root / session_id

    def chunk_path(self, session_id: str, chapter_id: str, chunk_index: int) -> Path:
        return self.session_dir(session_id) / "chunks" / chapter_id / f"{chunk_index:04d}.wav"

    def manifest_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "manifest.json"

    def chapters_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "chapters.json"

    def save_chapters(self, session_id: str, chapters: list[Chapter]) -> None:
        atomic_write_json(self.chapters_path(session_id), [asdict(c) for c in chapters])

    def load_chapters(self, session_id: str) -> list[Chapter] | None:
        path = self.chapters_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return [Chapter(**c) for c in data]

    def create(
        self,
        session_id: str,
        book_title: str,
        language: str,
        settings_hash: str,
        output_settings: dict,
        chapters: list[ChapterCheckpoint],
        source_path: str = "",
        narration_settings: dict | None = None,
    ) -> GenerationManifest:
        now = self._now()
        manifest = GenerationManifest(
            session_id=session_id,
            book_title=book_title,
            language=language,
            settings_hash=settings_hash,
            output_settings=output_settings,
            chapters=chapters,
            chunks={},
            status="preparing_text",
            created_at=now,
            updated_at=now,
            source_path=source_path,
            narration_settings=narration_settings or {},
        )
        self.save(manifest)
        return manifest

    def save(self, manifest: GenerationManifest) -> None:
        manifest.updated_at = self._now()
        atomic_write_json(self.manifest_path(manifest.session_id), asdict(manifest))

    def load(self, session_id: str) -> GenerationManifest | None:
        path = self.manifest_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return self._from_dict(data)

    def list_sessions(self) -> list[GenerationManifest]:
        if not self._sessions_root.exists():
            return []
        sessions = []
        for entry in sorted(self._sessions_root.iterdir()):
            if entry.is_dir():
                manifest = self.load(entry.name)
                if manifest:
                    sessions.append(manifest)
        return sessions

    def validate_existing_chunks(self, manifest: GenerationManifest) -> None:
        """Marks chunks whose audio file is missing/empty as incomplete, so
        resume regenerates only what's actually missing (§26 'validar chunks
        existentes')."""
        for chunk in manifest.chunks.values():
            path = self.chunk_path(manifest.session_id, chunk.chapter_id, chunk.index_in_chapter)
            if not path.exists() or path.stat().st_size == 0:
                chunk.completed = False

    def delete(self, session_id: str) -> None:
        shutil.rmtree(self.session_dir(session_id), ignore_errors=True)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _from_dict(self, data: dict) -> GenerationManifest:
        chapters = [ChapterCheckpoint(**c) for c in data["chapters"]]
        chunks = {k: ChunkCheckpoint(**v) for k, v in data["chunks"].items()}
        return GenerationManifest(
            session_id=data["session_id"],
            book_title=data["book_title"],
            language=data["language"],
            settings_hash=data["settings_hash"],
            output_settings=data["output_settings"],
            chapters=chapters,
            chunks=chunks,
            status=data["status"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            source_path=data.get("source_path", ""),
            narration_settings=data.get("narration_settings", {}),
        )
