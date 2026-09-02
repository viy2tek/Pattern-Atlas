"""Desktop application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from .application import MidiExportService
from .gui.main_window import MainWindow


def run() -> int:
    """Show the MIDI exporter window and return Qt's exit status."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Pattern Atlas")
    window = MainWindow(MidiExportService())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
