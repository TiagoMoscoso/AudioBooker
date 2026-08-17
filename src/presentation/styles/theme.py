"""Visual theme (§34): minimalist, contemporary, literary — ivory/charcoal
palette, a serif for titles and a clean sans-serif for the interface, no
skeuomorphism or "generic AI tool" chrome."""
from __future__ import annotations

_SERIF_STACK = "'Iowan Old Style', 'Georgia', 'Noto Serif', 'DejaVu Serif', serif"
_SANS_STACK = "'Inter', 'Segoe UI', 'Helvetica Neue', 'Noto Sans', sans-serif"

_LIGHT = {
    "background": "#FBF8F2",  # marfim suave
    "surface": "#FFFFFF",  # branco quente
    "text": "#2B2926",  # carvão
    "secondary": "#7A756D",  # cinza quente
    "accent": "#8A5A44",  # terracota sofisticado — cor de destaque única
    "accent_text": "#FFFFFF",
    "border": "#E4DFD5",
}

_DARK = {
    "background": "#1C1B19",
    "surface": "#262421",
    "text": "#EDE8DF",
    "secondary": "#A39C8E",
    "accent": "#C98A66",
    "accent_text": "#1C1B19",
    "border": "#3A3733",
}


def build_stylesheet(mode: str = "light") -> str:
    p = _DARK if mode == "dark" else _LIGHT
    return f"""
    QMainWindow, QWidget {{
        background-color: {p['background']};
        color: {p['text']};
        font-family: {_SANS_STACK};
        font-size: 13px;
    }}
    QLabel {{
        background-color: transparent;
    }}
    QToolBar {{
        background-color: {p['background']};
        border: none;
        border-bottom: 1px solid {p['border']};
        padding: 6px 10px;
        spacing: 8px;
    }}
    QLabel#Title {{
        font-family: {_SERIF_STACK};
        font-size: 26px;
        font-weight: 600;
        color: {p['text']};
    }}
    QLabel#Subtitle {{
        color: {p['secondary']};
        font-size: 13px;
    }}
    QLabel#SectionLabel {{
        font-weight: 600;
        color: {p['secondary']};
        letter-spacing: 1px;
        margin-top: 6px;
    }}
    QFrame#DropZone {{
        background-color: {p['surface']};
        border: 2px dashed {p['border']};
        border-radius: 14px;
    }}
    QFrame#DropZone[dragActive="true"] {{
        border-color: {p['accent']};
    }}
    QFrame#DropZone[dragInvalid="true"] {{
        border-color: #C0392B;
    }}
    QListWidget, QTextEdit {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 10px;
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 7px 6px;
        border-radius: 6px;
    }}
    QListWidget::item:selected {{
        background-color: {p['border']};
        color: {p['text']};
    }}
    QPushButton {{
        background-color: {p['accent']};
        color: {p['accent_text']};
        border: none;
        border-radius: 8px;
        padding: 9px 20px;
        font-weight: 600;
    }}
    QPushButton:disabled {{
        background-color: {p['border']};
        color: {p['secondary']};
    }}
    QPushButton#Secondary {{
        background-color: transparent;
        color: {p['text']};
        border: 1px solid {p['border']};
        font-weight: 500;
        padding: 7px 16px;
    }}
    QPushButton#IconButton {{
        background-color: transparent;
        color: {p['text']};
        border: none;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 15px;
    }}
    QPushButton#IconButton:hover {{
        background-color: {p['border']};
    }}
    QProgressBar {{
        border: 1px solid {p['border']};
        border-radius: 8px;
        background-color: {p['surface']};
        text-align: center;
        height: 20px;
        color: {p['text']};
    }}
    QProgressBar::chunk {{
        background-color: {p['accent']};
        border-radius: 7px;
    }}
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        padding: 6px 8px;
    }}
    QRadioButton, QCheckBox {{
        spacing: 8px;
        padding: 4px 0;
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: {p['border']};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {p['accent']};
        width: 14px;
        height: 14px;
        margin: -6px 0;
        border-radius: 7px;
    }}
    QSplitter::handle {{
        background-color: {p['border']};
    }}
    QScrollArea#LibraryScroll {{
        border: none;
        background: transparent;
    }}
    QLineEdit#SearchBar {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 18px;
        padding: 9px 16px;
        font-size: 13px;
    }}
    QLineEdit#SearchBar:focus {{
        border-color: {p['accent']};
    }}
    QFrame#BookCard {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 10px;
    }}
    QFrame#BookCard:hover {{
        border-color: {p['accent']};
    }}
    QLabel#BookCardCover {{
        background-color: {p['border']};
        border-radius: 8px;
    }}
    QLabel#BookCardTitle {{
        font-family: {_SERIF_STACK};
        font-size: 13px;
        font-weight: 600;
        color: {p['text']};
    }}
    QPushButton#CardMenuButton {{
        background-color: rgba(0, 0, 0, 0.35);
        color: #FFFFFF;
        border: none;
        border-radius: 6px;
        font-size: 14px;
        padding: 2px 8px;
    }}
    QPushButton#CardMenuButton:hover {{
        background-color: rgba(0, 0, 0, 0.55);
    }}
    QLabel#PlayerCover {{
        background-color: {p['border']};
        border-radius: 12px;
    }}
    QListWidget#ChapterList::item:selected {{
        background-color: {p['accent']};
        color: {p['accent_text']};
    }}
    """
