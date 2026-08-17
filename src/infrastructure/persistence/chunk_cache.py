"""Content-addressed cache for generated TTS chunks (§28): if a chunk with an
identical (text, voice, model, language, TTS params) hash already exists and
is valid, it's reused instead of re-synthesized — across sessions, not just
within a single resume."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


class ChunkCache:
    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir / "chunk_cache"

    @staticmethod
    def compute_hash(text: str, voice: str, model: str, language: str, params: str) -> str:
        payload = f"{text}\x1f{voice}\x1f{model}\x1f{language}\x1f{params}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @property
    def directory(self) -> Path:
        return self._dir

    def path_for(self, chunk_hash: str) -> Path:
        return self._dir / f"{chunk_hash}.wav"

    def get(self, chunk_hash: str) -> Path | None:
        path = self.path_for(chunk_hash)
        if path.exists() and path.stat().st_size > 0:
            return path
        return None

    def put(self, chunk_hash: str, source_path: Path) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, self.path_for(chunk_hash))

    def size_bytes(self) -> int:
        if not self._dir.exists():
            return 0
        return sum(f.stat().st_size for f in self._dir.rglob("*") if f.is_file())

    def clear(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)
