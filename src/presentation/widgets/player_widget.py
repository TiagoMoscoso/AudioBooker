"""Simple integrated player (§30): play/pause/seek/duration for the voice
preview and the finished audiobook."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget


def _format_ms(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


class PlayerWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        self._play_button = QPushButton("▶")
        self._play_button.setObjectName("IconButton")
        self._play_button.setFixedWidth(36)
        self._play_button.clicked.connect(self._toggle_play)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.sliderMoved.connect(self._player.setPosition)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("Subtitle")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._play_button)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._time_label)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

        self.setEnabled(False)

    def load(self, path: Path) -> None:
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self.setEnabled(True)

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_position_changed(self, position: int) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(position)
        self._slider.blockSignals(False)
        self._time_label.setText(f"{_format_ms(position)} / {_format_ms(self._player.duration())}")

    def _on_duration_changed(self, duration: int) -> None:
        self._slider.setRange(0, duration)

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self._play_button.setText(
            "⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶"
        )
