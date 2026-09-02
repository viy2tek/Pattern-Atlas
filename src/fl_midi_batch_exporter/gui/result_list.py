"""Widget for displaying exported MIDI stems."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QListWidget

from ..core.models import ExportResult
from .icons import IconLabel


class ResultList(QListWidget):
    """Display one concise row for each exported MIDI file."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultList")
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

    def show_export_result(self, result: ExportResult) -> None:
        """Replace current rows with the files produced by an export."""
        self.clear()
        for stem in result.stems:
            self.addItem(f"{stem.path.name} — {stem.note_count} notes")
        self._update_empty_state()

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
