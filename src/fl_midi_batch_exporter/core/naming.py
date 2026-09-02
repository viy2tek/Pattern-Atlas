"""Deterministic, Windows-safe names for exported MIDI stems."""

from pathlib import Path

from .models import MidiSource

_INVALID = '<>:"/\\|?*'


def _safe_name(value: str) -> str:
    """Remove characters and endings that Windows does not allow in names."""
    cleaned = "".join(char for char in value if char not in _INVALID)
    return cleaned.rstrip(" .")


def suggest_stem_name(source: MidiSource, number: int) -> str:
    """Return a stable numbered MIDI filename for *source*."""
    name = _safe_name(source.name)
    if not name:
        if source.channel is not None:
            name = f"Track {source.track_index + 1:02d} - Ch {source.channel + 1:02d}"
        else:
            name = f"Track {source.track_index + 1:02d}"
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
