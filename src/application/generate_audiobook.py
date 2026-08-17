"""GenerateAudiobookService: orchestrates text normalization -> chunking ->
Chatterbox -> checkpoint -> post-processing -> whole-book mastering for a
full audiobook (§21-§32), reporting progress via a callback so the
presentation layer can drive it from a background thread without ever
blocking the UI (§23, §24). Never calls Chatterbox directly — only through
SpeechSynthesizer (§15); quality validation/retry, when enabled, lives
entirely inside that injected synthesizer
(infrastructure.tts.reliable_synthesizer.ReliableSpeechSynthesizer), not here."""
from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import numpy as np

from domain.chapter import Chapter
from domain.generation import (
    GenerationProgress,
    GenerationState,
    OutputFormat,
    OutputSettings,
)
from domain.narration import NarrationSettings
from infrastructure.audio.mastering import LoudnessMaster
from infrastructure.audio.post_processor import (
    CHUNK_PAUSE_MS,
    PARAGRAPH_PAUSE_MS,
    SCENE_BREAK_PAUSE_MS,
    AudioPostProcessor,
)
from infrastructure.persistence.atomic_write import atomic_write_json
from infrastructure.persistence.checkpoint_store import (
    ChapterCheckpoint,
    CheckpointStore,
    ChunkCheckpoint,
    GenerationManifest,
)
from infrastructure.persistence.chunk_cache import ChunkCache
from infrastructure.tts.hardware import HardwareDetector
from infrastructure.tts.synthesizer import AudioSegment, SpeechRequest, SpeechSynthesizer
from services.filename_sanitizer import FilenameSanitizer
from services.generation_diagnostics import ChunkDiagnostic, DiagnosticsCollector
from services.generation_profiler import ChunkPerformanceRecord, PerformanceCollector
from services.narration_chunker import ChunkBoundary, NarrationChunk, NarrationChunker
from services.spoken_form_normalizer import SpokenFormNormalizer

_FALLBACK_SAMPLE_RATE = 24000  # used only if every chunk was already cached/complete

_BOUNDARY_PAUSE_MS = {
    ChunkBoundary.CHUNK.value: CHUNK_PAUSE_MS,
    ChunkBoundary.PARAGRAPH.value: PARAGRAPH_PAUSE_MS,
    ChunkBoundary.SCENE_BREAK.value: SCENE_BREAK_PAUSE_MS,
}

# Checkpoint batching (§ CPU/GPU overlap): manifest.json is a full-book
# fsync'd rewrite (infrastructure.persistence.checkpoint_store.CheckpointStore
# .save), so doing it after every single chunk is the single most wasteful
# thing the old sequential loop did. Batching is safe because ChunkCache is
# content-addressed and independent of manifest state: _ChunkWriteQueue always
# does ChunkCache.put() in the same step as the WAV write (never deferred), so
# even if the manifest checkpoint lags behind what's actually on disk after a
# crash, a resumed run still gets a ChunkCache hit for any chunk whose WAV
# already exists — worst case is a redundant cache-hit-and-copy, never
# redundant GPU synthesis.
_CHECKPOINT_FLUSH_EVERY_N_CHUNKS = 5
_CHECKPOINT_FLUSH_EVERY_SECONDS = 5.0
# Bounded so a slow disk can never let unbounded synthesized audio pile up in
# memory (backpressure) — the GPU thread blocks on submit() once this fills.
_WRITE_QUEUE_MAXSIZE = 2
_PROGRESS_MIN_INTERVAL_SECONDS = 0.2


def _throttle_progress(
    callback: Callable[[GenerationProgress], None],
) -> Callable[[GenerationProgress], None]:
    """Rate-limits the high-frequency per-chunk GENERATING_AUDIO progress
    event to at most once per _PROGRESS_MIN_INTERVAL_SECONDS. Every other
    state (chapter/finalize/terminal transitions) always passes through
    immediately — those are infrequent and often UI-meaningful (e.g. the
    CANCELLED/COMPLETED terminal states must never be dropped)."""
    last_emit_at = 0.0

    def wrapped(progress: GenerationProgress) -> None:
        nonlocal last_emit_at
        now = time.monotonic()
        if (
            progress.state != GenerationState.GENERATING_AUDIO
            or now - last_emit_at >= _PROGRESS_MIN_INTERVAL_SECONDS
        ):
            last_emit_at = now
            callback(progress)

    return wrapped


