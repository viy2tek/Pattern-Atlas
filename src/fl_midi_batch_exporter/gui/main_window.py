"""Single-window workflow for analyzing and exporting MIDI stems."""

from __future__ import annotations

import logging
import os
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
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..application import MidiExportService
from ..core.models import (
    ExportedStem,
    ExportResult,
    MidiBatchResult,
    MidiExportError,
    MidiProjectAnalysis,
    MidiSource,
    MidiSourceSelection,
    SplitMode,
)
from .drop_zone import MIDI_SUFFIXES, DragOverlay, DropZone
from .icons import IconLabel, svg_icon
from .result_list import ResultList
from .theme import APP_STYLESHEET

logger = logging.getLogger(__name__)
_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


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
        self._input_paths: tuple[Path, ...] = ()
        self._analysis: MidiProjectAnalysis | None = None
        self._analyses: tuple[tuple[Path, MidiProjectAnalysis], ...] = ()
        self._last_output_dir: Path | None = None
        self._thread: QThread | None = None
        self._worker: _ServiceWorker | None = None
        self._is_busy = False
        self._source_preview_expanded = False

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

        source_card = QFrame()
        source_card.setObjectName("surface")
        source_card_layout = QVBoxLayout(source_card)
        source_card_layout.setContentsMargins(10, 7, 10, 7)
        source_card_layout.setSpacing(4)
        source_header = QHBoxLayout()
        source_header.setContentsMargins(0, 0, 0, 0)
        source_title = QLabel("MIDI sources")
        source_title.setObjectName("sectionTitle")
        source_header.addWidget(source_title)
        source_header.addStretch()
        self.source_expand_button = QPushButton("Expand")
        self.source_expand_button.setObjectName("compactButton")
        self.source_expand_button.setMinimumHeight(28)
        self.source_expand_button.clicked.connect(self._toggle_source_preview)
        source_header.addWidget(self.source_expand_button)
        source_card_layout.addLayout(source_header)
        self.source_table = QTableWidget(0, 7)
        self.source_table.setObjectName("sourceTable")
        self.source_table.setHorizontalHeaderLabels(
            ["Use", "File", "Source", "Track", "Channel", "Notes", "Range"]
        )
        self.source_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.source_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.source_table.setAlternatingRowColors(True)
        self.source_table.verticalHeader().setVisible(False)
        self.source_table.horizontalHeader().setStretchLastSection(True)
        self.source_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.source_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.source_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        for column in (3, 4, 5):
            self.source_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.source_table.setMinimumHeight(128)
        self.source_table.setMaximumHeight(174)
        self.source_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.source_table.itemChanged.connect(self._source_item_changed)
        source_card_layout.addWidget(self.source_table)
        self.source_card = source_card
        layout.addWidget(source_card)

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
        self._action_widget = QWidget()
        self._action_widget.setLayout(action_layout)
        layout.addWidget(self._action_widget)
        self._split_widget = QWidget()
        self._split_widget.setLayout(split_layout)
        layout.addWidget(self._split_widget)

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
        if DropZone.input_paths_from_event(event):
            self._set_drag_overlay_visible(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Keep the full-window drop target active while dragging."""
        if DropZone.input_paths_from_event(event):
            self._set_drag_overlay_visible(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Load MIDI files or folders dropped anywhere in the window."""
        paths = DropZone.input_paths_from_event(event)
        self._set_drag_overlay_visible(False)
        if not paths:
            event.ignore()
            return
        self.load_files(paths)
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
                if DropZone.input_paths_from_event(event):  # type: ignore[arg-type]
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

    @Slot()
    def _toggle_source_preview(self) -> None:
        """Expand or restore the source table without changing its data."""
        self._source_preview_expanded = not self._source_preview_expanded
        expanded = self._source_preview_expanded
        self.source_expand_button.setText("Collapse" if expanded else "Expand")
        self._action_widget.setVisible(not expanded)
        self._split_widget.setVisible(not expanded)
        self.result_card.setVisible(not expanded)
        self.source_table.setMaximumHeight(16777215 if expanded else 174)
        self._main_layout.setStretchFactor(self.source_card, 1 if expanded else 0)
        self._main_layout.setStretchFactor(self.result_card, 0 if expanded else 1)
        self._update_result_height()

    def _update_result_height(self) -> None:
        """Keep the result panel proportional to the reference viewport."""
        if hasattr(self, "result_card"):
            scale = max(0.4, min(1.0, self.height() / 1041))
            self._main_layout.setSpacing(max(4, int(8 * scale)))
            self.browse_button.setMinimumHeight(max(38, int(52 * scale)))
            self._info_widget.setFixedHeight(max(40, int(52 * scale)))
            self.output_card.setFixedHeight(max(86, int(102 * scale)))
            self.export_button.setMinimumHeight(max(42, int(58 * scale)))
            if self._source_preview_expanded:
                self.result_card.setMinimumHeight(0)
            else:
                self.result_card.setMinimumHeight(max(230, int(self.height() * 0.34)))
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

    def _populate_source_table(
        self, analyses: tuple[tuple[Path, MidiProjectAnalysis], ...]
    ) -> None:
        """Show every detected source with selection and rename controls."""
        rows = [
            (path, source)
            for path, analysis in analyses
            for source in analysis.sources
        ]
        self.source_table.blockSignals(True)
        try:
            self.source_table.setRowCount(len(rows))
            for row, (path, source) in enumerate(rows):
                use_item = QTableWidgetItem()
                use_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                )
                use_item.setCheckState(Qt.CheckState.Checked)
                use_item.setData(Qt.ItemDataRole.UserRole, path)
                use_item.setData(Qt.ItemDataRole.UserRole + 1, source.id)
                use_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.source_table.setItem(row, 0, use_item)

                file_item = QTableWidgetItem(path.name)
                file_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.source_table.setItem(row, 1, file_item)

                source_item = QTableWidgetItem(source.name)
                source_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable
                )
                source_item.setData(Qt.ItemDataRole.UserRole, source.name)
                self.source_table.setItem(row, 2, source_item)

                self.source_table.setItem(
                    row, 3, self._read_only_item(f"Track {source.track_index + 1}")
                )
                channel = "—" if source.channel is None else f"Ch {source.channel + 1}"
                self.source_table.setItem(row, 4, self._read_only_item(channel))
                self.source_table.setItem(
                    row, 5, self._read_only_item(str(source.note_count))
                )
                self.source_table.setItem(
                    row, 6, self._read_only_item(self._format_note_range(source))
                )
        finally:
            self.source_table.blockSignals(False)
        self._update_controls()

    @staticmethod
    def _read_only_item(text: str) -> QTableWidgetItem:
        """Create a non-editable table cell."""
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    @staticmethod
    def _format_note_range(source: MidiSource) -> str:
        """Format a source's lowest and highest MIDI note as note names."""
        if source.lowest_note is None or source.highest_note is None:
            return "—"
        lowest = MainWindow._format_note(source.lowest_note)
        highest = MainWindow._format_note(source.highest_note)
        return lowest if lowest == highest else f"{lowest}–{highest}"

    @staticmethod
    def _format_note(note: int) -> str:
        """Convert a MIDI note number to scientific pitch notation."""
        return f"{_NOTE_NAMES[note % 12]}{note // 12 - 1}"

    def _selected_source_selections(self) -> dict[Path, MidiSourceSelection]:
        """Return the current checkboxes and renamed source values."""
        selected: dict[Path, set[str]] = {}
        overrides: dict[Path, dict[str, str]] = {}
        for row in range(self.source_table.rowCount()):
            use_item = self.source_table.item(row, 0)
            source_item = self.source_table.item(row, 2)
            if use_item is None or source_item is None:
                continue
            path = use_item.data(Qt.ItemDataRole.UserRole)
            source_id = use_item.data(Qt.ItemDataRole.UserRole + 1)
            if not isinstance(path, Path) or not isinstance(source_id, str):
                continue
            selected.setdefault(path, set())
            overrides.setdefault(path, {})
            if use_item.checkState() == Qt.CheckState.Checked:
                selected[path].add(source_id)
            original_name = source_item.data(Qt.ItemDataRole.UserRole)
            current_name = source_item.text().strip()
            if (
                isinstance(original_name, str)
                and current_name
                and current_name != original_name
            ):
                overrides[path][source_id] = current_name
        return {
            path: MidiSourceSelection(ids, overrides[path])
            for path, ids in selected.items()
        }

    def _has_selected_sources(self) -> bool:
        """Return whether at least one source is currently checked."""
        return any(
            self.source_table.item(row, 0) is not None
            and self.source_table.item(row, 0).checkState() == Qt.CheckState.Checked
            for row in range(self.source_table.rowCount())
        )

    def _source_item_changed(self, _: QTableWidgetItem) -> None:
        """Refresh export availability after a source checkbox changes."""
        self._update_controls()

    @Slot()
    def _browse_for_file(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose MIDI files",
            str(self._input_path.parent if self._input_path else Path.home()),
            "MIDI files (*.mid *.midi)",
        )
        if filenames:
            self.load_files(tuple(Path(filename) for filename in filenames))

    @Slot(Path)
    def load_file(self, path: Path) -> None:
        """Start analysis for a selected MIDI file."""
        self.load_files((path,))

    def load_files(self, paths: tuple[Path, ...] | list[Path]) -> None:
        """Start analysis for MIDI files and folders selected by the user."""
        requested = tuple(Path(path) for path in paths)
        if not requested:
            self._show_message(
                "Choose MIDI files",
                "Please select at least one MIDI file or folder.",
                QMessageBox.Icon.Warning,
            )
            return
        if self._is_busy:
            return

        self._input_paths = requested
        self._input_path = requested[0]
        self._analysis = None
        self._analyses = ()
        self._last_output_dir = None
        self.source_label.setText(
            requested[0].name if len(requested) == 1 else f"{len(requested)} MIDI files selected"
        )
        self.detected_label.setText("Analyzing MIDI sources…")
        self.status_label.setText("Analyzing MIDI…")
        self.output_dir_input.setText(str(self._default_output_directory(requested)))
        self.result_list.clear()
        self.source_table.setRowCount(0)
        self._update_controls()

        mode = self._selected_mode()
        self._start_worker(
            lambda _progress: self._analyze_inputs(requested, mode),
            self._analysis_loaded,
            "The MIDI files could not be analyzed. Please try another selection.",
            clear_analysis_on_failure=True,
        )

    def _analyze_inputs(
        self, requested: tuple[Path, ...], mode: SplitMode
    ) -> tuple[tuple[Path, MidiProjectAnalysis], ...]:
        """Expand selected folders and analyze every discovered MIDI file."""
        inputs = self.service.collect_midi_inputs(requested)
        return tuple((path, self.service.analyze(path, mode)) for path in inputs)

    @staticmethod
    def _default_output_directory(requested: tuple[Path, ...]) -> Path:
        """Choose the current single-file path or a shared batch root."""
        if len(requested) == 1 and requested[0].is_file():
            return requested[0].with_name(f"{requested[0].stem} - MIDI Stems")
        if len(requested) == 1 and requested[0].is_dir():
            return requested[0] / "Pattern Atlas Batch"
        parents = [path.parent for path in requested]
        return Path(os.path.commonpath([str(path) for path in parents])) / "Pattern Atlas Batch"

    @Slot(int)
    def _mode_changed(self, _: int) -> None:
        if self._input_paths and not self._is_busy:
            self.load_files(self._input_paths)

    @Slot()
    def _choose_output_directory(self) -> None:
        start_dir = self.output_dir_input.text() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Choose output folder", start_dir)
        if directory:
            self.output_dir_input.setText(directory)

    @Slot()
    def _export(self) -> None:
        # Keep the single-file state contract usable for callers that loaded
        # the analysis directly before the batch workflow was introduced.
        if not self._input_paths and self._input_path is not None:
            self._input_paths = (self._input_path,)
        if not self._analyses and self._analysis is not None and self._input_path is not None:
            self._analyses = ((self._input_path, self._analysis),)
        if not self._input_paths or not self._analyses:
            return
        output_text = self.output_dir_input.text().strip()
        if not output_text:
            self._show_message(
                "Choose an output folder",
                "Choose a folder for the exported MIDI files.",
                QMessageBox.Icon.Warning,
            )
            return

        output_dir = Path(output_text)
        mode = self._selected_mode()
        selections = self._selected_source_selections()
        self.status_label.setText("Exporting MIDI stems…")
        self.result_list.clear()
        direct_single_file = (
            len(self._input_paths) == 1
            and self._input_paths[0].is_file()
            and len(self._analyses) == 1
        )
        if direct_single_file:
            input_path = self._analyses[0][0]
            selection = selections.get(input_path, MidiSourceSelection())
            operation = lambda progress: self.service.export(
                input_path,
                output_dir,
                mode,
                on_stem=progress,
                selected_source_ids=selection.source_ids,
                name_overrides=selection.name_overrides,
            )
        else:
            operation = lambda progress: self.service.export_many(
                self._input_paths,
                output_dir,
                mode,
                on_stem=progress,
                source_selections=selections,
            )
        self._start_worker(
            operation,
            self._export_finished,
            "The MIDI stems could not be exported. Please try again.",
            clear_analysis_on_failure=False,
            on_progress=self._export_progress,
        )

    def _analysis_loaded(self, result: object) -> None:
        analyses = result
        if not isinstance(analyses, tuple) or not all(
            isinstance(item, tuple)
            and len(item) == 2
            and isinstance(item[0], Path)
            and isinstance(item[1], MidiProjectAnalysis)
            for item in analyses
        ):
            raise TypeError("Analysis worker returned an unexpected result.")
        self._analyses = analyses
        self._analysis = analyses[0][1] if len(analyses) == 1 else None
        source_count = sum(len(analysis.sources) for _, analysis in analyses)
        if len(analyses) == 1:
            self.source_label.setText(analyses[0][0].name)
        else:
            self.source_label.setText(f"{len(analyses)} MIDI files selected")
        self.detected_label.setText(f"{source_count} MIDI sources")
        self._populate_source_table(analyses)
        self.status_label.setText("Ready to export.")
        self._update_controls()

    def _export_finished(self, result: object) -> None:
        export_result = result
        if not isinstance(export_result, (ExportResult, MidiBatchResult)):
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
            self._analyses = ()
            self.source_table.setRowCount(0)
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
        self.export_button.setEnabled(
            bool(self._analyses) and self._has_selected_sources() and not self._is_busy
        )
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
