"""Home screen (§35, redesigned as the library): a search bar and a
Netflix-style poster grid of generated audiobooks are the main focus now;
importing a new book (drag & drop or file picker) is demoted to a slim bar
at the bottom (§ Biblioteca)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from domain.library import LibraryBook
from i18n import tr
from infrastructure.parsers.factory import SUPPORTED_EXTENSIONS
from presentation.widgets.cover_art import placeholder_cover

_CARD_WIDTH = 168
_COVER_WIDTH = 152
_COVER_HEIGHT = 228  # 2:3 poster/book-cover aspect ratio
_GRID_SPACING = 20


class DropZone(QFrame):
    """A slim, low-emphasis import bar (drag & drop or file picker) — the
    library grid is the home screen's real focus now."""

    file_dropped = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        self._label = QLabel(tr("home.drop_hint"))
        self._label.setObjectName("Subtitle")
        layout.addWidget(self._label)
        layout.addStretch(1)
        self._choose_button = QPushButton(tr("home.choose_file"))
        self._choose_button.setObjectName("Secondary")
        self._choose_button.clicked.connect(self._choose_file)
        layout.addWidget(self._choose_button)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        path = Path(event.mimeData().urls()[0].toLocalFile())
        valid = path.suffix.lower() in SUPPORTED_EXTENSIONS
        self._set_drag_state(valid)
        if valid:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: ANN001 - Qt event type
        self._set_drag_state(None)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_state(None)
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            self.file_dropped.emit(str(path))

    def _set_drag_state(self, valid: bool | None) -> None:
        self.setProperty("dragActive", valid is True)
        self.setProperty("dragInvalid", valid is False and valid is not None)
        if valid is True:
            self._label.setText(tr("home.drop_hint_active"))
        elif valid is False:
            self._label.setText(tr("home.drop_hint_invalid"))
        else:
            self._label.setText(tr("home.drop_hint"))
        self.style().unpolish(self)
        self.style().polish(self)

    def retranslate(self) -> None:
        self._choose_button.setText(tr("home.choose_file"))
        self._set_drag_state(None)

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("home.choose_file"), "", tr("home.file_filter"))
        if path:
            self.file_dropped.emit(path)


