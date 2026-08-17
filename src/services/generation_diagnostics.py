"""Per-chunk and per-book generation diagnostics (§ quality warnings /
Audiobook Inspector): a plain, human-readable JSON artifact written once per
book so problems can be spotted before export — not something the UI
renders, and not a substitute for the manual/auditory verification steps in
the narration pipeline plan (no automated test suite per project
convention)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

_WORST_CHUNKS_KEPT = 20


@dataclass(frozen=True)
class ChunkDiagnostic:
    chunk_id: str
    attempt_count: int
    final_attempt_reason: str  # "ok" | "empty" | "silent" | "clipping" | "too_short" | "too_long" | ...
    duration_seconds: float
    peak: float
    flags: tuple[str, ...] = ()


@dataclass
class GenerationDiagnosticsReport:
    book_id: str
    total_chunks: int = 0
    chunks_with_warnings: int = 0
    total_retries: int = 0
    total_adaptive_splits: int = 0
    book_lufs_before: float | None = None
    book_lufs_after: float | None = None
    worst_chunks: list[ChunkDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "total_chunks": self.total_chunks,
            "chunks_with_warnings": self.chunks_with_warnings,
            "total_retries": self.total_retries,
            "total_adaptive_splits": self.total_adaptive_splits,
            "book_lufs_before": self.book_lufs_before,
            "book_lufs_after": self.book_lufs_after,
            "worst_chunks": [asdict(c) for c in self.worst_chunks],
        }


class DiagnosticsCollector:
    """Accumulates ChunkDiagnostic entries during a generation run (fed by
    ReliableSpeechSynthesizer, one per synthesized chunk) and rolls them up
    into a GenerationDiagnosticsReport once the book is fully mastered."""

    def __init__(self) -> None:
        self._entries: list[ChunkDiagnostic] = []

    def record(self, entry: ChunkDiagnostic) -> None:
        self._entries.append(entry)

    def build_report(
        self,
        book_id: str,
        book_lufs_before: float | None = None,
        book_lufs_after: float | None = None,
    ) -> GenerationDiagnosticsReport:
        with_warnings = [e for e in self._entries if e.flags]
        worst = sorted(with_warnings, key=lambda e: len(e.flags), reverse=True)[:_WORST_CHUNKS_KEPT]
        return GenerationDiagnosticsReport(
            book_id=book_id,
            total_chunks=len(self._entries),
            chunks_with_warnings=len(with_warnings),
            total_retries=sum(max(0, e.attempt_count - 1) for e in self._entries),
            total_adaptive_splits=sum(1 for e in self._entries if "adaptive_split_used" in e.flags),
            book_lufs_before=book_lufs_before,
            book_lufs_after=book_lufs_after,
            worst_chunks=worst,
        )
