import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from fl_midi_batch_exporter.application import MidiExportService
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
