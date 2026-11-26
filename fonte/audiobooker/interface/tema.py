"""Aparência única das ferramentas do PC: tema escuro, destaque ciano, Segoe UI e Segoe Fluent Icons."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

FUNDO = "#1C1C1F"
SUPERFICIE = "#28282D"
SUPERFICIE_2 = "#323238"
BORDA = "#3A3A42"
TEXTO = "#ECECF1"
FRACO = "#A0A0AA"
DESTAQUE = "#4DD0E1"
AVISO = "#FBBF24"
ERRO = "#F85252"
OK = "#5BD58A"

FONTE = "Segoe UI"
FONTE_ICONES = "Segoe Fluent Icons"

# glifos do Segoe Fluent Icons
GLIFOS = {
    "frases": "",      # microfone
    "livros": "",      # biblioteca
    "vozes": "",       # pessoa
    "dicionario": "",  # dicionário
    "config": "",      # engrenagem
    "tocar": "",
    "pausar": "",
    "parar": "",
    "salvar": "",
    "apagar": "",
    "pasta": "",
    "mais": "",
    "menos": "",
    "cima": "",
    "baixo": "",
    "copiar": "",
    "importar": "",
    "exportar": "",
    "estrela": "",
    "estrela_cheia": "",
    "gerar": "",
    "abrir": "",
    "ok": "",
    "aviso": "",
    "atualizar": "",
    "cancelar": "",
}


def glifo(nome: str) -> str:
    return GLIFOS.get(nome, "")


def icone(nome: str, cor: str = TEXTO, tamanho: int = 20) -> QIcon:
    pm = QPixmap(tamanho * 2, tamanho * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    f = QFont(FONTE_ICONES)
    f.setPixelSize(tamanho * 2 - 6)
    p.setFont(f)
    p.setPen(QColor(cor))
    p.drawText(QRectF(0, 0, tamanho * 2, tamanho * 2), Qt.AlignmentFlag.AlignCenter, glifo(nome))
    p.end()
    return QIcon(pm)


QSS = f"""
* {{ font-family: "{FONTE}"; font-size: 10pt; color: {TEXTO}; }}
QMainWindow, QWidget#raiz, QDialog {{ background: {FUNDO}; }}
QWidget {{ background: transparent; }}
QToolTip {{ background: {SUPERFICIE_2}; color: {TEXTO}; border: 1px solid {BORDA}; padding: 4px 6px; }}

QLabel#titulo {{ font-size: 18pt; font-weight: 600; }}
QLabel#subtitulo {{ color: {FRACO}; }}
QLabel#secao {{ font-size: 11pt; font-weight: 600; }}
QLabel#fraco {{ color: {FRACO}; }}
QLabel#aviso {{ color: {AVISO}; }}
QLabel#erro {{ color: {ERRO}; }}
QLabel#ok {{ color: {OK}; }}

QFrame#cartao {{ background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 10px; }}
QFrame#lateral {{ background: {SUPERFICIE}; border-right: 1px solid {BORDA}; }}
QFrame#linha {{ background: {BORDA}; max-height: 1px; min-height: 1px; border: none; }}

QPushButton {{ background: {SUPERFICIE_2}; border: 1px solid {BORDA}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {DESTAQUE}; }}
QPushButton:pressed {{ background: {BORDA}; }}
QPushButton:disabled {{ color: {FRACO}; border-color: {SUPERFICIE_2}; background: {SUPERFICIE}; }}
QPushButton[variante="primario"] {{ background: {DESTAQUE}; color: {FUNDO}; border-color: {DESTAQUE}; font-weight: 600; }}
QPushButton[variante="primario"]:hover {{ background: #6FDCE9; }}
QPushButton[variante="primario"]:disabled {{ background: #2F5A60; color: {FRACO}; border-color: #2F5A60; }}
QPushButton[variante="perigo"]:hover {{ border-color: {ERRO}; color: {ERRO}; }}
QPushButton[variante="icone"] {{ padding: 6px 8px; min-width: 18px; }}
QPushButton[variante="nav"] {{ background: transparent; border: none; border-left: 3px solid transparent; border-radius: 0;
    text-align: left; padding: 11px 16px; color: {FRACO}; }}
QPushButton[variante="nav"]:hover {{ background: {SUPERFICIE_2}; color: {TEXTO}; }}
QPushButton[variante="nav"]:checked {{ background: {SUPERFICIE_2}; border-left: 3px solid {DESTAQUE}; color: {TEXTO}; font-weight: 600; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {FUNDO}; border: 1px solid {BORDA}; border-radius: 6px; padding: 6px 8px; selection-background-color: {DESTAQUE}; selection-color: {FUNDO}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {DESTAQUE}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SUPERFICIE}; border: 1px solid {BORDA}; selection-background-color: {SUPERFICIE_2}; selection-color: {DESTAQUE}; outline: none; }}

QListWidget, QTableWidget, QTreeWidget {{ background: {FUNDO}; border: 1px solid {BORDA}; border-radius: 8px; outline: none; alternate-background-color: {SUPERFICIE}; gridline-color: {BORDA}; }}
QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {SUPERFICIE}; }}
QListWidget::item:selected {{ background: {SUPERFICIE_2}; color: {DESTAQUE}; }}
QTableWidget::item {{ padding: 4px 8px; }}
QTableWidget::item:selected {{ background: {SUPERFICIE_2}; color: {TEXTO}; }}
QHeaderView::section {{ background: {SUPERFICIE}; color: {FRACO}; border: none; border-bottom: 1px solid {BORDA}; padding: 6px 8px; font-weight: 600; }}
QTableCornerButton::section {{ background: {SUPERFICIE}; border: none; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDA}; border-radius: 4px; background: {FUNDO}; }}
QCheckBox::indicator:checked {{ background: {DESTAQUE}; border-color: {DESTAQUE}; image: none; }}
QCheckBox::indicator:hover {{ border-color: {DESTAQUE}; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDA}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {DESTAQUE}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXTO}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {DESTAQUE}; }}

QProgressBar {{ background: {FUNDO}; border: 1px solid {BORDA}; border-radius: 6px; text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {DESTAQUE}; border-radius: 5px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDA}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {FRACO}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDA}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QTabWidget::pane {{ border: 1px solid {BORDA}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {FRACO}; padding: 8px 16px; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXTO}; border-bottom: 2px solid {DESTAQUE}; }}
QTabBar::tab:hover {{ color: {TEXTO}; }}

QStatusBar {{ background: {SUPERFICIE}; border-top: 1px solid {BORDA}; color: {FRACO}; }}
QStatusBar QLabel {{ color: {FRACO}; }}
QMenu {{ background: {SUPERFICIE}; border: 1px solid {BORDA}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {SUPERFICIE_2}; }}
QSplitter::handle {{ background: {BORDA}; }}
QGroupBox {{ border: 1px solid {BORDA}; border-radius: 8px; margin-top: 12px; padding: 12px 10px 8px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 6px; color: {FRACO}; }}
"""


def aplicar(app) -> None:
    app.setStyle("Fusion")
    fonte = QFont(FONTE, 10)
    app.setFont(fonte)
    app.setStyleSheet(QSS)
    _ = QFontDatabase  # fontes do sistema já bastam