class BookCard(QFrame):
    opened = Signal(str)
    delete_requested = Signal(str)
    rename_requested = Signal(str, str)
    cover_change_requested = Signal(str, str)

    def __init__(self, book: LibraryBook, parent=None) -> None:
        super().__init__(parent)
        self.book = book
        self.setObjectName("BookCard")
        self.setFixedWidth(_CARD_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._cover_label = QLabel()
        self._cover_label.setObjectName("BookCardCover")
        self._cover_label.setFixedSize(_COVER_WIDTH, _COVER_HEIGHT)
        self._cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._cover_label)

        self._title_label = QLabel(book.display_title())
        self._title_label.setObjectName("BookCardTitle")
        self._title_label.setWordWrap(True)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._title_label)

        self._title_edit = QLineEdit(book.display_title())
        self._title_edit.setVisible(False)
        self._title_edit.editingFinished.connect(self._commit_rename)
        self._title_edit.installEventFilter(self)
        layout.addWidget(self._title_edit)

        self._menu_button = QPushButton("⋯", self)
        self._menu_button.setObjectName("CardMenuButton")
        self._menu_button.setFixedSize(26, 22)
        self._menu_button.setVisible(False)
        self._menu_button.clicked.connect(self._show_menu)
        self._menu_button.move(_CARD_WIDTH - 34, 10)

        self._refresh_cover()

    def _refresh_cover(self) -> None:
        size = self._cover_label.size()
        if self.book.cover_path and Path(self.book.cover_path).exists():
            pixmap = QPixmap(self.book.cover_path)
        else:
            pixmap = placeholder_cover(self.book.display_title(), size)
        self._cover_label.setPixmap(
            pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def enterEvent(self, event) -> None:  # noqa: ANN001 - Qt event type
        self._menu_button.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001 - Qt event type
        self._menu_button.setVisible(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001 - Qt event type
        if event.button() == Qt.MouseButton.LeftButton and not self._title_edit.isVisible():
            self.opened.emit(self.book.id)
        super().mousePressEvent(event)

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001 - Qt event types
        if (
            obj is self._title_edit
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self._cancel_rename()
            return True
        return super().eventFilter(obj, event)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        rename_action = menu.addAction(tr("home.menu_rename"))
        cover_action = menu.addAction(tr("home.menu_change_cover"))
        menu.addSeparator()
        delete_action = menu.addAction(tr("home.menu_delete"))
        chosen = menu.exec(self._menu_button.mapToGlobal(self._menu_button.rect().bottomLeft()))
        if chosen == rename_action:
            self._start_rename()
        elif chosen == cover_action:
            self._choose_cover()
        elif chosen == delete_action:
            self.delete_requested.emit(self.book.id)

    def _start_rename(self) -> None:
        self._title_edit.setText(self.book.display_title())
        self._title_label.setVisible(False)
        self._title_edit.setVisible(True)
        self._title_edit.setFocus()
        self._title_edit.selectAll()

    def _cancel_rename(self) -> None:
        self._title_edit.setVisible(False)
        self._title_label.setVisible(True)

    def _commit_rename(self) -> None:
        if not self._title_edit.isVisible():
            return
        new_title = self._title_edit.text().strip()
        self._cancel_rename()
        if new_title and new_title != self.book.display_title():
            self._title_label.setText(new_title)
            self.rename_requested.emit(self.book.id, new_title)

    def _choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("home.dialog_choose_cover_title"), "", tr("home.image_filter"))
        if path:
            self.cover_change_requested.emit(self.book.id, path)


class LibraryGridWidget(QScrollArea):
    book_opened = Signal(str)
    book_deleted = Signal(str)
    book_renamed = Signal(str, str)
    book_cover_changed = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LibraryScroll")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(_GRID_SPACING)
        self._grid.setContentsMargins(4, 4, 4, 12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setWidget(self._container)

        self._empty_label = QLabel(tr("home.empty_library"))
        self._empty_label.setObjectName("Subtitle")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._cards: list[BookCard] = []

    def set_books(self, books: list[LibraryBook]) -> None:
        for card in self._cards:
            self._grid.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        self._empty_label.setParent(None)

        if not books:
            self._grid.addWidget(self._empty_label, 0, 0)
            return

        for book in books:
            card = BookCard(book)
            card.opened.connect(self.book_opened)
            card.delete_requested.connect(self.book_deleted)
            card.rename_requested.connect(self.book_renamed)
            card.cover_change_requested.connect(self.book_cover_changed)
            self._cards.append(card)
        self._relayout()

    def filter_text(self, query: str) -> None:
        needle = query.strip().lower()
        for card in self._cards:
            card.setVisible(needle in card.book.display_title().lower())

    def retranslate(self) -> None:
        self._empty_label.setText(tr("home.empty_library"))

    def resizeEvent(self, event) -> None:  # noqa: ANN001 - Qt event type
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        if not self._cards:
            return
        while self._grid.count():
            self._grid.takeAt(0)
        available = max(self.viewport().width(), _CARD_WIDTH)
        columns = max(1, (available + _GRID_SPACING) // (_CARD_WIDTH + _GRID_SPACING))
        for index, card in enumerate(self._cards):
            row, col = divmod(index, columns)
            self._grid.addWidget(card, row, col)


class HomeScreen(QWidget):
    file_selected = Signal(str)
    book_opened = Signal(str)
    book_deleted = Signal(str)
    book_renamed = Signal(str, str)
    book_cover_changed = Signal(str, str)

    def __init__(self, logo_path: Path, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(56, 28, 56, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)
        if logo_path.exists():
            logo_label = QLabel()
            pixmap = QPixmap(str(logo_path)).scaledToHeight(
                36, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
            header.addWidget(logo_label)
        title = QLabel("Audiobooker")
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        self._search_bar = QLineEdit()
        self._search_bar.setObjectName("SearchBar")
        self._search_bar.setPlaceholderText(tr("home.search_placeholder"))
        self._search_bar.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_bar)

        self._library_grid = LibraryGridWidget()
        self._library_grid.book_opened.connect(self.book_opened)
        self._library_grid.book_deleted.connect(self.book_deleted)
        self._library_grid.book_renamed.connect(self.book_renamed)
        self._library_grid.book_cover_changed.connect(self.book_cover_changed)
        layout.addWidget(self._library_grid, 1)

        self._drop_zone = DropZone()
        self._drop_zone.file_dropped.connect(self.file_selected)
        self._drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._drop_zone)

    def set_books(self, books: list[LibraryBook]) -> None:
        self._library_grid.set_books(books)
        self._search_bar.clear()

    def retranslate(self) -> None:
        self._search_bar.setPlaceholderText(tr("home.search_placeholder"))
        self._library_grid.retranslate()
        self._drop_zone.retranslate()

    def _on_search_changed(self, text: str) -> None:
        self._library_grid.filter_text(text)