class GenerationCancelled(Exception):
    pass


@dataclass
class GenerationResult:
    session_id: str
    book_id: str
    chapters: list[dict]  # {chapter_id, title, order, file_name, duration_ms}
    total_duration_ms: int
    output_format: str


@dataclass
class _PendingChunkWrite:
    """One chunk's worth of disk I/O, handed off from the GPU/main thread to
    _ChunkWriteQueue so the main thread can move on to the next chunk
    immediately instead of blocking on soundfile writes / cache copies /
    checkpoint fsyncs. Exactly one of `source`/`segment` is set."""

    chunk_id: str
    chunk: ChunkCheckpoint
    chunk_path: Path
    text_hash: str
    source: Path | None  # cache-hit: bytes to copy
    segment: AudioSegment | None  # freshly synthesized: bytes to write
    diagnostic: ChunkDiagnostic | None
    perf: ChunkPerformanceRecord | None


class _ChunkWriteQueue:
    """Single background thread performing all per-chunk disk I/O (WAV
    write/cache copy, ChunkCache.put, checkpoint bookkeeping) so the one GPU
    worker thread can start the next chunk's model.generate() immediately
    instead of blocking on I/O. This class never calls the synthesizer —
    concurrency here is strictly "GPU generates chunk N+1 while this thread
    persists chunk N," matching the codebase's "estabilidade > paralelismo
    agressivo" principle (see infrastructure.tts.model_manager) of never
    running two simultaneous model.generate() calls."""

    def __init__(
        self,
        checkpoint_store: CheckpointStore,
        chunk_cache: ChunkCache,
        diagnostics: DiagnosticsCollector,
        performance: PerformanceCollector,
        manifest: GenerationManifest,
        manifest_lock: threading.Lock,
        flush_every_n: int = _CHECKPOINT_FLUSH_EVERY_N_CHUNKS,
        flush_every_seconds: float = _CHECKPOINT_FLUSH_EVERY_SECONDS,
    ) -> None:
        self._checkpoint_store = checkpoint_store
        self._chunk_cache = chunk_cache
        self._diagnostics = diagnostics
        self._performance = performance
        self._manifest = manifest
        self._manifest_lock = manifest_lock
        self._flush_every_n = flush_every_n
        self._flush_every_seconds = flush_every_seconds
        self._queue: queue.Queue[_PendingChunkWrite | None] = queue.Queue(maxsize=_WRITE_QUEUE_MAXSIZE)
        self._error: Exception | None = None
        self._pending_since_flush = 0
        self._last_flush = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="ChunkWriteQueue", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def submit(self, item: _PendingChunkWrite) -> None:
        self.check_error()
        self._queue.put(item)  # blocks if full — this is the backpressure

    def check_error(self) -> None:
        if self._error is not None:
            raise self._error

    def drain_and_flush(self) -> None:
        """Blocks until every queued item has been written to disk, then
        always performs one checkpoint save regardless of the batching
        cadence. Call before any point that depends on every chunk actually
        being on disk (cancel, before _finalize reads chunk WAVs, run end)."""
        self._queue.join()
        self.check_error()
        self._flush_checkpoint()

    def stop(self) -> None:
        """Terminates the writer thread. Never raises — meant to be called
        from a `finally` block, where raising would mask whatever exception
        (if any) is already propagating. Any write error is surfaced through
        check_error()/drain_and_flush() during normal operation instead."""
        self._queue.put(None)
        self._thread.join()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            try:
                self._write_one(item)
            except Exception as exc:  # noqa: BLE001 - surfaced via check_error()
                self._error = exc
            finally:
                self._queue.task_done()

    def _write_one(self, item: _PendingChunkWrite) -> None:
        t0 = time.perf_counter()
        item.chunk_path.parent.mkdir(parents=True, exist_ok=True)
        if item.segment is not None:
            item.segment.save(item.chunk_path)
            # Cache-put happens in the same step as the WAV write (never
            # deferred) — this is what keeps the "a stale/lagging checkpoint
            # still cache-hits on resume" guarantee true by construction.
            self._chunk_cache.put(item.text_hash, item.chunk_path)
        else:
            item.chunk_path.write_bytes(item.source.read_bytes())
        disk_write_time = time.perf_counter() - t0

        with self._manifest_lock:
            item.chunk.completed = True

        if item.diagnostic is not None:
            self._diagnostics.record(item.diagnostic)
        if item.perf is not None:
            self._performance.record(replace(item.perf, disk_write_time_seconds=disk_write_time))

        self._pending_since_flush += 1
        due = (
            self._pending_since_flush >= self._flush_every_n
            or time.monotonic() - self._last_flush >= self._flush_every_seconds
        )
        if due:
            self._flush_checkpoint()

    def _flush_checkpoint(self) -> None:
        t0 = time.perf_counter()
        with self._manifest_lock:
            self._checkpoint_store.save(self._manifest)
        self._performance.record_checkpoint_flush(time.perf_counter() - t0)
        self._pending_since_flush = 0
        self._last_flush = time.monotonic()


