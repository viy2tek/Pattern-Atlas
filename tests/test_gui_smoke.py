import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mido
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
