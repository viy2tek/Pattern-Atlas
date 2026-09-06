import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mido
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from fl_midi_batch_exporter.application import MidiExportService
from fl_midi_batch_exporter.core.models import MidiExportError
from fl_midi_batch_exporter.gui.main_window import MainWindow


def test_main_window_preserves_the_current_layout_contract() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MidiExportService())

    assert window.windowTitle() == "Pattern Atlas"
    assert window.minimumWidth() == 760
    assert window.minimumHeight() == 700
    assert window.maximumHeight() == 700
    assert window.export_button.text() == "Export MIDI Stems"
    assert window.export_button.isEnabled() is False
    assert window.mode_selector.count() == 3

    window.close()
    app.processEvents()


def test_result_list_can_show_stems_as_they_finish(
    midi_file, tmp_path
) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MidiExportService())
    window._show_message = lambda *args: None

    input_path = midi_file(
        "progress.mid",
        [
            [
                mido.MetaMessage("track_name", name="Lead"),
                mido.Message("note_on", note=60, velocity=100),
                mido.Message("note_off", note=60, velocity=0, time=120),
            ],
            [
                mido.MetaMessage("track_name", name="Bass"),
                mido.Message("note_on", note=48, velocity=100),
                mido.Message("note_off", note=48, velocity=0, time=120),
            ],
        ],
    )
    window._input_path = input_path
    window._analysis = MidiExportService().analyze(input_path)
    window.output_dir_input.setText(str(tmp_path / "stems"))
    window._export()

    deadline = time.monotonic() + 5
    while window._is_busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert not window._is_busy
    assert window.result_list.count() == 2
    window.close()
    app.processEvents()


def test_failed_export_removes_partial_rows_from_the_result_list() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MidiExportService())
    window._show_message = lambda *args: None
    window.result_list.addItem("partial.mid — 1 notes")

    window._worker_failed("write failed", MidiExportError("write failed"), False)

    assert window.result_list.count() == 0
    window.close()
    app.processEvents()


def test_main_window_exports_multiple_midi_inputs(
    midi_file, tmp_path
) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MidiExportService())
    window._show_message = lambda *args: None

    first = midi_file(
        "Song 01.mid",
        [[mido.Message("note_on", note=60, velocity=100)]],
    )
    second = midi_file(
        "Song 02.mid",
        [[mido.Message("note_on", note=48, velocity=100)]],
    )

    window.load_files([first, second])
    deadline = time.monotonic() + 5
    while window._is_busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert not window._is_busy
    assert window.source_label.text() == "2 MIDI files selected"
    assert window.detected_label.text() == "2 MIDI sources"
    window.output_dir_input.setText(str(tmp_path / "batch-output"))
    window._export()

    deadline = time.monotonic() + 5
    while window._is_busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert not window._is_busy
    assert window.result_list.count() == 2
    assert (tmp_path / "batch-output" / "Song 01 - MIDI Stems").is_dir()
    assert (tmp_path / "batch-output" / "Song 02 - MIDI Stems").is_dir()
    window.close()
    app.processEvents()


def test_main_window_previews_and_filters_sources_before_export(
    midi_file, tmp_path
) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MidiExportService())
    window._show_message = lambda *args: None
    input_path = midi_file(
        "preview.mid",
        [
            [
                mido.MetaMessage("track_name", name="Lead"),
                mido.Message("note_on", note=60, velocity=100),
            ],
            [
                mido.MetaMessage("track_name", name="Bass"),
                mido.Message("note_on", note=48, velocity=100),
            ],
        ],
    )

    window.load_file(input_path)
    deadline = time.monotonic() + 5
    while window._is_busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert window.source_table.rowCount() == 2
    assert window.source_table.item(0, 0).checkState().name == "Checked"
    assert window.source_table.item(0, 2).text() == "Lead"
    assert window.source_table.item(0, 5).text() == "1"
    assert window.source_table.item(0, 6).text() == "C4"

    window.source_table.item(0, 2).setText("Lead Main")
    window.source_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    window.source_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    assert window.export_button.isEnabled() is False
    window.source_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    window.source_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    window.output_dir_input.setText(str(tmp_path / "stems"))
    window._export()

    deadline = time.monotonic() + 5
    while window._is_busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert window.result_list.count() == 1
    assert (tmp_path / "stems" / "01 - Lead Main.mid").exists()
    window.close()
    app.processEvents()


def test_source_preview_can_expand_and_collapse() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MidiExportService())

    assert window.source_expand_button.text() == "Expand"
    assert window._source_preview_expanded is False

    window.source_expand_button.click()
    app.processEvents()

    assert window.source_expand_button.text() == "Collapse"
    assert window._source_preview_expanded is True
    assert window._action_widget.isHidden() is True
    assert window._split_widget.isHidden() is True
    assert window.result_card.isHidden() is True
    assert window.source_table.maximumHeight() > 174

    window.source_expand_button.click()
    app.processEvents()

    assert window.source_expand_button.text() == "Expand"
    assert window._source_preview_expanded is False
    assert window._action_widget.isHidden() is False
    assert window._split_widget.isHidden() is False
    assert window.result_card.isHidden() is False
    assert window.source_table.maximumHeight() == 174
    window.close()
    app.processEvents()


def test_exported_files_card_stays_inside_the_content_surface() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MidiExportService())
    window.show()
    app.processEvents()

    assert window.result_card.geometry().bottom() <= window._content_surface.rect().bottom()

    window.close()
    app.processEvents()
