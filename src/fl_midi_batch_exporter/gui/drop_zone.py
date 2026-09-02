"""A small drag-and-drop target for MIDI files."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from .icons import IconLabel


MIDI_SUFFIXES = {".mid", ".midi"}


class DropZone(QFrame):
    """Accept one local MIDI file dropped onto the application window."""

    file_dropped = Signal(Path)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("dropZone")

        self.icon = IconLabel("upload", "#5f6879", 34)
        self.title_label = QLabel("Drop a MIDI file here")
        self.title_label.setObjectName("dropTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label = QLabel("Supports .mid and .midi files")
        self.hint_label.setObjectName("dropHint")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(5)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.title_label)
        layout.addWidget(self.hint_label)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept drags only when they contain a local MIDI file."""
        if self.midi_path_from_event(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Notify listeners of the first valid dropped file."""
        path = self.midi_path_from_event(event)
        if path is None:
            event.ignore()
            return
        self.file_dropped.emit(path)
        event.acceptProposedAction()

    @staticmethod
    def midi_path_from_event(
        event: QDragEnterEvent | QDragMoveEvent | QDropEvent,
    ) -> Path | None:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_file() and path.suffix.lower() in MIDI_SUFFIXES:
                    return path
        return None


class DragOverlay(QFrame):
    """Visual target shown while a valid MIDI file is dragged over the app."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dragOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.icon = IconLabel("upload", "#2f73df", 48, self)
        self.title_label = QLabel("Drop Here")
        self.title_label.setObjectName("dragOverlayTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label = QLabel("Release a .mid or .midi file anywhere in this area")
        self.hint_label.setObjectName("dragOverlayHint")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        layout.addStretch(1)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.title_label)
        layout.addWidget(self.hint_label)
        layout.addStretch(1)
