"""Player screen (§ Biblioteca — evolves §30): plays a library book chapter
by chapter, with skip/pause/play, speed and volume control, inline
title/cover editing, and on-demand ZIP export. Playback position is saved so
re-opening the same book resumes where the user left off, instead of
restarting from the beginning."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from domain.generation import OutputMode
from domain.library import LibraryBook, LibraryChapter
from i18n import tr
from presentation.widgets.cover_art import placeholder_cover

_SAVE_INTERVAL_MS = 5000
_SPEED_OPTIONS = (0.75, 1.0, 1.25, 1.5, 1.75, 2.0)


def _format_ms(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _format_duration(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h{minutes:02d}" if hours else f"{minutes}min"


class PlayerScreen(QWidget):
    rename_requested = Signal(str, str)  # book_id, new_title
    cover_change_requested = Signal(str, str)  # book_id, source_image_path
    playback_position_changed = Signal(str, str, int)  # book_id, chapter_id, position_ms
    export_requested = Signal(str, str, object)  # book_id, destination_dir, OutputMode

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._book: LibraryBook | None = None
        self._audio_dir: Path | None = None
        self._current_index = -1
        self._exporting = False

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

        self._save_timer = QTimer(self)
        self._save_timer.setInterval(_SAVE_INTERVAL_MS)
        self._save_timer.timeout.connect(self._save_position)

        root = QHBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(32)
        root.addWidget(self._build_header_panel(), 0)
        root.addWidget(self._build_chapters_panel(), 1)

    # -- UI construction -----------------------------------------------

    def _build_header_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(240)
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)

        self._cover_label = QLabel()
        self._cover_label.setObjectName("PlayerCover")
        self._cover_label.setFixedSize(220, 330)
        self._cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._cover_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        title_row = QHBoxLayout()
        self._title_label = QLabel()
        self._title_label.setObjectName("Title")
        self._title_label.setWordWrap(True)
        title_row.addWidget(self._title_label, 1)
        edit_title_button = QPushButton("✎")
        edit_title_button.setObjectName("IconButton")
        edit_title_button.setFixedWidth(30)
        edit_title_button.clicked.connect(self._start_rename)
        title_row.addWidget(edit_title_button)
        layout.addLayout(title_row)

        self._title_edit = QLineEdit()
        self._title_edit.setVisible(False)
        self._title_edit.editingFinished.connect(self._commit_rename)
        layout.addWidget(self._title_edit)

        self._cover_button = QPushButton(tr("home.menu_change_cover"))
        self._cover_button.setObjectName("Secondary")
        self._cover_button.clicked.connect(self._choose_cover)
        layout.addWidget(self._cover_button)

        layout.addStretch(1)

        self._export_section_label = QLabel(tr("player.export_section"))
        self._export_section_label.setObjectName("SectionLabel")
        layout.addWidget(self._export_section_label)

        self._export_mode_combo = QComboBox()
        self._populate_export_mode_combo()
        layout.addWidget(self._export_mode_combo)

        self._export_button = QPushButton(tr("player.export"))
        self._export_button.clicked.connect(self._on_export_clicked)
        layout.addWidget(self._export_button)

        return panel

    def _populate_export_mode_combo(self) -> None:
        self._export_mode_combo.addItem(tr("player.mode_separate"), OutputMode.SEPARATE_CHAPTERS)
        self._export_mode_combo.addItem(tr("player.mode_single"), OutputMode.SINGLE_FILE)

    def _build_chapters_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)

        self._chapters_label = QLabel(tr("book.chapters"))
        self._chapters_label.setObjectName("SectionLabel")
        layout.addWidget(self._chapters_label)

        self._chapter_list = QListWidget()
        self._chapter_list.setObjectName("ChapterList")
        self._chapter_list.itemActivated.connect(self._on_chapter_activated)
        layout.addWidget(self._chapter_list, 1)

        transport = QHBoxLayout()
        self._prev_button = QPushButton("⏮")
        self._prev_button.setObjectName("IconButton")
        self._prev_button.clicked.connect(self._play_previous)
        self._play_button = QPushButton("▶")
        self._play_button.setObjectName("IconButton")
        self._play_button.clicked.connect(self._toggle_play)
        self._next_button = QPushButton("⏭")
        self._next_button.setObjectName("IconButton")
        self._next_button.clicked.connect(self._play_next)
        transport.addWidget(self._prev_button)
        transport.addWidget(self._play_button)
        transport.addWidget(self._next_button)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.sliderMoved.connect(self._player.setPosition)
        transport.addWidget(self._seek_slider, 1)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("Subtitle")
        transport.addWidget(self._time_label)
        layout.addLayout(transport)

        controls_row = QHBoxLayout()
        self._speed_label = QLabel(tr("player.speed"))
        self._speed_label.setObjectName("Subtitle")
        controls_row.addWidget(self._speed_label)
        self._speed_combo = QComboBox()
        for rate in _SPEED_OPTIONS:
            self._speed_combo.addItem(f"{rate:g}x", rate)
        self._speed_combo.setCurrentIndex(_SPEED_OPTIONS.index(1.0))
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        controls_row.addWidget(self._speed_combo)

        controls_row.addStretch(1)

        self._volume_label = QLabel(tr("player.volume"))
        self._volume_label.setObjectName("Subtitle")
        controls_row.addWidget(self._volume_label)
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(100)
        self._volume_slider.setFixedWidth(120)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        controls_row.addWidget(self._volume_slider)
        layout.addLayout(controls_row)

        return panel

    # -- public API ----------------------------------------------------

    def load_book(self, book: LibraryBook, audio_dir: Path) -> None:
        self._save_position()  # flush any pending position for the book we're leaving
        self._book = book
        self._audio_dir = audio_dir
        self._current_index = -1

        self._title_label.setText(book.display_title())
        self._refresh_cover()
        self._populate_chapter_list()

        self._player.stop()

        target_index = 0
        start_position_ms = 0
        if book.playback.chapter_id:
            for idx, chapter in enumerate(self._ordered_chapters()):
                if chapter.chapter_id == book.playback.chapter_id:
                    target_index = idx
                    start_position_ms = book.playback.position_ms
                    break
        self._load_chapter(target_index, start_position_ms=start_position_ms)

    def _populate_chapter_list(self) -> None:
        self._chapter_list.blockSignals(True)
        current_row = self._chapter_list.currentRow()
        self._chapter_list.clear()
        for chapter in self._ordered_chapters():
            item = QListWidgetItem(f"{chapter.order:02d}. {chapter.title}  ·  {_format_duration(chapter.duration_ms)}")
            item.setData(Qt.ItemDataRole.UserRole, chapter.chapter_id)
            self._chapter_list.addItem(item)
        if current_row >= 0:
            self._chapter_list.setCurrentRow(current_row)
        self._chapter_list.blockSignals(False)

    def set_exporting(self, exporting: bool) -> None:
        self._exporting = exporting
        self._export_button.setEnabled(not exporting)
        self._export_button.setText(tr("player.exporting") if exporting else tr("player.export"))

    def showEvent(self, event) -> None:  # noqa: ANN001 - Qt event type
        self._save_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: ANN001 - Qt event type
        self._save_timer.stop()
        self._save_position()
        self._player.pause()
        super().hideEvent(event)

    def retranslate(self) -> None:
        self._cover_button.setText(tr("home.menu_change_cover"))
        self._export_section_label.setText(tr("player.export_section"))
        self._retranslate_export_mode_combo()
        self.set_exporting(self._exporting)
        self._chapters_label.setText(tr("book.chapters"))
        self._speed_label.setText(tr("player.speed"))
        self._volume_label.setText(tr("player.volume"))
        if self._book is not None:
            self._populate_chapter_list()

    def _retranslate_export_mode_combo(self) -> None:
        current = self._export_mode_combo.currentData()
        self._export_mode_combo.blockSignals(True)
        self._export_mode_combo.clear()
        self._populate_export_mode_combo()
        index = self._export_mode_combo.findData(current)
        if index >= 0:
            self._export_mode_combo.setCurrentIndex(index)
        self._export_mode_combo.blockSignals(False)

    # -- chapters / transport --------------------------------------------

    def _ordered_chapters(self) -> list[LibraryChapter]:
        if self._book is None:
            return []
        return sorted(self._book.chapters, key=lambda c: c.order)

    def _load_chapter(self, index: int, start_position_ms: int = 0, autoplay: bool = False) -> None:
        chapters = self._ordered_chapters()
        if not (0 <= index < len(chapters)) or self._audio_dir is None:
            return
        self._current_index = index
        chapter = chapters[index]

        self._chapter_list.blockSignals(True)
        self._chapter_list.setCurrentRow(index)
        self._chapter_list.blockSignals(False)

        self._player.setSource(QUrl.fromLocalFile(str(self._audio_dir / chapter.file_name)))
        if start_position_ms:
            self._player.setPosition(start_position_ms)
        if autoplay:
            self._player.play()

    def _on_chapter_activated(self, item: QListWidgetItem) -> None:
        was_playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self._load_chapter(self._chapter_list.row(item), autoplay=was_playing)
        self._save_position()

    def _play_previous(self) -> None:
        if self._current_index > 0:
            was_playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            self._load_chapter(self._current_index - 1, autoplay=was_playing)
            self._save_position()

    def _play_next(self) -> None:
        if self._current_index < len(self._ordered_chapters()) - 1:
            was_playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            self._load_chapter(self._current_index + 1, autoplay=was_playing)
            self._save_position()

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._current_index < len(self._ordered_chapters()) - 1:
                self._load_chapter(self._current_index + 1, autoplay=True)
            else:
                self._save_position()

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self._play_button.setText("⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶")
        if state == QMediaPlayer.PlaybackState.PausedState:
            self._save_position()

    def _on_position_changed(self, position: int) -> None:
        self._seek_slider.blockSignals(True)
        self._seek_slider.setValue(position)
        self._seek_slider.blockSignals(False)
        self._time_label.setText(f"{_format_ms(position)} / {_format_ms(self._player.duration())}")

    def _on_duration_changed(self, duration: int) -> None:
        self._seek_slider.setRange(0, duration)

    def _on_speed_changed(self, index: int) -> None:
        rate = self._speed_combo.itemData(index)
        if rate:
            self._player.setPlaybackRate(rate)

    def _on_volume_changed(self, value: int) -> None:
        self._audio_output.setVolume(value / 100)

    def _save_position(self) -> None:
        chapters = self._ordered_chapters()
        if self._book is None or not (0 <= self._current_index < len(chapters)):
            return
        chapter = chapters[self._current_index]
        self.playback_position_changed.emit(self._book.id, chapter.chapter_id, self._player.position())

    # -- title / cover editing -------------------------------------------

    def _refresh_cover(self) -> None:
        size = self._cover_label.size()
        if self._book and self._book.cover_path and Path(self._book.cover_path).exists():
            pixmap = QPixmap(self._book.cover_path)
        else:
            pixmap = placeholder_cover(self._book.display_title() if self._book else "?", size)
        self._cover_label.setPixmap(
            pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _start_rename(self) -> None:
        if self._book is None:
            return
        self._title_edit.setText(self._book.display_title())
        self._title_label.setVisible(False)
        self._title_edit.setVisible(True)
        self._title_edit.setFocus()
        self._title_edit.selectAll()

    def _commit_rename(self) -> None:
        if self._book is None or not self._title_edit.isVisible():
            return
        new_title = self._title_edit.text().strip()
        self._title_edit.setVisible(False)
        self._title_label.setVisible(True)
        if new_title and new_title != self._book.display_title():
            self._title_label.setText(new_title)
            self.rename_requested.emit(self._book.id, new_title)

    def _choose_cover(self) -> None:
        if self._book is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("home.dialog_choose_cover_title"), "", tr("home.image_filter"))
        if path:
            self.cover_change_requested.emit(self._book.id, path)

    # -- export ----------------------------------------------------------

    def _on_export_clicked(self) -> None:
        if self._book is None:
            return
        destination = QFileDialog.getExistingDirectory(self, tr("player.dialog_choose_folder_title"))
        if not destination:
            return
        output_mode = self._export_mode_combo.currentData()
        self.export_requested.emit(self._book.id, destination, output_mode)