class GenerateAudiobookService:
    def __init__(
        self,
        synthesizer: SpeechSynthesizer,
        checkpoint_store: CheckpointStore,
        chunk_cache: ChunkCache,
        library_dir: Path,
        post_processor: AudioPostProcessor | None = None,
        chunker: NarrationChunker | None = None,
        normalizer: SpokenFormNormalizer | None = None,
        loudness_master: LoudnessMaster | None = None,
        sanitizer: FilenameSanitizer | None = None,
    ) -> None:
        self._synthesizer = synthesizer
        self._checkpoint_store = checkpoint_store
        self._chunk_cache = chunk_cache
        self._library_dir = library_dir
        self._post_processor = post_processor or AudioPostProcessor()
        self._chunker = chunker or NarrationChunker()
        self._normalizer = normalizer or SpokenFormNormalizer()
        self._loudness_master = loudness_master or LoudnessMaster()
        self._sanitizer = sanitizer or FilenameSanitizer()

    # -- session setup ----------------------------------------------------

    def start_session(
        self,
        book_title: str,
        source_path: str,
        chapters: list[Chapter],
        settings: NarrationSettings,
        output_settings: OutputSettings,
    ) -> GenerationManifest:
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        included_chapters = [c for c in chapters if c.included]

        chapter_checkpoints: list[ChapterCheckpoint] = []
        chunk_checkpoints: dict[str, ChunkCheckpoint] = {}
        for chapter in included_chapters:
            chunks = self._chunk_chapter(chapter.text, settings)
            chunk_ids = [f"{chapter.id}:{idx:04d}" for idx in range(len(chunks))]
            chapter_checkpoints.append(ChapterCheckpoint(
                chapter_id=chapter.id, title=chapter.title, order=chapter.order, chunk_ids=chunk_ids,
            ))
            for idx, chunk in enumerate(chunks):
                chunk_id = chunk_ids[idx]
                text_hash = self._chunk_hash(chunk.text, settings)
                chunk_checkpoints[chunk_id] = ChunkCheckpoint(
                    chunk_id=chunk_id,
                    chapter_id=chapter.id,
                    index_in_chapter=idx,
                    text_hash=text_hash,
                    boundary=chunk.boundary_before.value,
                )

        manifest = self._checkpoint_store.create(
            session_id=session_id,
            book_title=book_title,
            language=settings.language.value,
            settings_hash=self._chunk_hash("", settings),
            output_settings=self._output_settings_dict(output_settings),
            chapters=chapter_checkpoints,
            source_path=source_path,
            narration_settings=settings.to_dict(),
        )
        manifest.chunks = chunk_checkpoints
        self._checkpoint_store.save(manifest)
        # Persists the exact reviewed chapters (including manual renames/
        # merges/exclusions) so resume after a full app restart can recover
        # them without re-running import + chapter detection (§26).
        self._checkpoint_store.save_chapters(session_id, chapters)
        return manifest

    # -- generation ---------------------------------------------------------

    def run(
        self,
        manifest: GenerationManifest,
        chapters: list[Chapter],
        settings: NarrationSettings,
        on_progress: Callable[[GenerationProgress], None],
        should_cancel: Callable[[], bool],
    ) -> GenerationResult:
        started_at = time.monotonic()
        on_progress = _throttle_progress(on_progress)
        self._checkpoint_store.validate_existing_chunks(manifest)
        manifest.status = GenerationState.GENERATING_AUDIO.value
        self._checkpoint_store.save(manifest)

        hardware = HardwareDetector().detect()
        self._reset_gpu_memory_stats()

        chapters_by_id = {c.id: c for c in chapters}
        total_chunks = sum(len(cc.chunk_ids) for cc in manifest.chapters)
        done_chunks = sum(1 for chunk in manifest.chunks.values() if chunk.completed)
        diagnostics = DiagnosticsCollector()
        performance = PerformanceCollector()

        manifest_lock = threading.Lock()
        writer = _ChunkWriteQueue(
            self._checkpoint_store, self._chunk_cache, diagnostics, performance, manifest, manifest_lock,
        )
        writer.start()
        try:
            for chapter_number, chapter_checkpoint in enumerate(manifest.chapters, start=1):
                chapter = chapters_by_id[chapter_checkpoint.chapter_id]
                # Both a pure function of (chapter.text, settings.language, the
                # injected normalizer/chunker's own rule state) — recomputing
                # here reproduces exactly what start_session() hashed, so no
                # extra checkpoint field is needed to persist chunk text itself.
                chunks = self._chunk_chapter(chapter.text, settings)

                for chunk_index, chunk_id in enumerate(chapter_checkpoint.chunk_ids):
                    writer.check_error()

                    if should_cancel():
                        # Everything submitted so far must actually be on disk
                        # and reflected in the manifest before we mark the
                        # session interrupted, or resume could think a chunk
                        # is missing when it was really just still queued.
                        writer.drain_and_flush()
                        # Persisted as "interrupted", not "cancelled": the point
                        # of checkpoint/resume (§26) is precisely to let the
                        # user pick this session back up later. CANCELLED is
                        # only used transiently to tell the progress screen the
                        # run stopped; ResumeGenerationService still offers it
                        # on the next launch. A session is only permanently
                        # gone once the user explicitly discards it.
                        manifest.status = "interrupted"
                        self._checkpoint_store.save(manifest)
                        on_progress(GenerationProgress(
                            state=GenerationState.CANCELLED,
                            chapter_index=chapter_number,
                            chapter_count=len(manifest.chapters),
                            chapter_title=chapter_checkpoint.title,
                            chunk_index=chunk_index,
                            chunk_count=len(chapter_checkpoint.chunk_ids),
                            elapsed_seconds=time.monotonic() - started_at,
                            fraction_complete=(done_chunks / total_chunks) if total_chunks else 1.0,
                        ))
                        raise GenerationCancelled()

                    on_progress(GenerationProgress(
                        state=GenerationState.GENERATING_AUDIO,
                        chapter_index=chapter_number,
                        chapter_count=len(manifest.chapters),
                        chapter_title=chapter_checkpoint.title,
                        chunk_index=chunk_index + 1,
                        chunk_count=len(chapter_checkpoint.chunk_ids),
                        elapsed_seconds=time.monotonic() - started_at,
                        fraction_complete=(done_chunks / total_chunks) if total_chunks else 1.0,
                    ))

                    chunk = manifest.chunks[chunk_id]
                    chunk_path = self._checkpoint_store.chunk_path(
                        manifest.session_id, chapter.id, chunk_index
                    )
                    if chunk.completed and chunk_path.exists():
                        continue  # already done in a previous run; counted in initial done_chunks

                    text = chunks[chunk_index].text
                    cached = self._chunk_cache.get(chunk.text_hash)
                    if cached is not None:
                        perf_record = ChunkPerformanceRecord(
                            chunk_id=chunk_id,
                            text_length=len(text),
                            token_count=None,
                            cache_hit=True,
                            generation_time_seconds=0.0,
                            disk_write_time_seconds=0.0,
                            retry_count=0,
                            audio_duration_seconds=self._probe_duration(cached),
                        )
                        writer.submit(_PendingChunkWrite(
                            chunk_id=chunk_id, chunk=chunk, chunk_path=chunk_path,
                            text_hash=chunk.text_hash, source=cached, segment=None,
                            diagnostic=None, perf=perf_record,
                        ))
                    else:
                        gen_start = time.perf_counter()
                        segment = self._synthesizer.synthesize(SpeechRequest(text=text, settings=settings))
                        generation_time = time.perf_counter() - gen_start

                        # Both properties are mutable single-instance state on
                        # the synthesizer, overwritten on every call — must be
                        # captured synchronously here, right after synthesize()
                        # returns, never read later from the writer thread.
                        diagnostic = getattr(self._synthesizer, "last_diagnostic", None)
                        diagnostic = (
                            replace(diagnostic, chunk_id=chunk_id)
                            if isinstance(diagnostic, ChunkDiagnostic) else None
                        )
                        retry_count = max(0, diagnostic.attempt_count - 1) if diagnostic else 0
                        token_count = getattr(self._synthesizer, "last_input_token_count", None)

                        peak_gpu_bytes = self._sample_gpu_memory()
                        if peak_gpu_bytes is not None:
                            performance.record_gpu_memory_sample(chunk_index, peak_gpu_bytes)

                        perf_record = ChunkPerformanceRecord(
                            chunk_id=chunk_id,
                            text_length=len(text),
                            token_count=token_count,
                            cache_hit=False,
                            generation_time_seconds=generation_time,
                            disk_write_time_seconds=0.0,
                            retry_count=retry_count,
                            audio_duration_seconds=segment.duration_seconds,
                        )
                        writer.submit(_PendingChunkWrite(
                            chunk_id=chunk_id, chunk=chunk, chunk_path=chunk_path,
                            text_hash=chunk.text_hash, source=None, segment=segment,
                            diagnostic=diagnostic, perf=perf_record,
                        ))

                    # Optimistic: counted at submission, not once the writer
                    # thread has actually flushed it to disk. With a queue
                    # depth of _WRITE_QUEUE_MAXSIZE this is at most a couple of
                    # chunks' cosmetic lag on the progress bar — an accepted
                    # tradeoff for not blocking the GPU thread on I/O.
                    done_chunks += 1

                on_progress(GenerationProgress(
                    state=GenerationState.PROCESSING_CHAPTER,
                    chapter_index=chapter_number,
                    chapter_count=len(manifest.chapters),
                    chapter_title=chapter_checkpoint.title,
                    chunk_index=len(chapter_checkpoint.chunk_ids),
                    chunk_count=len(chapter_checkpoint.chunk_ids),
                    elapsed_seconds=time.monotonic() - started_at,
                    fraction_complete=(done_chunks / total_chunks) if total_chunks else 1.0,
                ))

            writer.check_error()
            writer.drain_and_flush()
        finally:
            writer.stop()

        wall_clock_generation_seconds = time.monotonic() - started_at
        # Resolved once here rather than inline per-chunk: since writes are
        # now asynchronous, a chunk's file isn't guaranteed to exist the
        # instant it's produced — but by this point drain_and_flush() has
        # guaranteed every chunk actually made it to disk.
        sample_rate = self._probe_sample_rate(manifest) or _FALLBACK_SAMPLE_RATE

        manifest.status = GenerationState.FINALIZING.value
        self._checkpoint_store.save(manifest)
        result = self._finalize(
            manifest, sample_rate, on_progress, started_at, diagnostics,
            performance, wall_clock_generation_seconds, hardware.device, hardware.device_name,
        )
        # The finished audio now lives permanently under library_dir/<book_id>
        # (§ Biblioteca) — the resumable session workspace has served its
        # purpose and would otherwise linger forever, since nothing else
        # cleans up completed sessions (only interrupted ones are discarded
        # explicitly by the user, see ResumeGenerationService).
        self._checkpoint_store.delete(manifest.session_id)
        return result

    def _reset_gpu_memory_stats(self) -> None:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
        except ImportError:
            pass

    def _sample_gpu_memory(self) -> int | None:
        try:
            import torch
            if torch.cuda.is_available():
                return int(torch.cuda.max_memory_allocated())
        except ImportError:
            pass
        return None

    def _probe_duration(self, path: Path) -> float:
        import soundfile as sf
        info = sf.info(str(path))
        return (info.frames / info.samplerate) if info.samplerate else 0.0

    def _chunk_chapter(self, chapter_text: str, settings: NarrationSettings) -> list[NarrationChunk]:
        normalized = self._normalizer.normalize(chapter_text, settings.language.value)
        return self._chunker.chunk_chapter(normalized)

    # -- finalization -------------------------------------------------------

    def _finalize(
        self,
        manifest: GenerationManifest,
        sample_rate: int,
        on_progress: Callable[[GenerationProgress], None],
        started_at: float,
        diagnostics: DiagnosticsCollector,
        performance: PerformanceCollector,
        wall_clock_generation_seconds: float,
        device: str,
        device_name: str,
    ) -> GenerationResult:
        """Encodes one audio file per chapter and copies them straight into
        the book's permanent library folder, plus a lossless FLAC master per
        chapter (§ um único encode final / double-lossy-encode fix — see
        ExportBookService, which prefers these masters over decoding an
        already-lossy library file back to WAV). Chapter-level files (rather
        than a combined single file) are always produced here, regardless of
        any export-time format choice, because the player needs discrete
        files to skip between chapters — a combined single file is only ever
        built later, on demand, when exporting a ZIP (see ExportWorker).

        Loudness mastering is a whole-book pass, not independent per
        chapter: every chapter's boundary-aware, trimmed/faded PCM is
        assembled first, the whole book's loudness is measured once, and a
        single uniform gain is applied to every chapter — so chapters never
        drift apart in perceived volume the way independent per-chapter
        normalization could. This does mean the whole book's raw samples
        are held in memory simultaneously during the loudness measurement
        step; for a typical audiobook (mono float32 at the model's native
        24kHz) this is a few GB even for a very long book, which was judged
        an acceptable trade-off against the alternative of chapters that
        don't match in volume — revisit with a streaming/incremental LUFS
        aggregator if a long enough book makes this impractical in practice."""
        finalize_started_at = time.monotonic()
        chapter_count = len(manifest.chapters)
        output_format = OutputFormat(manifest.output_settings["audio_format"])
        bitrate = manifest.output_settings["bitrate_kbps"]

        workspace = self._checkpoint_store.session_dir(manifest.session_id)
        finalized_dir = workspace / "finalized"
        finalized_dir.mkdir(parents=True, exist_ok=True)

        book_id = f"book_{uuid.uuid4().hex[:12]}"
        audio_dir = self._library_dir / book_id / "audio"
        masters_dir = self._library_dir / book_id / "masters"
        audio_dir.mkdir(parents=True, exist_ok=True)
        masters_dir.mkdir(parents=True, exist_ok=True)
        ext = output_format.value

        # Pass 1: assemble every chapter (pauses/trim/fade), not yet
        # gain-adjusted.
        chapter_samples: list[np.ndarray] = []
        for i, chapter_checkpoint in enumerate(manifest.chapters, start=1):
            on_progress(GenerationProgress(
                state=GenerationState.PROCESSING_CHAPTER,
                chapter_index=i, chapter_count=chapter_count, chapter_title=chapter_checkpoint.title,
                chunk_index=len(chapter_checkpoint.chunk_ids), chunk_count=len(chapter_checkpoint.chunk_ids),
                elapsed_seconds=time.monotonic() - started_at, fraction_complete=0.7 * i / chapter_count,
            ))
            chunk_paths = [
                self._checkpoint_store.chunk_path(manifest.session_id, chapter_checkpoint.chapter_id, idx)
                for idx in range(len(chapter_checkpoint.chunk_ids))
            ]
            pauses_ms = self._pauses_for_chapter(chapter_checkpoint, manifest)
            samples = self._post_processor.concatenate(chunk_paths, sample_rate, pauses_ms=pauses_ms)
            chapter_samples.append(samples)

        # Pass 2: one whole-book loudness measurement/gain, applied uniformly.
        combined = np.concatenate(chapter_samples) if chapter_samples else np.zeros(0, dtype=np.float32)
        book_lufs_before = self._loudness_master.measure_lufs(combined, sample_rate)
        gain = self._loudness_master.compute_gain_for_target(combined, sample_rate)
        del combined  # release the temporary whole-book buffer once measured

        chapter_entries: list[dict] = []
        for i, (chapter_checkpoint, samples) in enumerate(zip(manifest.chapters, chapter_samples), start=1):
            on_progress(GenerationProgress(
                state=GenerationState.PROCESSING_CHAPTER,
                chapter_index=i, chapter_count=chapter_count, chapter_title=chapter_checkpoint.title,
                chunk_index=len(chapter_checkpoint.chunk_ids), chunk_count=len(chapter_checkpoint.chunk_ids),
                elapsed_seconds=time.monotonic() - started_at, fraction_complete=0.7 + 0.2 * i / chapter_count,
            ))
            mastered = self._loudness_master.true_peak_limit(samples * gain)
            chapter_wav = finalized_dir / f"{chapter_checkpoint.chapter_id}.wav"
            self._post_processor.write_wav(mastered, sample_rate, chapter_wav)
            duration_ms = int(len(mastered) / sample_rate * 1000) if sample_rate else 0

            chapter_name = self._sanitizer.sanitize(chapter_checkpoint.title, fallback=f"Capitulo {i}")
            file_name = f"{i:02d} - {chapter_name}.{ext}"
            master_path = masters_dir / f"{chapter_checkpoint.chapter_id}.flac"
            self._post_processor.write_flac(mastered, sample_rate, master_path)
            self._post_processor.encode(chapter_wav, audio_dir / file_name, output_format, bitrate)

            chapter_entries.append({
                "chapter_id": chapter_checkpoint.chapter_id,
                "title": chapter_checkpoint.title,
                "order": chapter_checkpoint.order,
                "file_name": file_name,
                "duration_ms": duration_ms,
            })

        # Gain is a single static multiplier over the whole book, so its
        # effect on integrated loudness is exactly 20*log10(gain) dB unless
        # the true-peak limiter additionally reduced an individual chapter
        # further — an acceptable approximation for a diagnostics figure
        # (the actual mastering decision above already used the true
        # pre-gain whole-book measurement, not this estimate).
        book_lufs_after = (
            book_lufs_before + 20 * np.log10(gain)
            if book_lufs_before != float("-inf") and gain > 0
            else book_lufs_before
        )
        report = diagnostics.build_report(book_id, book_lufs_before, float(book_lufs_after))
        atomic_write_json(self._library_dir / book_id / "diagnostics_report.json", report.to_dict())

        wall_clock_finalize_seconds = time.monotonic() - finalize_started_at
        performance_report = performance.build_report(
            book_id, device, device_name, wall_clock_generation_seconds, wall_clock_finalize_seconds,
        )
        atomic_write_json(
            self._library_dir / book_id / "performance_report.json", performance_report.to_dict()
        )

        on_progress(GenerationProgress(
            state=GenerationState.FINALIZING, chapter_index=chapter_count, chapter_count=chapter_count,
            chapter_title="", chunk_index=0, chunk_count=0,
            elapsed_seconds=time.monotonic() - started_at, fraction_complete=0.95,
        ))
        on_progress(GenerationProgress(
            state=GenerationState.COMPLETED, chapter_index=chapter_count, chapter_count=chapter_count,
            chapter_title="", chunk_index=0, chunk_count=0,
            elapsed_seconds=time.monotonic() - started_at, fraction_complete=1.0,
        ))

        return GenerationResult(
            session_id=manifest.session_id,
            book_id=book_id,
            chapters=chapter_entries,
            total_duration_ms=sum(c["duration_ms"] for c in chapter_entries),
            output_format=output_format.value,
        )

    def _pauses_for_chapter(
        self, chapter_checkpoint: ChapterCheckpoint, manifest: GenerationManifest
    ) -> list[int]:
        return [
            _BOUNDARY_PAUSE_MS.get(manifest.chunks[chunk_id].boundary, CHUNK_PAUSE_MS)
            for chunk_id in chapter_checkpoint.chunk_ids[1:]
        ]

    def _probe_sample_rate(self, manifest: GenerationManifest) -> int | None:
        for chapter_checkpoint in manifest.chapters:
            for idx in range(len(chapter_checkpoint.chunk_ids)):
                path = self._checkpoint_store.chunk_path(
                    manifest.session_id, chapter_checkpoint.chapter_id, idx
                )
                if path.exists():
                    return self._probe_sample_rate_of(path)
        return None

    def _probe_sample_rate_of(self, path: Path) -> int:
        import soundfile as sf
        return sf.info(str(path)).samplerate

    def _output_settings_dict(self, output_settings: OutputSettings) -> dict:
        return {
            "mode": output_settings.mode.value,
            "audio_format": output_settings.audio_format.value,
            "bitrate_kbps": output_settings.bitrate_kbps,
        }

    def _chunk_hash(self, text: str, settings: NarrationSettings) -> str:
        voice = str(settings.voice_reference.path) if settings.voice_reference else "default"
        model = "chatterbox-en" if settings.language.value == "en" else "chatterbox-multilingual-v3"
        params = (
            f"{settings.style.value}:{settings.exaggeration}:{settings.cfg_weight}:"
            f"{settings.temperature}:{settings.repetition_penalty}:{settings.min_p}:{settings.top_p}"
        )
        return ChunkCache.compute_hash(text, voice, model, settings.language.value, params)
