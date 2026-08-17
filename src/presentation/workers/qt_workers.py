"""QThread-based workers (§23): every call into application services that
could block (parsing, model loading, TTS, encoding, zipping) runs here, off
the UI thread, and reports back only through Qt signals — widgets are never
touched from a worker thread."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from application.analyze_document import AnalyzeDocumentService
from application.export_book import ExportBookService
from application.generate_audiobook import GenerateAudiobookService, GenerationCancelled
from application.generate_preview import GeneratePreviewService
from application.import_document import ImportDocumentService
from domain.chapter import Chapter
from domain.generation import OutputMode
from domain.library import LibraryBook
from domain.narration import NarrationLanguage, NarrationSettings
from infrastructure.parsers.base import ScannedPdfError
from infrastructure.persistence.checkpoint_store import GenerationManifest
from infrastructure.tts.model_manager import ChatterboxModelManager


class ImportWorker(QThread):
    succeeded = Signal(object, object, object)  # ParsedDocument, list[Chapter], DocumentEstimate
    # message, is_scanned_pdf — the flag lets the UI pick the right dialog
    # without sniffing translated message text for language-specific words.
    failed = Signal(str, bool)

    def __init__(
        self,
        import_service: ImportDocumentService,
        analyze_service: AnalyzeDocumentService,
        path: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._import_service = import_service
        self._analyze_service = analyze_service
        self._path = path

    def run(self) -> None:
        try:
            result = self._import_service.import_document(self._path)
            chapters = self._analyze_service.build_chapters(
                result.document.sections, result.chapter_candidates
            )
            estimate = self._analyze_service.estimate(chapters)
            self.succeeded.emit(result.document, chapters, estimate)
        except ScannedPdfError as exc:
            self.failed.emit(str(exc), True)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as an error message
            self.failed.emit(str(exc), False)


class PreviewWorker(QThread):
    succeeded = Signal(object)  # PreviewResult
    failed = Signal(str)

    def __init__(self, service: GeneratePreviewService, settings: NarrationSettings, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._settings = settings

    def run(self) -> None:
        try:
            result = self._service.generate(self._settings)
            self.succeeded.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ModelPrepareWorker(QThread):
    """Downloads/loads the Chatterbox model for one language off the UI
    thread (§16, §23). Used at startup to prepare the last-used language
    before the user reaches the import screen, so a multi-GB first-time
    download is visible up front instead of surfacing mid-click later."""

    succeeded = Signal()
    failed = Signal(str)

    def __init__(
        self, model_manager: ChatterboxModelManager, language: NarrationLanguage, parent=None
    ) -> None:
        super().__init__(parent)
        self._model_manager = model_manager
        self._language = language

    def run(self) -> None:
        try:
            self._model_manager.get_model(self._language)
            self.succeeded.emit()
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a recoverable warning
            self.failed.emit(str(exc))


class GenerationWorker(QThread):
    progress = Signal(object)  # GenerationProgress
    succeeded = Signal(object)  # GenerationResult
    cancelled = Signal()
    failed = Signal(str)

    def __init__(
        self,
        service: GenerateAudiobookService,
        manifest: GenerationManifest,
        chapters: list[Chapter],
        settings: NarrationSettings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._manifest = manifest
        self._chapters = chapters
        self._settings = settings
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            result = self._service.run(
                self._manifest,
                self._chapters,
                self._settings,
                on_progress=lambda p: self.progress.emit(p),
                should_cancel=lambda: self._cancel_requested,
            )
            self.succeeded.emit(result)
        except GenerationCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ExportWorker(QThread):
    """Zips a library book's audio into a user-chosen folder, off the UI
    thread — exporting a long book (esp. with single-file re-encoding) can
    take a while and must never block the player screen (§23)."""

    succeeded = Signal(object)  # Path to the created .zip
    failed = Signal(str)

    def __init__(
        self,
        service: ExportBookService,
        book: LibraryBook,
        destination_dir: Path,
        output_mode: OutputMode,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._book = book
        self._destination_dir = destination_dir
        self._output_mode = output_mode

    def run(self) -> None:
        try:
            zip_path = self._service.export(self._book, self._destination_dir, self._output_mode)
            self.succeeded.emit(zip_path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
