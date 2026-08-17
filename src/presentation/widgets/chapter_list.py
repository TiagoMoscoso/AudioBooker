"""Chapter review list (§14): view detected chapters, rename, exclude from
generation, reorder (drag & drop), and merge with the next chapter. Not a
full text editor — only the operations the spec calls for."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QInputDialog, QListWidget, QListWidgetItem, QMenu

from domain.chapter import Chapter
from i18n import tr


class ChapterListWidget(QListWidget):
    chapters_changed = Signal(list)  # emits list[Chapter] after any structural change

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.model().rowsMoved.connect(self._on_rows_moved)
        self.itemChanged.connect(self._on_item_changed)
        self._chapters: list[Chapter] = []

    def set_chapters(self, chapters: list[Chapter]) -> None:
        self._chapters = list(chapters)
        self._rebuild()

    def chapters(self) -> list[Chapter]:
        return list(self._chapters)

    def set_all_included(self, included: bool) -> None:
        for chapter in self._chapters:
            chapter.included = included
        self._rebuild()
        self.chapters_changed.emit(self.chapters())

    def _rebuild(self) -> None:
        self.blockSignals(True)
        self.clear()
        for chapter in self._chapters:
            item = QListWidgetItem(self._label_for(chapter))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if chapter.included else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, chapter.id)
            self.addItem(item)
        self.blockSignals(False)

    def _label_for(self, chapter: Chapter) -> str:
        mark = "✓" if chapter.included else "—"
        return f"{mark}  {chapter.title}"

    def _find(self, chapter_id: str) -> Chapter | None:
        return next((c for c in self._chapters if c.id == chapter_id), None)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        chapter_id = item.data(Qt.ItemDataRole.UserRole)
        chapter = self._find(chapter_id)
        if chapter is None:
            return
        included = item.checkState() == Qt.CheckState.Checked
        if included == chapter.included:
            return
        chapter.included = included
        # _rebuild() re-emits itemChanged while repopulating; block it so
        # toggling one chapter doesn't recursively fire this handler.
        self._rebuild()
        self.chapters_changed.emit(self.chapters())

    def _on_rows_moved(self, *_args) -> None:
        new_order: list[Chapter] = []
        for i in range(self.count()):
            chapter_id = self.item(i).data(Qt.ItemDataRole.UserRole)
            chapter = self._find(chapter_id)
            if chapter:
                new_order.append(chapter)
        for i, chapter in enumerate(new_order):
            chapter.order = i
        self._chapters = new_order
        self.chapters_changed.emit(self.chapters())

    def _show_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None:
            return
        chapter_id = item.data(Qt.ItemDataRole.UserRole)
        chapter = self._find(chapter_id)
        if chapter is None:
            return
        row = self.row(item)

        menu = QMenu(self)
        rename_action = menu.addAction(tr("chapters.menu_rename"))
        toggle_action = menu.addAction(
            tr("chapters.menu_exclude") if chapter.included else tr("chapters.menu_include")
        )
        merge_action = menu.addAction(tr("chapters.menu_merge_next")) if row + 1 < len(self._chapters) else None

        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == rename_action:
            self._rename(chapter)
        elif chosen == toggle_action:
            chapter.included = not chapter.included
            self._rebuild()
            self.chapters_changed.emit(self.chapters())
        elif merge_action is not None and chosen == merge_action:
            self._merge_with_next(row)

    def _rename(self, chapter: Chapter) -> None:
        new_title, ok = QInputDialog.getText(
            self, tr("chapters.rename_dialog_title"), tr("chapters.rename_dialog_label"), text=chapter.title
        )
        if ok and new_title.strip():
            chapter.title = new_title.strip()
            self._rebuild()
            self.chapters_changed.emit(self.chapters())

    def _merge_with_next(self, row: int) -> None:
        current = self._chapters[row]
        following = self._chapters[row + 1]
        current.text = f"{current.text}\n\n{following.text}"
        del self._chapters[row + 1]
        for i, chapter in enumerate(self._chapters):
            chapter.order = i
        self._rebuild()
        self.chapters_changed.emit(self.chapters())
