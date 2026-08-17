"""Per-chunk and per-book performance metrics (§ profiling): a plain JSON
artifact written once per book, sibling to generation_diagnostics.py's
quality report, so every other optimization in this pass (async chunk
writes, batched checkpoints, warm-up) can be measured before/after rather
than assumed. Not rendered by the UI."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import median


@dataclass(frozen=True)
class ChunkPerformanceRecord:
    chunk_id: str
    text_length: int
    # Best-effort *input*-token count, computed via the model's own
    # tokenizer purely for this metric (chatterbox's generate() doesn't
    # return token counts) — not the true output speech-token count. None
    # when unavailable (e.g. profiling disabled, tokenizer call failed).
    token_count: int | None
    cache_hit: bool
    generation_time_seconds: float  # 0.0 for cache hits — nothing was generated
    disk_write_time_seconds: float
    retry_count: int
    audio_duration_seconds: float

    @property
    def rtf(self) -> float | None:
        """generation_time / audio_duration. None for cache hits (no
        generation happened) or zero-duration audio (avoids divide-by-zero)."""
        if self.cache_hit or self.audio_duration_seconds <= 0:
            return None
        return self.generation_time_seconds / self.audio_duration_seconds


@dataclass
class GenerationPerformanceReport:
    book_id: str
    device: str
    device_name: str
    total_chunks: int
    cache_hit_chunks: int
    synthesized_chunks: int
    total_generation_time_seconds: float
    total_audio_duration_seconds: float
    average_rtf: float | None
    median_rtf: float | None
    peak_gpu_memory_bytes: int | None
    peak_gpu_memory_chunk_index: int | None
    checkpoint_flush_count: int
    total_checkpoint_flush_time_seconds: float
    wall_clock_generation_seconds: float
    wall_clock_finalize_seconds: float
    wall_clock_total_seconds: float
    chunks: list[ChunkPerformanceRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "device": self.device,
            "device_name": self.device_name,
            "total_chunks": self.total_chunks,
            "cache_hit_chunks": self.cache_hit_chunks,
            "synthesized_chunks": self.synthesized_chunks,
            "total_generation_time_seconds": self.total_generation_time_seconds,
            "total_audio_duration_seconds": self.total_audio_duration_seconds,
            "average_rtf": self.average_rtf,
            "median_rtf": self.median_rtf,
            "peak_gpu_memory_bytes": self.peak_gpu_memory_bytes,
            "peak_gpu_memory_chunk_index": self.peak_gpu_memory_chunk_index,
            "checkpoint_flush_count": self.checkpoint_flush_count,
            "total_checkpoint_flush_time_seconds": self.total_checkpoint_flush_time_seconds,
            "wall_clock_generation_seconds": self.wall_clock_generation_seconds,
            "wall_clock_finalize_seconds": self.wall_clock_finalize_seconds,
            "wall_clock_total_seconds": self.wall_clock_total_seconds,
            "chunks": [asdict(c) | {"rtf": c.rtf} for c in self.chunks],
        }


class PerformanceCollector:
    """Accumulates ChunkPerformanceRecord entries during a generation run and
    rolls them up into a GenerationPerformanceReport once the book is fully
    mastered. Mirrors services.generation_diagnostics.DiagnosticsCollector's
    shape deliberately, so both collectors are driven the same way from
    GenerateAudiobookService.run()/_finalize()."""

    def __init__(self) -> None:
        self._entries: list[ChunkPerformanceRecord] = []
        self._checkpoint_flush_times: list[float] = []
        self._peak_gpu_memory_bytes: int | None = None
        self._peak_gpu_memory_chunk_index: int | None = None

    def record(self, entry: ChunkPerformanceRecord) -> None:
        self._entries.append(entry)

    def record_checkpoint_flush(self, duration_seconds: float) -> None:
        self._checkpoint_flush_times.append(duration_seconds)

    def record_gpu_memory_sample(self, chunk_index: int, peak_bytes: int) -> None:
        """Called with the cumulative torch.cuda.max_memory_allocated()
        reading after each synthesized (non-cache-hit) chunk. Since that
        counter is monotonically non-decreasing for the process (reset only
        once per run), the last sample naturally is the run's peak — this
        just tracks which chunk first reached it."""
        if self._peak_gpu_memory_bytes is None or peak_bytes > self._peak_gpu_memory_bytes:
            self._peak_gpu_memory_bytes = peak_bytes
            self._peak_gpu_memory_chunk_index = chunk_index

    def build_report(
        self,
        book_id: str,
        device: str,
        device_name: str,
        wall_clock_generation_seconds: float,
        wall_clock_finalize_seconds: float,
    ) -> GenerationPerformanceReport:
        synthesized = [e for e in self._entries if not e.cache_hit]
        cache_hits = [e for e in self._entries if e.cache_hit]
        rtfs = [e.rtf for e in synthesized if e.rtf is not None]
        total_generation_time = sum(e.generation_time_seconds for e in synthesized)
        total_audio_duration = sum(e.audio_duration_seconds for e in self._entries)

        return GenerationPerformanceReport(
            book_id=book_id,
            device=device,
            device_name=device_name,
            total_chunks=len(self._entries),
            cache_hit_chunks=len(cache_hits),
            synthesized_chunks=len(synthesized),
            total_generation_time_seconds=total_generation_time,
            total_audio_duration_seconds=total_audio_duration,
            average_rtf=(sum(rtfs) / len(rtfs)) if rtfs else None,
            median_rtf=median(rtfs) if rtfs else None,
            peak_gpu_memory_bytes=self._peak_gpu_memory_bytes,
            peak_gpu_memory_chunk_index=self._peak_gpu_memory_chunk_index,
            checkpoint_flush_count=len(self._checkpoint_flush_times),
            total_checkpoint_flush_time_seconds=sum(self._checkpoint_flush_times),
            wall_clock_generation_seconds=wall_clock_generation_seconds,
            wall_clock_finalize_seconds=wall_clock_finalize_seconds,
            wall_clock_total_seconds=wall_clock_generation_seconds + wall_clock_finalize_seconds,
            chunks=list(self._entries),
        )
