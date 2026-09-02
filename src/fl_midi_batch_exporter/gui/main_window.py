"""Single-window workflow for analyzing and exporting MIDI stems."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..application import MidiExportService
from ..core.models import (
    ExportedStem,
    ExportResult,
    MidiExportError,
    MidiProjectAnalysis,
    SplitMode,
)
from .drop_zone import MIDI_SUFFIXES, DragOverlay, DropZone
from .icons import IconLabel, svg_icon
from .result_list import ResultList
from .theme import APP_STYLESHEET

logger = logging.getLogger(__name__)


class _ServiceWorker(QObject):
    """Execute one service operation without blocking the GUI event loop."""

    succeeded = Signal(object)
    progressed = Signal(object)
    failed = Signal(str, object, bool)
    finished = Signal()

    def __init__(
        self,
        operation: Callable[[Callable[[object], None]], object],
        error_message: str,
        clear_analysis_on_failure: bool,
    ) -> None:
        super().__init__()
        self._operation = operation
        self._error_message = error_message
        self._clear_analysis_on_failure = clear_analysis_on_failure

    @Slot()
    def run(self) -> None:
        """Run the requested service operation and report its outcome."""
        try:
            self.succeeded.emit(self._operation(self.progressed.emit))
        except MidiExportError as error:
            self.failed.emit(str(error), error, self._clear_analysis_on_failure)
        except Exception as error:  # noqa: BLE001  # pragma: no cover - GUI boundary
            self.failed.emit(
                self._error_message, error, self._clear_analysis_on_failure
            )
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    """A compact, non-blocking desktop interface for MIDI batch export."""

    worker_failure_received = Signal(str, object, bool)

    def __init__(self, service: MidiExportService) -> None:
        super().__init__()
        self.service = service
        self._input_path: Path | None = None
        self._analysis: MidiProjectAnalysis | None = None
        self._last_output_dir: Path | None = None
        self._thread: QThread | None = None
        self._worker: _ServiceWorker | None = None
        self._is_busy = False

        self.setWindowTitle("Pattern Atlas")
        self.setWindowIcon(svg_icon("waveform", "#2f73df", 24))
        # Keep the vertical layout predictable while allowing the content to
        # breathe when the user widens the window.
        self.setMinimumWidth(760)
        self.setMinimumHeight(700)
        self.setMaximumHeight(700)
        self.resize(900, 700)
        self.setAcceptDrops(True)
        self._build_ui()
        self.worker_failure_received.connect(
            self._worker_failed, Qt.ConnectionType.QueuedConnection
        )
        self._update_controls()

    def _build_ui(self) -> None:
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        outer_layout = QVBoxLayout(central_widget)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(0)
        self.setCentralWidget(central_widget)
        self.setStyleSheet(APP_STYLESHEET)

        content_surface = QFrame()
        content_surface.setObjectName("contentSurface")
        outer_layout.addWidget(content_surface)
        self._content_surface = content_surface
        self.drag_overlay = DragOverlay(content_surface)
        self.drag_overlay.setGeometry(content_surface.rect())
        self.drag_overlay.hide()
        layout = QVBoxLayout(content_surface)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(8)
        self._main_layout = layout

        output_card = QFrame()
        output_card.setObjectName("surface")
        output_card_layout = QVBoxLayout(output_card)
        output_card_layout.setContentsMargins(12, 9, 12, 9)
        output_card_layout.setSpacing(6)
        output_label = QLabel("Output folder")
        output_label.setObjectName("sectionTitle")
        output_card_layout.addWidget(output_label)

        output_layout = QHBoxLayout()
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        path_frame = QFrame()
        path_frame.setObjectName("pathFrame")
        path_layout = QHBoxLayout(path_frame)
        path_layout.setContentsMargins(10, 0, 10, 0)
        path_layout.setSpacing(7)
        path_layout.addWidget(IconLabel("folder", "#5f6b80", 22))
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setObjectName("pathInput")
        self.output_dir_input.setPlaceholderText("Choose where exported MIDI files are saved")
        path_layout.addWidget(self.output_dir_input)
        output_layout.addWidget(path_frame, 1)
        self.output_dir_button = QPushButton("Select folder…")
        self.output_dir_button.setIcon(svg_icon("folder", "#52627a", 20))
        self.output_dir_button.clicked.connect(self._choose_output_directory)
        output_layout.addWidget(self.output_dir_button)
        output_card_layout.addLayout(output_layout)
        output_card.setFixedHeight(102)
        self.output_card = output_card
        layout.addWidget(output_card)

        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)
        self.source_label = QLabel("No MIDI file selected")
        self.source_label.setWordWrap(True)
        self.detected_label = QLabel("Choose a file to detect MIDI sources")
        info_layout.addLayout(self._info_row("info", "Source:", self.source_label))
        info_layout.addLayout(self._info_row("info", "Detected:", self.detected_label))
        info_widget.setFixedHeight(52)
        info_widget.setMinimumWidth(332)
        self._info_widget = info_widget

        self.browse_button = QPushButton("Browse…")
        self.browse_button.setMinimumHeight(40)
        self.browse_button.setIcon(svg_icon("folder", "#52627a", 20))
        self.browse_button.clicked.connect(self._browse_for_file)
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 12, 0)
        input_layout.setSpacing(8)
        input_layout.addWidget(info_widget, 1)
        input_layout.addWidget(self.browse_button)
        layout.addLayout(input_layout)

        self.mode_selector = QComboBox()
        self.mode_selector.addItem("Automatic", SplitMode.AUTO)
        self.mode_selector.addItem("By track", SplitMode.TRACK)
        self.mode_selector.addItem("By MIDI channel", SplitMode.CHANNEL)
        self.mode_selector.setMinimumHeight(30)
        split_layout = QHBoxLayout()
        split_layout.setContentsMargins(8, 0, 8, 0)
        split_layout.setSpacing(8)
        split_label = QLabel("Split mode:")
        split_label.setObjectName("fieldLabel")
        split_layout.addWidget(split_label)
        split_layout.addWidget(self.mode_selector, 1)
        self.mode_selector.currentIndexChanged.connect(self._mode_changed)

        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        self.export_button = QPushButton("Export MIDI Stems")
        self.export_button.setObjectName("primaryButton")
        self.export_button.setMinimumHeight(58)
        self.export_button.clicked.connect(self._export)
        action_layout.addWidget(self.export_button, 1)
        layout.addLayout(action_layout)
        layout.addLayout(split_layout)

        result_card = QFrame()
        result_card.setObjectName("surface")
        result_card_layout = QVBoxLayout(result_card)
        result_card_layout.setContentsMargins(10, 9, 10, 9)
        result_card_layout.setSpacing(4)
        result_title = QLabel("Exported files")
        result_title.setObjectName("sectionTitle")
        result_card_layout.addWidget(result_title)
        self.result_list = ResultList()
        self.result_list.setMinimumHeight(100)
        result_card_layout.addWidget(self.result_list, 1)

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self.open_folder_button = QPushButton("Open output folder")
        self.open_folder_button.setIcon(svg_icon("folder", "#52627a", 20))
        self.open_folder_button.clicked.connect(self._open_output_folder)
        footer_layout.addWidget(self.open_folder_button)
        footer_layout.addStretch()
        self.status_label = QLabel("Ready to export.")
        self.status_label.setObjectName("statusLabel")
        footer_layout.addWidget(self.status_label)
        status_dot = QLabel("●")
        status_dot.setStyleSheet("color: #2f73df; font-size: 16px;")
        footer_layout.addWidget(status_dot)
        result_card_layout.addLayout(footer_layout)
        self.result_card = result_card
        layout.addWidget(result_card, 1)
        central_widget.installEventFilter(self)
        for child in central_widget.findChildren(QWidget):
            child.installEventFilter(self)
        self._update_result_height()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_result_height()
        self.drag_overlay.setGeometry(self._content_surface.rect())

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept valid MIDI drags over any part of the main window."""
        if DropZone.midi_path_from_event(event) is not None:
            self._set_drag_overlay_visible(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Keep the full-window drop target active while dragging."""
        if DropZone.midi_path_from_event(event) is not None:
            self._set_drag_overlay_visible(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Load a valid MIDI file dropped anywhere in the window."""
        path = DropZone.midi_path_from_event(event)
        self._set_drag_overlay_visible(False)
        if path is None:
            event.ignore()
            return
        self.load_file(path)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        """Restore the normal interface when a drag exits the window."""
        self._set_drag_overlay_visible(False)
        event.accept()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        """Show the drop target when a drag enters any child widget."""
        if isinstance(watched, QWidget) and (
            watched is self or self.isAncestorOf(watched)
        ):
            event_type = event.type()
            if event_type in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if DropZone.midi_path_from_event(event):  # type: ignore[arg-type]
                    self._set_drag_overlay_visible(True)
            elif event_type == QEvent.Type.Drop:
                self._set_drag_overlay_visible(False)
        return super().eventFilter(watched, event)

    def _set_drag_overlay_visible(self, visible: bool) -> None:
        """Toggle and size the full-surface drag target."""
        if visible:
            self.drag_overlay.setGeometry(self._content_surface.rect())
            self.drag_overlay.raise_()
        self.drag_overlay.setVisible(visible)

    def _update_result_height(self) -> None:
        """Keep the result panel proportional to the reference viewport."""
        if hasattr(self, "result_card"):
            scale = max(0.4, min(1.0, self.height() / 1041))
            self._main_layout.setSpacing(max(4, int(8 * scale)))
            self.browse_button.setMinimumHeight(max(38, int(52 * scale)))
            self._info_widget.setFixedHeight(max(40, int(52 * scale)))
            self.output_card.setFixedHeight(max(86, int(102 * scale)))
            self.export_button.setMinimumHeight(max(42, int(58 * scale)))
            self.result_card.setMinimumHeight(max(250, int(self.height() * 0.38)))
            self._main_layout.invalidate()

    def _info_row(self, icon: str, title: str, value: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        row.addWidget(IconLabel(icon, "#4e5c73", 18))
        label = QLabel(title)
        label.setObjectName("fieldLabel")
        label.setFixedWidth(84)
        row.addWidget(label)
        value.setObjectName("mutedText")
        row.addWidget(value, 1)
        return row

    @Slot()
    def _browse_for_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose MIDI file",
            str(self._input_path.parent if self._input_path else Path.home()),
            "MIDI files (*.mid *.midi)",
        )
        if filename:
            self.load_file(Path(filename))

    @Slot(Path)
    def load_file(self, path: Path) -> None:
        """Start analysis for a selected MIDI file."""
        if not self._is_valid_midi_file(path):
            self._show_message(
                "Choose a MIDI file",
                "Please select a readable .mid or .midi file.",
                QMessageBox.Icon.Warning,
            )
            return
        if self._is_busy:
            return

        self._input_path = path
        self._analysis = None
        self._last_output_dir = None
        self.source_label.setText(path.name)
        self.detected_label.setText("Analyzing MIDI sources…")
        self.status_label.setText("Analyzing MIDI…")
        self.output_dir_input.setText(str(path.with_name(f"{path.stem} - MIDI Stems")))
        self.result_list.clear()
        self._update_controls()

        mode = self._selected_mode()
        self._start_worker(
            lambda _progress: self.service.analyze(path, mode),
            self._analysis_loaded,
            "The MIDI file could not be analyzed. Please try another file.",
            clear_analysis_on_failure=True,
        )

    @Slot(int)
    def _mode_changed(self, _: int) -> None:
        if self._input_path is not None and not self._is_busy:
            self.load_file(self._input_path)

    @Slot()
    def _choose_output_directory(self) -> None:
        start_dir = self.output_dir_input.text() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Choose output folder", start_dir)
        if directory:
            self.output_dir_input.setText(directory)

    @Slot()
    def _export(self) -> None:
        if self._input_path is None or self._analysis is None:
            return
        output_text = self.output_dir_input.text().strip()
        if not output_text:
            self._show_message(
                "Choose an output folder",
                "Choose a folder for the exported MIDI files.",
                QMessageBox.Icon.Warning,
            )
            return

        input_path = self._input_path
        output_dir = Path(output_text)
        mode = self._selected_mode()
        self.status_label.setText("Exporting MIDI stems…")
        self.result_list.clear()
        self._start_worker(
            lambda progress: self.service.export(
                input_path, output_dir, mode, on_stem=progress
            ),
            self._export_finished,
            "The MIDI stems could not be exported. Please try again.",
            clear_analysis_on_failure=False,
            on_progress=self._export_progress,
        )

    def _analysis_loaded(self, result: object) -> None:
        analysis = result
        if not isinstance(analysis, MidiProjectAnalysis):
            raise TypeError("Analysis worker returned an unexpected result.")
        self._analysis = analysis
        self.detected_label.setText(f"{len(analysis.sources)} MIDI sources")
        self.status_label.setText("Ready to export.")
        self._update_controls()

    def _export_finished(self, result: object) -> None:
        export_result = result
        if not isinstance(export_result, ExportResult):
            raise TypeError("Export worker returned an unexpected result.")
        self.result_list.show_export_result(export_result)
        self._last_output_dir = Path(self.output_dir_input.text())
        self.status_label.setText("Export complete.")
        self.open_folder_button.setEnabled(bool(export_result.stems))
        self._show_message(
            "Export complete",
            f"Exported {len(export_result.stems)} MIDI files.",
            QMessageBox.Icon.Information,
        )

    def _export_progress(self, stem: object) -> None:
        """Show each stem immediately after its atomic commit."""
        if not isinstance(stem, ExportedStem):
            raise TypeError("Export worker reported an unexpected stem.")
        self.result_list.add_exported_stem(stem)
        self.status_label.setText(f"Exporting MIDI stems… ({self.result_list.count()})")

    def _start_worker(
        self,
        operation: Callable[[Callable[[object], None]], object],
        on_success: Callable[[object], None],
        fallback_error: str,
        clear_analysis_on_failure: bool,
        on_progress: Callable[[object], None] | None = None,
    ) -> None:
        self._is_busy = True
        self._update_controls()

        thread = QThread(self)
        worker = _ServiceWorker(operation, fallback_error, clear_analysis_on_failure)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(on_success)
        if on_progress is not None:
            worker.progressed.connect(on_progress, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(
            self.worker_failure_received, Qt.ConnectionType.QueuedConnection
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._worker_finished(thread))

        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(str, object, bool)
    def _worker_failed(
        self, message: str, error: object, clear_analysis_on_failure: bool
    ) -> None:
        if isinstance(error, BaseException):
            logger.error(
                "MIDI GUI operation failed",
                exc_info=(type(error), error, error.__traceback__),
            )
        else:  # pragma: no cover - signal contract guard
            logger.error("MIDI GUI operation failed: %s", error)
        self.result_list.clear()
        if clear_analysis_on_failure:
            self.detected_label.setText("No MIDI sources detected")
            self._analysis = None
        self.status_label.setText("Could not finish operation.")
        self._show_message("Could not finish operation", message, QMessageBox.Icon.Critical)

    def _worker_finished(self, thread: QThread) -> None:
        if self._thread is thread:
            self._thread = None
            self._worker = None
            self._is_busy = False
            self._update_controls()

    def _update_controls(self) -> None:
        can_select_input = not self._is_busy
        self.browse_button.setEnabled(can_select_input)
        self.mode_selector.setEnabled(can_select_input)
        self.export_button.setEnabled(self._analysis is not None and not self._is_busy)
        self.open_folder_button.setEnabled(
            self._last_output_dir is not None and not self._is_busy
        )

    def _selected_mode(self) -> SplitMode:
        mode = self.mode_selector.currentData()
        return mode if isinstance(mode, SplitMode) else SplitMode.AUTO

    @staticmethod
    def _is_valid_midi_file(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in MIDI_SUFFIXES

    def _open_output_folder(self) -> None:
        if self._last_output_dir is None:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output_dir))):
            self._show_message(
                "Could not open folder",
                "Open the output folder manually from your file browser.",
                QMessageBox.Icon.Warning,
            )

    def _show_message(
        self, title: str, text: str, icon: QMessageBox.Icon
    ) -> None:
        message_box = QMessageBox(self)
        message_box.setIcon(icon)
        message_box.setWindowTitle(title)
        message_box.setText(text)
        message_box.exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Wait for an active worker before Qt destroys its thread object."""
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        event.accept()
