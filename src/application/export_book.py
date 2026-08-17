"""ExportBookService: packages a library book's audio into a ZIP on demand —
the export-time counterpart to GenerateAudiobookService, decoupled from
generation itself so a ZIP is only ever built when the user explicitly asks
for one from the player screen (§ export). Chapters are always stored
per-file in the library (see GenerateAudiobookService._finalize); a combined
single file is only assembled here, at export time.

Prefers each chapter's lossless FLAC master (library_dir/<book_id>/masters/)
over decoding the already-encoded library file back to WAV — a book stored
as MP3 would otherwise be decoded then re-encoded a second time on export
(MP3 -> WAV -> MP3), stacking a second generation-loss pass on top of the
original TTS-WAV -> MP3 encode. Falls back to decode-then-reencode only for
books generated before masters existed, so older libraries still export."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import soundfile as sf

from domain.generation import OutputFormat, OutputMode
from domain.library import LibraryBook
from i18n import tr
from infrastructure.audio.post_processor import AudioPostProcessor
from infrastructure.packaging.zip_packager import ZipPackager
from services.filename_sanitizer import FilenameSanitizer

_EXPORT_BITRATE_KBPS = 128


class ExportBookService:
    def __init__(
        self,
        library_dir: Path,
        packager: ZipPackager | None = None,
        post_processor: AudioPostProcessor | None = None,
        sanitizer: FilenameSanitizer | None = None,
    ) -> None:
        self._library_dir = library_dir
        self._packager = packager or ZipPackager()
        self._post_processor = post_processor or AudioPostProcessor()
        self._sanitizer = sanitizer or FilenameSanitizer()

    def export(self, book: LibraryBook, destination_dir: Path, output_mode: OutputMode) -> Path:
        audio_dir = self._library_dir / book.id / "audio"
        safe_title = self._sanitizer.sanitize(book.display_title(), fallback="Audiobook")
        ordered_chapters = sorted(book.chapters, key=lambda c: c.order)
        manifest_dict = {
            "title": book.display_title(),
            "author": None,
            "chapters": [{"title": c.title, "order": c.order} for c in ordered_chapters],
            "tts_engine": "chatterbox",
            "created_at": book.created_at,
        }

        tmp_dir: Path | None = None
        try:
            if output_mode == OutputMode.SINGLE_FILE:
                files, tmp_dir = self._build_single_file(book, audio_dir, ordered_chapters, safe_title)
            else:
                files = {c.file_name: audio_dir / c.file_name for c in ordered_chapters}
            return self._packager.package(files, manifest_dict, destination_dir / f"{safe_title}.zip")
        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def _build_single_file(
        self, book: LibraryBook, audio_dir: Path, ordered_chapters: list, safe_title: str
    ) -> tuple[dict[str, Path], Path]:
        output_format = OutputFormat(book.output_format)
        tmp_dir = Path(tempfile.mkdtemp(prefix="audiobooker_export_"))
        masters_dir = self._library_dir / book.id / "masters"

        wav_paths: list[Path] = []
        sample_rate: int | None = None
        for chapter in ordered_chapters:
            master_path = masters_dir / f"{chapter.chapter_id}.flac"
            if master_path.exists():
                # Already lossless — read directly, no ffmpeg decode needed.
                source_path = master_path
            else:
                wav_path = tmp_dir / f"{chapter.chapter_id}.wav"
                self._post_processor.decode_to_wav(audio_dir / chapter.file_name, wav_path)
                source_path = wav_path
            chapter_rate = sf.info(str(source_path)).samplerate
            if sample_rate is None:
                sample_rate = chapter_rate
            elif chapter_rate != sample_rate:
                raise ValueError(
                    tr(
                        "error.sample_rate_mismatch",
                        path=source_path, expected=sample_rate, actual=chapter_rate,
                    )
                )
            wav_paths.append(source_path)

        combined = self._post_processor.concatenate_with_pauses(wav_paths, sample_rate or 24000)
        combined_wav = tmp_dir / "combined.wav"
        self._post_processor.write_wav(combined, sample_rate or 24000, combined_wav)

        out_name = f"{safe_title}.{output_format.value}"
        out_path = tmp_dir / out_name
        self._post_processor.encode(combined_wav, out_path, output_format, _EXPORT_BITRATE_KBPS)
        return {out_name: out_path}, tmp_dir
