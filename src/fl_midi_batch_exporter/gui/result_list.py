"""Widget for displaying and dragging exported MIDI stems."""

from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QListWidgetItem,
)

from ..core.models import ExportedStem, ExportResult, MidiBatchResult
from .icons import IconLabel


class ResultList(QListWidget):
    """Display one concise row for each exported MIDI file."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultList")
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setToolTip("Drag exported MIDI files into your DAW")
        self.empty_icon = IconLabel("file", "#c3c9d4", 34, self)
        self.empty_state = QLabel("No files exported yet.", self)
        self.empty_state.setObjectName("mutedText")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_empty_state()

    def resizeEvent(self, event: object) -> None:  # pragma: no cover - Qt geometry
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._update_empty_state()

    def clear(self) -> None:
        super().clear()
        self._update_empty_state()

    def show_export_result(self, result: ExportResult | MidiBatchResult) -> None:
        """Replace current rows with the files produced by an export."""
        self.clear()
        for stem in result.stems:
            self.add_exported_stem(stem)

    def add_exported_stem(self, stem: ExportedStem) -> None:
        """Append one committed stem to the visible export list."""
        item = QListWidgetItem(f"{stem.path.name} — {stem.note_count} notes")
        item.setData(Qt.ItemDataRole.UserRole, str(stem.path))
        item.setToolTip("Drag this MIDI file into your DAW")
        self.addItem(item)
        self._update_empty_state()

    def mimeData(self, items: list[QListWidgetItem]) -> QMimeData:
        """Expose selected exported paths as native file URLs."""
        mime_data = QMimeData()
        urls = []
        for item in items:
            raw_path = item.data(Qt.ItemDataRole.UserRole)
            if not raw_path:
                continue
            urls.append(QUrl.fromLocalFile(str(Path(str(raw_path)))))
        mime_data.setUrls(urls)
        if urls:
            mime_data.setText("\n".join(url.toLocalFile() for url in urls))
        return mime_data

    def _update_empty_state(self) -> None:
        empty = self.count() == 0
        self.empty_icon.setVisible(empty)
        self.empty_state.setVisible(empty)
        if empty:
            self.empty_state.adjustSize()
            group_height = self.empty_icon.height() + 8 + self.empty_state.height()
            top = max(1, (self.height() - group_height) // 2)
            center_x = (self.width() - self.empty_state.width()) // 2
            self.empty_icon.move((self.width() - self.empty_icon.width()) // 2, top)
            self.empty_state.move(max(0, center_x), top + self.empty_icon.height() + 8)
