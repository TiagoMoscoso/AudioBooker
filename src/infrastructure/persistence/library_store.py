"""Persists the audiobook library (§ new "Biblioteca"): a JSON index of
finished books plus their permanent per-chapter audio files, stored under
`library_dir`, decoupled from the resumable-session workspace under
`sessions/`. Covers are normalized to a poster-shaped JPEG via QImage —
Pillow is not a runtime dependency of this app."""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from domain.library import LibraryBook, LibraryChapter, PlaybackPosition
from infrastructure.persistence.atomic_write import atomic_write_json

_COVER_WIDTH = 480
_COVER_HEIGHT = 720  # 2:3 poster/book-cover aspect ratio


class LibraryStore:
    def __init__(self, library_dir: Path) -> None:
        self._dir = library_dir
        self._index_path = library_dir / "library.json"

    # -- book directory layout ---------------------------------------------

    def book_dir(self, book_id: str) -> Path:
        return self._dir / book_id

    def audio_dir(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "audio"

    def cover_path_for(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "cover.jpg"

    # -- index CRUD ----------------------------------------------------

    def load(self) -> list[LibraryBook]:
        if not self._index_path.exists():
            return []
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        books = []
        for entry in data:
            books.append(self._from_dict(entry))
        return books

    def get(self, book_id: str) -> LibraryBook | None:
        for book in self.load():
            if book.id == book_id:
                return book
        return None

    def add(self, book: LibraryBook) -> None:
        books = self.load()
        books.insert(0, book)
        self._save_all(books)

    def update(self, book: LibraryBook) -> None:
        books = [book if b.id == book.id else b for b in self.load()]
        self._save_all(books)

    def delete(self, book_id: str) -> None:
        books = [b for b in self.load() if b.id != book_id]
        self._save_all(books)
        shutil.rmtree(self.book_dir(book_id), ignore_errors=True)

    def set_playback(self, book_id: str, position: PlaybackPosition) -> None:
        book = self.get(book_id)
        if book is None:
            return
        book.playback = position
        self.update(book)

    def set_custom_title(self, book_id: str, title: str) -> None:
        book = self.get(book_id)
        if book is None:
            return
        book.custom_title = title.strip() or None
        self.update(book)

    def set_cover(self, book_id: str, source_image_path: str) -> None:
        """Crops/resizes a user-picked image to a poster aspect ratio and
        stores it permanently alongside the book's audio."""
        image = QImage(source_image_path)
        if image.isNull():
            return
        scaled = image.scaled(
            _COVER_WIDTH, _COVER_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - _COVER_WIDTH) // 2)
        y = max(0, (scaled.height() - _COVER_HEIGHT) // 2)
        cropped = scaled.copy(x, y, _COVER_WIDTH, _COVER_HEIGHT)

        cover_path = self.cover_path_for(book_id)
        cover_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(str(cover_path), "JPG", quality=90)

        book = self.get(book_id)
        if book is not None:
            book.cover_path = str(cover_path)
            self.update(book)

    # -- internal ------------------------------------------------------

    def _save_all(self, books: list[LibraryBook]) -> None:
        atomic_write_json(self._index_path, [self._to_dict(b) for b in books])

    def _to_dict(self, book: LibraryBook) -> dict:
        return asdict(book)

    def _from_dict(self, data: dict) -> LibraryBook:
        chapters = [LibraryChapter(**c) for c in data["chapters"]]
        playback_data = data.get("playback") or {}
        playback = PlaybackPosition(
            chapter_id=playback_data.get("chapter_id"),
            position_ms=playback_data.get("position_ms", 0),
            updated_at=playback_data.get("updated_at", ""),
        )
        return LibraryBook(
            id=data["id"],
            canonical_title=data["canonical_title"],
            chapters=chapters,
            total_duration_ms=data["total_duration_ms"],
            output_format=data["output_format"],
            source_path=data.get("source_path", ""),
            created_at=data.get("created_at", ""),
            custom_title=data.get("custom_title"),
            cover_path=data.get("cover_path"),
            playback=playback,
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
