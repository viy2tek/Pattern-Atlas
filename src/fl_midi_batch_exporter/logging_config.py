"""Persistent diagnostic logging for the desktop application."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "fl_midi_batch_exporter"


def configure_logging(log_dir: Path | None = None) -> Path | None:
    """Configure one rotating application log without blocking startup on failure."""
    directory = log_dir or _default_log_directory()
    log_path = directory / "pattern-atlas.log"
    logger = logging.getLogger(LOGGER_NAME)

    for handler in logger.handlers:
        if getattr(handler, "_pattern_atlas_handler", False):
            return Path(handler.baseFilename)

    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError:
        return None

    handler._pattern_atlas_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    return log_path


def _default_log_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "Pattern Atlas" / "logs"
