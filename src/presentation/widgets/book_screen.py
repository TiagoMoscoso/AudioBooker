"""Book screen (§36): chapter review on the left, narration configuration,
preview, and generation controls on the right."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

from domain.chapter import Chapter
from domain.document import DocumentMetadata
from domain.narration import NarrationLanguage, NarrationSettings, NarrationStyle, VoiceReference
from i18n import format_estimate, tr
from presentation.widgets.chapter_list import ChapterListWidget
from presentation.widgets.player_widget import PlayerWidget

_NARRATION_LANGUAGE_KEYS = {
    NarrationLanguage.PORTUGUESE: "narration_language.pt",
    NarrationLanguage.ENGLISH: "narration_language.en",
}
_NARRATION_STYLE_KEYS = {
    NarrationStyle.NATURAL: "narration_style.natural",
    NarrationStyle.CALM: "narration_style.calmo",
    NarrationStyle.EXPRESSIVE: "narration_style.expressivo",
    NarrationStyle.DRAMATIC: "narration_style.dramatico",
}


class BookScreen(QWidget):
    generate_preview_requested = Signal()
    generate_audiobook_requested = Signal()
    chapters_changed = Signal(list)
    settings_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._voice_reference: VoiceReference | None = None
        self._advanced_touched = False
        self._generating_preview = False

        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([420, 340])

    # -- left: chapters ----------------------------------------------------

    def _build_left_panel(self) -> QWidget:
        left = QWidget()
        layout = QVBoxLayout(left)

        self._title_label = QLabel()
        self._title_label.setObjectName("Title")
        self._author_label = QLabel()
        self._author_label.setObjectName("Subtitle")
        self._estimate_label = QLabel()
        self._estimate_label.setObjectName("Subtitle")
        layout.addWidget(self._title_label)
        layout.addWidget(self._author_label)
        layout.addWidget(self._estimate_label)

        chapters_header = QHBoxLayout()
        self._chapters_label = QLabel(tr("book.chapters"))
        self._chapters_label.setObjectName("SectionLabel")
        chapters_header.addWidget(self._chapters_label)
        chapters_header.addStretch(1)
        self.select_all_checkbox = QCheckBox(tr("book.select_all"))
        self.select_all_checkbox.setChecked(True)
        self.select_all_checkbox.toggled.connect(self._on_select_all_toggled)
        chapters_header.addWidget(self.select_all_checkbox)
        layout.addLayout(chapters_header)

        self.chapter_list = ChapterListWidget()
        self.chapter_list.chapters_changed.connect(self.chapters_changed)
        self.chapter_list.chapters_changed.connect(self._update_estimate)
        self.chapter_list.chapters_changed.connect(self._sync_select_all_checkbox)
        layout.addWidget(self.chapter_list, 1)
        return left

    def _on_select_all_toggled(self, checked: bool) -> None:
        self.chapter_list.set_all_included(checked)

    def _sync_select_all_checkbox(self, chapters: list[Chapter]) -> None:
        all_included = all(c.included for c in chapters) if chapters else True
        self.select_all_checkbox.blockSignals(True)
        self.select_all_checkbox.setChecked(all_included)
        self.select_all_checkbox.blockSignals(False)

    # -- right: narration settings ------------------------------------------

    def _build_right_panel(self) -> QWidget:
        right = QWidget()
        layout = QVBoxLayout(right)

        self._narration_label = QLabel(tr("book.narration"))
        self._narration_label.setObjectName("SectionLabel")
        layout.addWidget(self._narration_label)

        form = QFormLayout()
        form.setSpacing(10)

        self.language_combo = QComboBox()
        self._populate_language_combo()
        self.language_combo.currentIndexChanged.connect(lambda _: self.settings_changed.emit())
        self._language_row_label = QLabel(tr("book.language"))
        form.addRow(self._language_row_label, self.language_combo)

        voice_row = QHBoxLayout()
        self._voice_label = QLabel(tr("book.voice_default"))
        self._choose_voice_button = QPushButton(tr("book.choose_sample"))
        self._choose_voice_button.setObjectName("Secondary")
        self._choose_voice_button.clicked.connect(self._choose_voice)
        self._remove_voice_button = QPushButton(tr("book.remove"))
        self._remove_voice_button.setObjectName("Secondary")
        self._remove_voice_button.clicked.connect(self._remove_voice)
        voice_row.addWidget(self._voice_label, 1)
        voice_row.addWidget(self._choose_voice_button)
        voice_row.addWidget(self._remove_voice_button)
        self._narrator_voice_row_label = QLabel(tr("book.narrator_voice"))
        form.addRow(self._narrator_voice_row_label, voice_row)

        self.style_combo = QComboBox()
        self._populate_style_combo()
        self.style_combo.currentIndexChanged.connect(self._on_style_changed)
        self._style_row_label = QLabel(tr("book.style"))
        form.addRow(self._style_row_label, self.style_combo)

        layout.addLayout(form)

        self._advanced_box = QGroupBox(tr("book.advanced"))
        self._advanced_box.setCheckable(True)
        self._advanced_box.setChecked(False)
        advanced_form = QFormLayout(self._advanced_box)
        self.exaggeration_spin = QDoubleSpinBox()
        self.exaggeration_spin.setRange(0.0, 1.0)
        self.exaggeration_spin.setSingleStep(0.05)
        self.exaggeration_spin.setValue(0.5)
        self.exaggeration_spin.valueChanged.connect(self._on_advanced_changed)
        self.cfg_weight_spin = QDoubleSpinBox()
        self.cfg_weight_spin.setRange(0.0, 1.0)
        self.cfg_weight_spin.setSingleStep(0.05)
        self.cfg_weight_spin.setValue(0.5)
        self.cfg_weight_spin.valueChanged.connect(self._on_advanced_changed)
        self._exaggeration_row_label = QLabel(tr("book.exaggeration"))
        advanced_form.addRow(self._exaggeration_row_label, self.exaggeration_spin)
        self._cfg_weight_row_label = QLabel(tr("book.cfg_weight"))
        advanced_form.addRow(self._cfg_weight_row_label, self.cfg_weight_spin)
        layout.addWidget(self._advanced_box)

        self.preview_button = QPushButton(tr("book.generate_preview"))
        self.preview_button.clicked.connect(self.generate_preview_requested)
        layout.addWidget(self.preview_button)

        self.preview_player = PlayerWidget()
        layout.addWidget(self.preview_player)

        self.generate_button = QPushButton(tr("book.generate_audiobook"))
        self.generate_button.clicked.connect(self.generate_audiobook_requested)
        layout.addWidget(self.generate_button)
        layout.addStretch(1)
        return right

    def _populate_language_combo(self) -> None:
        for lang in NarrationLanguage:
            self.language_combo.addItem(tr(_NARRATION_LANGUAGE_KEYS[lang]), lang)

    def _populate_style_combo(self) -> None:
        for style in NarrationStyle:
            self.style_combo.addItem(tr(_NARRATION_STYLE_KEYS[style]), style)

    # -- public API ----------------------------------------------------

    def set_document(self, title: str, author: str | None, metadata: DocumentMetadata) -> None:
        self._title_label.setText(title)
        self._author_label.setText(author or "")

    def set_chapters(self, chapters: list[Chapter]) -> None:
        self.chapter_list.set_chapters(chapters)
        self._sync_select_all_checkbox(chapters)
        self._update_estimate()

    def chapters(self) -> list[Chapter]:
        return self.chapter_list.chapters()

    def set_estimate_text(self, text: str) -> None:
        self._estimate_label.setText(text)

    def set_language(self, language: NarrationLanguage) -> None:
        index = self.language_combo.findData(language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)

    def set_preview_generating(self, generating: bool) -> None:
        self._generating_preview = generating
        self.preview_button.setEnabled(not generating)
        self.preview_button.setText(tr("book.generating_preview") if generating else tr("book.generate_preview"))

    def narration_settings(self) -> NarrationSettings:
        language = self.language_combo.currentData()
        style = self.style_combo.currentData()
        base = NarrationSettings(language=language, voice_reference=self._voice_reference).with_style(style)
        if self._advanced_touched:
            base = NarrationSettings(
                language=base.language,
                style=base.style,
                voice_reference=base.voice_reference,
                exaggeration=self.exaggeration_spin.value(),
                cfg_weight=self.cfg_weight_spin.value(),
            )
        return base

    def retranslate(self) -> None:
        self._chapters_label.setText(tr("book.chapters"))
        self.select_all_checkbox.setText(tr("book.select_all"))
        self._narration_label.setText(tr("book.narration"))
        self._language_row_label.setText(tr("book.language"))
        self._narrator_voice_row_label.setText(tr("book.narrator_voice"))
        self._style_row_label.setText(tr("book.style"))
        self._advanced_box.setTitle(tr("book.advanced"))
        self._exaggeration_row_label.setText(tr("book.exaggeration"))
        self._cfg_weight_row_label.setText(tr("book.cfg_weight"))
        self._choose_voice_button.setText(tr("book.choose_sample"))
        self._remove_voice_button.setText(tr("book.remove"))
        self._voice_label.setText(self._voice_reference.name if self._voice_reference else tr("book.voice_default"))
        self.preview_button.setText(tr("book.generating_preview") if self._generating_preview else tr("book.generate_preview"))
        self.generate_button.setText(tr("book.generate_audiobook"))
        self._retranslate_combo(self.language_combo, self._populate_language_combo)
        self._retranslate_combo(self.style_combo, self._populate_style_combo)
        self._update_estimate()

    def _retranslate_combo(self, combo: QComboBox, populate) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        populate()
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)

    # -- internal --------------------------------------------------------

    def _on_style_changed(self, _index: int) -> None:
        style = self.style_combo.currentData()
        if style is not None and not self._advanced_touched:
            exaggeration, cfg_weight = NarrationSettings.preset_params(style)
            self.exaggeration_spin.blockSignals(True)
            self.cfg_weight_spin.blockSignals(True)
            self.exaggeration_spin.setValue(exaggeration)
            self.cfg_weight_spin.setValue(cfg_weight)
            self.exaggeration_spin.blockSignals(False)
            self.cfg_weight_spin.blockSignals(False)
        self.settings_changed.emit()

    def _on_advanced_changed(self, _value: float) -> None:
        self._advanced_touched = True
        self.settings_changed.emit()

    def _update_estimate(self, *_args) -> None:
        included = [c for c in self.chapter_list.chapters() if c.included]
        word_count = sum(len(c.text.split()) for c in included)
        minutes = word_count / 150
        self._estimate_label.setText(format_estimate(word_count, len(included), minutes))

    def _choose_voice(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("book.dialog_choose_voice_title"), "", tr("book.audio_filter"))
        if path:
            p = Path(path)
            self._voice_reference = VoiceReference(name=p.name, path=p)
            self._voice_label.setText(p.name)
            self.settings_changed.emit()

    def _remove_voice(self) -> None:
        self._voice_reference = None
        self._voice_label.setText(tr("book.voice_default"))
        self.settings_changed.emit()
