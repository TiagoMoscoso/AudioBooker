"""Settings screen (§38): appearance, interface language, cache management,
hardware/model status."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMessageBox, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)

from i18n import tr
from infrastructure.tts.model_manager import ModelState


def _format_bytes(n: int) -> str:
    size = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class SettingsScreen(QWidget):
    appearance_changed = Signal(str)
    ui_language_changed = Signal(str)
    clear_cache_requested = Signal()
    open_cache_folder_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cache_size_bytes: int | None = None
        self._model_state: ModelState = ModelState.UNAVAILABLE
        self._model_failure_detail: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(70, 50, 70, 50)
        layout.setSpacing(10)

        self._heading = QLabel(tr("settings.title"))
        self._heading.setObjectName("Title")
        layout.addWidget(self._heading)

        self._appearance_label = self._section_label(tr("settings.appearance"))
        layout.addWidget(self._appearance_label)
        self.system_radio = QRadioButton(tr("settings.system"))
        self.light_radio = QRadioButton(tr("settings.light"))
        self.dark_radio = QRadioButton(tr("settings.dark"))
        self.system_radio.setChecked(True)
        appearance_group = QButtonGroup(self)
        for radio, value in [
            (self.system_radio, "system"), (self.light_radio, "light"), (self.dark_radio, "dark"),
        ]:
            appearance_group.addButton(radio)
            layout.addWidget(radio)
            radio.toggled.connect(lambda checked, v=value: checked and self.appearance_changed.emit(v))

        self._ui_language_label = self._section_label(tr("settings.ui_language"))
        layout.addWidget(self._ui_language_label)
        self.english_radio = QRadioButton(tr("narration_language.en"))
        self.portuguese_radio = QRadioButton(tr("narration_language.pt"))
        self.english_radio.setChecked(True)
        language_group = QButtonGroup(self)
        for radio, value in [(self.english_radio, "en"), (self.portuguese_radio, "pt")]:
            language_group.addButton(radio)
            layout.addWidget(radio)
            radio.toggled.connect(lambda checked, v=value: checked and self.ui_language_changed.emit(v))

        self._storage_label = self._section_label(tr("settings.storage"))
        layout.addWidget(self._storage_label)
        self.cache_label = QLabel(tr("settings.cache_calculating"))
        layout.addWidget(self.cache_label)
        cache_buttons = QHBoxLayout()
        self._open_folder_button = QPushButton(tr("settings.open_folder"))
        self._open_folder_button.setObjectName("Secondary")
        self._open_folder_button.clicked.connect(self.open_cache_folder_requested)
        self._clear_cache_button = QPushButton(tr("settings.clear_cache"))
        self._clear_cache_button.setObjectName("Secondary")
        self._clear_cache_button.clicked.connect(self._confirm_clear_cache)
        cache_buttons.addWidget(self._open_folder_button)
        cache_buttons.addWidget(self._clear_cache_button)
        cache_buttons.addStretch(1)
        layout.addLayout(cache_buttons)

        self._hardware_section_label = self._section_label(tr("settings.hardware"))
        layout.addWidget(self._hardware_section_label)
        self.hardware_label = QLabel(tr("settings.detecting"))
        layout.addWidget(self.hardware_label)

        self._model_section_label = self._section_label(tr("settings.model"))
        layout.addWidget(self._model_section_label)
        self.model_label = QLabel("Chatterbox")
        self.model_status_label = QLabel(tr("model_state.not_loaded"))
        layout.addWidget(self.model_label)
        layout.addWidget(self.model_status_label)

        layout.addStretch(1)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def set_cache_size(self, size_bytes: int) -> None:
        self._cache_size_bytes = size_bytes
        self.cache_label.setText(tr("settings.cache_size", size=_format_bytes(size_bytes)))

    def set_hardware(self, device_name: str) -> None:
        self.hardware_label.setText(device_name)

    def set_model_status(self, state: ModelState, detail: str = "") -> None:
        self._model_state = state
        self._model_failure_detail = detail
        self.model_status_label.setText(self._model_status_text())

    def _model_status_text(self) -> str:
        if self._model_state == ModelState.DOWNLOADING:
            return tr("model_state.downloading")
        if self._model_state == ModelState.LOADING:
            return tr("model.loading")
        if self._model_state == ModelState.READY:
            return tr("model.ready")
        if self._model_state == ModelState.FAILED:
            return tr("model_state.failed", detail=self._model_failure_detail)
        return tr("model_state.not_loaded")

    def set_appearance(self, mode: str) -> None:
        radios = {"system": self.system_radio, "light": self.light_radio, "dark": self.dark_radio}
        radio = radios.get(mode)
        if radio:
            radio.setChecked(True)

    def set_ui_language(self, code: str) -> None:
        radios = {"en": self.english_radio, "pt": self.portuguese_radio}
        radio = radios.get(code)
        if radio:
            radio.setChecked(True)

    def retranslate(self) -> None:
        self._heading.setText(tr("settings.title"))
        self._appearance_label.setText(tr("settings.appearance"))
        self.system_radio.setText(tr("settings.system"))
        self.light_radio.setText(tr("settings.light"))
        self.dark_radio.setText(tr("settings.dark"))
        self._ui_language_label.setText(tr("settings.ui_language"))
        self.english_radio.setText(tr("narration_language.en"))
        self.portuguese_radio.setText(tr("narration_language.pt"))
        self._storage_label.setText(tr("settings.storage"))
        self.cache_label.setText(
            tr("settings.cache_size", size=_format_bytes(self._cache_size_bytes))
            if self._cache_size_bytes is not None
            else tr("settings.cache_calculating")
        )
        self._open_folder_button.setText(tr("settings.open_folder"))
        self._clear_cache_button.setText(tr("settings.clear_cache"))
        self._hardware_section_label.setText(tr("settings.hardware"))
        self._model_section_label.setText(tr("settings.model"))
        self.model_status_label.setText(self._model_status_text())

    def _confirm_clear_cache(self) -> None:
        confirm = QMessageBox.question(
            self, tr("settings.confirm_clear_cache_title"), tr("settings.confirm_clear_cache_text"),
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.clear_cache_requested.emit()
