"""Generation progress screen (§24, §25): real progress driven by
GenerationProgress events (never a fake timer-based bar), plus a safe
Cancel button."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from domain.generation import GenerationProgress
from i18n import tr

_STATE_KEYS = {
    "preparing_text": "generation_state.preparing_text",
    "generating_audio": "generation_state.generating_audio",
    "processing_chapter": "generation_state.processing_chapter",
    "finalizing": "generation_state.finalizing",
    "compacting": "generation_state.compacting",
    "completed": "generation_state.completed",
    "cancelled": "generation_state.cancelled",
    "failed": "generation_state.failed",
}


def _format_elapsed(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class GenerationScreen(QWidget):
    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_progress: GenerationProgress | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(70, 50, 70, 50)
        layout.setSpacing(10)

        self._heading = QLabel(tr("generation.title"))
        self._heading.setObjectName("Title")
        layout.addWidget(self._heading)

        self._chapter_label = QLabel()
        self._chapter_title_label = QLabel()
        self._chapter_title_label.setObjectName("Subtitle")
        self._chunk_label = QLabel()
        self._chunk_label.setObjectName("Subtitle")
        layout.addSpacing(8)
        layout.addWidget(self._chapter_label)
        layout.addWidget(self._chapter_title_label)
        layout.addSpacing(8)
        layout.addWidget(self._chunk_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        layout.addWidget(self._progress_bar)

        self._elapsed_label = QLabel(tr("generation.elapsed", time="00:00:00"))
        self._elapsed_label.setObjectName("Subtitle")
        layout.addWidget(self._elapsed_label)

        self._state_label = QLabel()
        layout.addWidget(self._state_label)

        layout.addSpacing(12)
        self.cancel_button = QPushButton(tr("generation.cancel"))
        self.cancel_button.setObjectName("Secondary")
        self.cancel_button.clicked.connect(self.cancel_requested)
        layout.addWidget(self.cancel_button)
        layout.addStretch(1)

    def update_progress(self, progress: GenerationProgress) -> None:
        self._last_progress = progress
        self._render(progress)

    def _render(self, progress: GenerationProgress) -> None:
        self._chapter_label.setText(
            tr("generation.chapter_progress", index=progress.chapter_index, count=progress.chapter_count)
        )
        self._chapter_title_label.setText(progress.chapter_title)
        self._chunk_label.setText(
            tr("generation.chunk_progress", index=progress.chunk_index, count=progress.chunk_count)
        )
        self._progress_bar.setValue(int(progress.fraction_complete * 100))
        self._elapsed_label.setText(
            tr("generation.elapsed", time=_format_elapsed(progress.elapsed_seconds))
        )
        self._state_label.setText(tr(_STATE_KEYS[progress.state.value]))

    def reset(self) -> None:
        self._last_progress = None
        self._progress_bar.setValue(0)
        self._chapter_label.clear()
        self._chapter_title_label.clear()
        self._chunk_label.clear()
        self._elapsed_label.setText(tr("generation.elapsed", time="00:00:00"))
        self._state_label.clear()
        self.cancel_button.setEnabled(True)

    def retranslate(self) -> None:
        self._heading.setText(tr("generation.title"))
        self.cancel_button.setText(tr("generation.cancel"))
        if self._last_progress is not None:
            self._render(self._last_progress)
        else:
            self._elapsed_label.setText(tr("generation.elapsed", time="00:00:00"))
