"""Deterministic, Windows-safe names for exported MIDI stems."""

import re
from pathlib import Path

from .models import MidiSource

_INVALID = '<>:"/\\|?*'
_GENERIC_NAME = re.compile(r"(?:channel|track)\s+\d+\Z", re.IGNORECASE)


def _safe_name(value: str) -> str:
    """Remove characters and endings that Windows does not allow in names."""
    cleaned = "".join(char for char in value if char not in _INVALID)
    return cleaned.rstrip(" .")


def suggest_stem_name(
    source: MidiSource, number: int, name_override: str | None = None
) -> str:
    """Return a stable numbered MIDI filename for *source*."""
    name = _safe_name(name_override if name_override is not None else source.name)
    if not name or (
        name_override is None and _GENERIC_NAME.fullmatch(name.strip())
    ):
        track_name = f"Track {source.track_index + 1:02d}"
        name = (
            f"{track_name} - Ch {source.channel + 1:02d}"
            if source.channel is not None
            else track_name
        )
    return f"{number:02d} - {name}.mid"


def reserve_output_path(directory: Path, filename: str) -> Path:
    """Choose *filename*, adding a numeric suffix when it already exists."""
    candidate = directory / filename
    number = 2
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    while candidate.exists():
        candidate = directory / f"{stem} ({number}){suffix}"
        number += 1
    return candidate
