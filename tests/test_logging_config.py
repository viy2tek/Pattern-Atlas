import importlib
import logging
from pathlib import Path


def test_logging_writes_diagnostics_to_a_rotating_local_file(tmp_path: Path) -> None:
    logging_config = importlib.import_module("fl_midi_batch_exporter.logging_config")
    log_path = logging_config.configure_logging(tmp_path)

    logging.getLogger("fl_midi_batch_exporter.test").error("diagnostic marker")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_path == tmp_path / "pattern-atlas.log"
    assert "diagnostic marker" in log_path.read_text(encoding="utf-8")
