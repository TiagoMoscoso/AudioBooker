"""Preparing screen (§16): shown at app startup while the Chatterbox model
for the last-used language is downloaded/loaded, so the user gets real
feedback ("Baixando modelo..." vs "Carregando modelo...") before reaching
the document import screen — instead of only finding out a multi-GB
download just started when they click "Gerar prévia" mid-session."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from i18n import tr


class PreparingScreen(QWidget):
    def __init__(self, logo_path: Path, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)
        layout.setContentsMargins(100, 60, 100, 60)

        if logo_path.exists():
            logo_label = QLabel()
            pixmap = QPixmap(str(logo_path)).scaledToHeight(
                72, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)

        self._title_label = QLabel(tr("preparing.title"))
        self._title_label.setObjectName("Title")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title_label)

        self._status_label = QLabel(tr("preparing.checking_model"))
        self._status_label.setObjectName("Subtitle")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        self._device_label = QLabel()
        self._device_label.setObjectName("Subtitle")
        self._device_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._device_label)

        # Indeterminate, not a fake percentage: huggingface_hub doesn't
        # expose byte-level download progress without hooking into fragile
        # internals, and §24 forbids faking progress with a timer. This
        # shows real work is happening without claiming a number we don't
        # have.
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedWidth(280)
        layout.addWidget(self._progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_status(self, message: str, device_name: str | None = None) -> None:
        if message:
            self._status_label.setText(message)
        if device_name:
            self._device_label.setText(device_name)

    def retranslate(self) -> None:
        self._title_label.setText(tr("preparing.title"))
        # The live status message (if any) was already resolved into a plain
        # string in the current language at the moment it was set (§ i18n) —
        # only the screen's own static default text is re-applied here.
        self._status_label.setText(tr("preparing.checking_model"))
