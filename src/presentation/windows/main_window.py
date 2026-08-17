"""Main window: composes Home, Book, Generation, and Settings screens into a
single flow, wiring them to application services exclusively through
background QThread workers (§23). The window itself holds only navigation
and orchestration glue — no parsing/TTS/audio logic lives here (§41)."""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QMessageBox, QPushButton, QSizePolicy,
    QStackedWidget, QToolBar, QWidget,
)

import i18n
from application.analyze_document import AnalyzeDocumentService
from application.export_book import ExportBookService
from application.generate_audiobook import GenerateAudiobookService
from application.generate_preview import GeneratePreviewService
from application.import_document import ImportDocumentService
from application.resume_generation import ResumeGenerationService
from domain.generation import GenerationState, OutputSettings
from domain.library import LibraryBook, LibraryChapter, PlaybackPosition
from i18n import tr
from infrastructure.parsers.base import ScannedPdfError, UnsupportedDocumentError
from infrastructure.persistence.checkpoint_store import CheckpointStore
from infrastructure.persistence.chunk_cache import ChunkCache
from infrastructure.persistence.library_store import LibraryStore, now_iso
from infrastructure.persistence.pronunciation_store import PronunciationStore
from infrastructure.persistence.settings_store import SettingsStore
from infrastructure.tts.chatterbox_synthesizer import ChatterboxSpeechSynthesizer
from infrastructure.tts.model_manager import ChatterboxModelManager, ModelState
from infrastructure.tts.reliable_synthesizer import ReliableSpeechSynthesizer
from services.narration_chunker import NarrationChunker
from services.spoken_form_normalizer import SpokenFormNormalizer
from presentation.styles.theme import build_stylesheet
from presentation.widgets.book_screen import BookScreen
from presentation.widgets.generation_screen import GenerationScreen
from presentation.widgets.home_screen import HomeScreen
from presentation.widgets.player_screen import PlayerScreen
from presentation.widgets.preparing_screen import PreparingScreen
from presentation.widgets.settings_screen import SettingsScreen
from presentation.workers.qt_workers import (
    ExportWorker, GenerationWorker, ImportWorker, ModelPrepareWorker, PreviewWorker,
)

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        resources_dir: Path,
        sessions_dir: Path,
        cache_dir: Path,
        config_dir: Path,
        library_dir: Path,
        model_manager: ChatterboxModelManager,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Audiobooker")
        self.resize(1150, 740)

        logo_path = resources_dir / "logo.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        self._resources_dir = resources_dir
        self._library_dir = library_dir
        self._model_manager = model_manager
        self._import_service = ImportDocumentService()
        self._analyze_service = AnalyzeDocumentService()

        self._checkpoint_store = CheckpointStore(sessions_dir)
        self._chunk_cache = ChunkCache(cache_dir)
        self._settings_store = SettingsStore(config_dir)
        self._library_store = LibraryStore(library_dir)
        self._pronunciation_store = PronunciationStore(config_dir)
        self._resume_service = ResumeGenerationService(self._checkpoint_store)

        # Narration/audio quality pipeline: pronunciation rules (bundled
        # defaults + any user overrides) feed both sentence-boundary
        # abbreviation protection (chunker) and abbreviation/number/
        # pronunciation-dictionary expansion (normalizer); the raw Chatterbox
        # synthesizer is wrapped once here with automatic quality validation
        # + retry, so every caller (generation and preview alike) benefits
        # without needing to know about it.
        pronunciation_rules = self._pronunciation_store.load_effective()
        self._chunker = NarrationChunker(abbreviation_tokens=pronunciation_rules.abbreviation_tokens())
        self._normalizer = SpokenFormNormalizer(rule_set=pronunciation_rules)
        self._synthesizer = ReliableSpeechSynthesizer(ChatterboxSpeechSynthesizer(model_manager))
        self._generate_service = GenerateAudiobookService(
            self._synthesizer,
            self._checkpoint_store,
            self._chunk_cache,
            library_dir,
            chunker=self._chunker,
            normalizer=self._normalizer,
        )
        self._preview_service = GeneratePreviewService(self._synthesizer, cache_dir / "previews")
        self._export_service = ExportBookService(library_dir)

        self._app_settings = self._settings_store.load()
        i18n.set_language(self._app_settings.ui_language)  # before any widget is built
        self._current_document = None
        self._current_source_path: str | None = None
        self._active_manifest = None
        self._import_worker = None
        self._preview_worker = None
        self._generation_worker = None
        self._export_worker = None
        self._model_prepare_worker = None
        self._status_poll_timer = None

        self._build_ui()
        self._apply_theme(self._app_settings.appearance)
        self._settings_screen.set_appearance(self._app_settings.appearance)
        self._settings_screen.set_ui_language(self._app_settings.ui_language)
        self._refresh_library()
        self._refresh_settings_status()
        self._start_model_preparation()

    # -- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        back_button = QPushButton("←")
        back_button.setObjectName("IconButton")
        back_button.clicked.connect(self._go_home)
        toolbar.addWidget(back_button)

        self._toolbar_title_label = QLabel("Audiobooker")
        self._toolbar_title_label.setStyleSheet("font-weight: 600; padding-left: 4px;")
        toolbar.addWidget(self._toolbar_title_label)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        settings_button = QPushButton("⚙")
        settings_button.setObjectName("IconButton")
        settings_button.clicked.connect(self._show_settings)
        toolbar.addWidget(settings_button)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._preparing_screen = PreparingScreen(self._resources_dir / "logo.png")
        self._stack.addWidget(self._preparing_screen)

        self._home_screen = HomeScreen(self._resources_dir / "logo.png")
        self._home_screen.file_selected.connect(self._on_file_selected)
        self._home_screen.book_opened.connect(self._on_book_opened)
        self._home_screen.book_deleted.connect(self._on_book_deleted)
        self._home_screen.book_renamed.connect(self._on_book_renamed)
        self._home_screen.book_cover_changed.connect(self._on_book_cover_changed)
        self._stack.addWidget(self._home_screen)

        self._book_screen = BookScreen()
        self._book_screen.generate_preview_requested.connect(self._on_preview_requested)
        self._book_screen.generate_audiobook_requested.connect(self._on_generate_requested)
        self._stack.addWidget(self._book_screen)

        self._generation_screen = GenerationScreen()
        self._generation_screen.cancel_requested.connect(self._on_cancel_requested)
        self._stack.addWidget(self._generation_screen)

        self._player_screen = PlayerScreen()
        self._player_screen.rename_requested.connect(self._on_book_renamed)
        self._player_screen.cover_change_requested.connect(self._on_book_cover_changed)
        self._player_screen.playback_position_changed.connect(self._on_playback_position_changed)
        self._player_screen.export_requested.connect(self._on_export_requested)
        self._stack.addWidget(self._player_screen)

        self._settings_screen = SettingsScreen()
        self._settings_screen.appearance_changed.connect(self._on_appearance_changed)
        self._settings_screen.ui_language_changed.connect(self._on_ui_language_changed)
        self._settings_screen.clear_cache_requested.connect(self._on_clear_cache)
        self._settings_screen.open_cache_folder_requested.connect(self._on_open_cache_folder)
        self._stack.addWidget(self._settings_screen)

        self._stack.setCurrentWidget(self._preparing_screen)

    def _apply_theme(self, mode: str) -> None:
        resolved = mode
        if mode == "system":
            scheme = QGuiApplication.styleHints().colorScheme()
            resolved = "dark" if scheme.name == "Dark" else "light"
        self.setStyleSheet(build_stylesheet(resolved))

    def _go_home(self) -> None:
        self._stack.setCurrentWidget(self._home_screen)

    def _show_settings(self) -> None:
        self._refresh_settings_status()
        self._stack.setCurrentWidget(self._settings_screen)

    # -- UI language (§ i18n) -----------------------------------------------

    def _on_ui_language_changed(self, code: str) -> None:
        if code == i18n.current_language():
            return
        self._app_settings.ui_language = code
        self._settings_store.save(self._app_settings)
        i18n.set_language(code)
        self._retranslate_all()

    def _retranslate_all(self) -> None:
        self._preparing_screen.retranslate()
        self._home_screen.retranslate()
        self._book_screen.retranslate()
        self._generation_screen.retranslate()
        self._player_screen.retranslate()
        self._settings_screen.retranslate()

    # -- startup: model preparation (§16) -----------------------------------

    def _start_model_preparation(self) -> None:
        """Downloads/loads the last-used language's model before the user
        reaches the import screen, with real status feedback (§16, §24) —
        rather than lazily starting a possibly multi-GB first-time download
        the first time the user clicks "Gerar prévia" with no explanation
        of why it's slow."""
        language = self._last_language_enum()
        hardware = self._model_manager.hardware()
        self._preparing_screen.set_status(tr("preparing.checking_model"), hardware.device_name)
        self._stack.setCurrentWidget(self._preparing_screen)

        self._status_poll_timer = QTimer(self)
        self._status_poll_timer.setInterval(250)
        self._status_poll_timer.timeout.connect(self._poll_model_status)
        self._status_poll_timer.start()

        self._model_prepare_worker = ModelPrepareWorker(self._model_manager, language)
        self._model_prepare_worker.succeeded.connect(self._on_model_prepared)
        self._model_prepare_worker.failed.connect(self._on_model_prepare_failed)
        self._model_prepare_worker.start()

    def _poll_model_status(self) -> None:
        status = self._model_manager.status
        self._preparing_screen.set_status(status.message, status.device_name)

    def _on_model_prepared(self) -> None:
        if self._status_poll_timer is not None:
            self._status_poll_timer.stop()
        self._refresh_settings_status()
        self._enter_home()

    def _on_model_prepare_failed(self, message: str) -> None:
        if self._status_poll_timer is not None:
            self._status_poll_timer.stop()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("main.model_prepare_failed_title"))
        box.setText(tr("main.model_prepare_failed_text"))
        box.setDetailedText(message)
        retry_button = box.addButton(tr("main.retry"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("main.continue_without_prep"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() == retry_button:
            self._start_model_preparation()
        else:
            self._enter_home()

    def _enter_home(self) -> None:
        self._stack.setCurrentWidget(self._home_screen)
        self._check_resumable_sessions()

    # -- startup: resumable sessions (§26) ----------------------------------

    def _check_resumable_sessions(self) -> None:
        resumable = self._resume_service.find_incomplete()
        if not resumable:
            return
        session = resumable[0]
        manifest = session.manifest
        box = QMessageBox(self)
        box.setWindowTitle(tr("main.incomplete_generation_title"))
        box.setText(
            tr(
                "main.incomplete_generation_text",
                title=manifest.book_title,
                percent=session.percent_complete,
            )
        )
        continue_button = box.addButton(tr("main.continue_btn"), QMessageBox.ButtonRole.AcceptRole)
        discard_button = box.addButton(tr("main.discard_btn"), QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        if box.clickedButton() == continue_button:
            self._resume_session(manifest)
        elif box.clickedButton() == discard_button:
            self._resume_service.discard(manifest.session_id)

    def _resume_session(self, manifest) -> None:
        prepared = self._resume_service.prepare_resume(manifest)
        if prepared is None:
            QMessageBox.warning(self, tr("main.cannot_resume_title"), tr("main.cannot_resume_text"))
            return
        chapters, settings = prepared
        self._active_manifest = manifest
        self._current_source_path = manifest.source_path
        self._start_generation_worker(manifest, chapters, settings)

    # -- home / import -------------------------------------------------

    def _on_file_selected(self, path: str) -> None:
        self._current_source_path = path
        self._import_worker = ImportWorker(self._import_service, self._analyze_service, Path(path))
        self._import_worker.succeeded.connect(self._on_import_succeeded)
        self._import_worker.failed.connect(self._on_import_failed)
        self._import_worker.start()

    def _on_import_succeeded(self, document, chapters, estimate) -> None:
        self._current_document = document
        self._book_screen.set_document(document.title, document.author, document.metadata)
        self._book_screen.set_chapters(chapters)
        self._book_screen.set_language(self._last_language_enum())
        self._book_screen.set_estimate_text(
            i18n.format_estimate(estimate.word_count, estimate.chapter_count, estimate.estimated_minutes)
        )
        self._stack.setCurrentWidget(self._book_screen)

    def _on_import_failed(self, message: str, is_scanned_pdf: bool) -> None:
        if is_scanned_pdf:
            QMessageBox.warning(self, tr("main.scanned_pdf_title"), message)
        else:
            QMessageBox.critical(self, tr("main.import_failed_title"), tr("main.import_failed_text", message=message))

    def _last_language_enum(self):
        from domain.narration import NarrationLanguage
        try:
            return NarrationLanguage(self._app_settings.last_language)
        except ValueError:
            return NarrationLanguage.PORTUGUESE

    # -- preview (§19) -------------------------------------------------

    def _on_preview_requested(self) -> None:
        settings = self._book_screen.narration_settings()
        self._app_settings.last_language = settings.language.value
        self._settings_store.save(self._app_settings)

        self._book_screen.set_preview_generating(True)
        self._preview_worker = PreviewWorker(self._preview_service, settings)
        self._preview_worker.succeeded.connect(self._on_preview_succeeded)
        self._preview_worker.failed.connect(self._on_preview_failed)
        self._preview_worker.start()

    def _on_preview_succeeded(self, result) -> None:
        self._book_screen.set_preview_generating(False)
        self._book_screen.preview_player.load(result.audio_path)

    def _on_preview_failed(self, message: str) -> None:
        self._book_screen.set_preview_generating(False)
        QMessageBox.critical(self, tr("main.preview_failed_title"), tr("main.preview_failed_text", message=message))

    # -- generation (§21-§32) --------------------------------------------

    def _on_generate_requested(self) -> None:
        if not self._current_document or not self._current_source_path:
            return
        chapters = self._book_screen.chapters()
        if not any(c.included for c in chapters):
            QMessageBox.warning(self, tr("main.no_chapters_title"), tr("main.no_chapters_text"))
            return

        settings = self._book_screen.narration_settings()
        output_settings = OutputSettings()

        manifest = self._generate_service.start_session(
            book_title=self._current_document.title,
            source_path=self._current_source_path,
            chapters=chapters,
            settings=settings,
            output_settings=output_settings,
        )
        self._active_manifest = manifest
        self._start_generation_worker(manifest, chapters, settings)

    def _start_generation_worker(self, manifest, chapters, settings) -> None:
        self._generation_screen.reset()
        self._stack.setCurrentWidget(self._generation_screen)
        self._generation_worker = GenerationWorker(self._generate_service, manifest, chapters, settings)
        self._generation_worker.progress.connect(self._generation_screen.update_progress)
        self._generation_worker.succeeded.connect(self._on_generation_succeeded)
        self._generation_worker.cancelled.connect(self._on_generation_cancelled)
        self._generation_worker.failed.connect(self._on_generation_failed)
        self._generation_worker.start()

    def _on_cancel_requested(self) -> None:
        if self._generation_worker is not None:
            self._generation_screen.cancel_button.setEnabled(False)
            self._generation_worker.request_cancel()

    def _on_generation_succeeded(self, result) -> None:
        manifest = self._active_manifest
        book = LibraryBook(
            id=result.book_id,
            canonical_title=manifest.book_title if manifest else "Audiobook",
            chapters=[
                LibraryChapter(
                    chapter_id=c["chapter_id"], title=c["title"], order=c["order"],
                    file_name=c["file_name"], duration_ms=c["duration_ms"],
                )
                for c in result.chapters
            ],
            total_duration_ms=result.total_duration_ms,
            output_format=result.output_format,
            source_path=manifest.source_path if manifest else "",
            created_at=now_iso(),
        )
        self._library_store.add(book)
        self._refresh_library()
        self._stack.setCurrentWidget(self._home_screen)

    def _on_generation_cancelled(self) -> None:
        self._stack.setCurrentWidget(self._book_screen)

    def _on_generation_failed(self, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(tr("main.preview_failed_title"))
        box.setText(tr("main.try_again_details"))
        box.setDetailedText(message)
        box.exec()
        self._stack.setCurrentWidget(self._book_screen)

    # -- settings (§38) --------------------------------------------------

    def _refresh_settings_status(self) -> None:
        hardware = self._model_manager.hardware()
        self._settings_screen.set_hardware(hardware.device_name)
        self._settings_screen.set_cache_size(self._chunk_cache.size_bytes())
        status = self._model_manager.status
        self._settings_screen.set_model_status(status.state, status.message)

    def _on_appearance_changed(self, mode: str) -> None:
        self._app_settings.appearance = mode
        self._settings_store.save(self._app_settings)
        self._apply_theme(mode)

    def _on_clear_cache(self) -> None:
        self._chunk_cache.clear()
        self._refresh_settings_status()

    def _on_open_cache_folder(self) -> None:
        self._chunk_cache.directory.mkdir(parents=True, exist_ok=True)
        self._open_folder(self._chunk_cache.directory)

    # -- library (§ Biblioteca) ---------------------------------------------

    def _refresh_library(self) -> None:
        self._home_screen.set_books(self._library_store.load())

    def _on_book_opened(self, book_id: str) -> None:
        book = self._library_store.get(book_id)
        if book is None:
            return
        audio_dir = self._library_store.audio_dir(book_id)
        self._player_screen.load_book(book, audio_dir)
        self._stack.setCurrentWidget(self._player_screen)

    def _on_book_deleted(self, book_id: str) -> None:
        book = self._library_store.get(book_id)
        title = book.display_title() if book else ""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("main.delete_book_title"))
        box.setText(tr("main.delete_book_text", title=title))
        delete_button = box.addButton(tr("main.delete_confirm"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("main.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() == delete_button:
            self._library_store.delete(book_id)
            self._refresh_library()

    def _on_book_renamed(self, book_id: str, new_title: str) -> None:
        self._library_store.set_custom_title(book_id, new_title)
        self._refresh_library()

    def _on_book_cover_changed(self, book_id: str, source_image_path: str) -> None:
        self._library_store.set_cover(book_id, source_image_path)
        self._refresh_library()

    def _on_playback_position_changed(self, book_id: str, chapter_id: str, position_ms: int) -> None:
        self._library_store.set_playback(
            book_id, PlaybackPosition(chapter_id=chapter_id, position_ms=position_ms, updated_at=now_iso())
        )

    # -- export (§ Biblioteca) -----------------------------------------------

    def _on_export_requested(self, book_id: str, destination_dir: str, output_mode) -> None:
        book = self._library_store.get(book_id)
        if book is None:
            return
        self._player_screen.set_exporting(True)
        self._export_worker = ExportWorker(self._export_service, book, Path(destination_dir), output_mode)
        self._export_worker.succeeded.connect(self._on_export_succeeded)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.start()

    def _on_export_succeeded(self, zip_path: Path) -> None:
        self._player_screen.set_exporting(False)
        box = QMessageBox(self)
        box.setWindowTitle(tr("main.export_succeeded_title"))
        box.setText(tr("main.export_succeeded_text", filename=zip_path.name))
        open_button = box.addButton(tr("main.open_folder"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("main.done"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() == open_button:
            self._open_folder(zip_path.parent)

    def _on_export_failed(self, message: str) -> None:
        self._player_screen.set_exporting(False)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(tr("main.export_failed_title"))
        box.setText(tr("main.try_again_details"))
        box.setDetailedText(message)
        box.exec()

    # -- misc --------------------------------------------------------------

    def _open_folder(self, path: Path) -> None:
        path = Path(path)
        if not path.exists():
            return
        if sys.platform.startswith("win"):
            subprocess.run(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])
