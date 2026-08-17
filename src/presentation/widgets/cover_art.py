"""Generates a simple placeholder poster cover (initial letter over a warm
solid color, picked deterministically from the title) for library books that
don't have a custom cover set — shared by the library grid and the player
screen so both show the same cover for a given book."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

_PLACEHOLDER_COLORS = ["#8A5A44", "#5A6E7A", "#5E7A54", "#7A5A78", "#8A7A44", "#5A5A8A"]


def placeholder_cover(title: str, size: QSize) -> QPixmap:
    pixmap = QPixmap(size)
    color = QColor(_PLACEHOLDER_COLORS[hash(title) % len(_PLACEHOLDER_COLORS)])
    pixmap.fill(color)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Georgia")
    font.setPointSize(max(14, size.width() // 5))
    font.setBold(True)
    painter.setFont(font)
    initial = (title.strip()[:1] or "?").upper()
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, initial)
    painter.end()
    return pixmap
