"""Immutable data models shared by the MIDI exporter core."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import mido


class SplitMode(StrEnum):
    AUTO = "auto"
    TRACK = "track"
    CHANNEL = "channel"


@dataclass(frozen=True)
class TimedMidiEvent:
    tick: int
    order: int
    track_index: int
    port: int | None
    message: mido.Message | mido.MetaMessage


@dataclass(frozen=True)
class MidiSource:
    id: str
    track_index: int
    name: str
    port: int | None
    channel: int | None
    event_count: int
    note_count: int
    first_tick: int
    last_tick: int
    suggested_filename: str = ""


@dataclass(frozen=True)
class MidiProjectAnalysis:
    ticks_per_beat: int
    global_events: tuple[TimedMidiEvent, ...]
    sources: tuple[MidiSource, ...]
    total_notes: int
    source_events: Mapping[str, tuple[TimedMidiEvent, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Defensively freeze the mapping supplied by callers."""
        object.__setattr__(self, "source_events", MappingProxyType(dict(self.source_events)))


@dataclass(frozen=True)
class ExportedStem:
    path: Path
    source: MidiSource
    event_count: int
    note_count: int


@dataclass(frozen=True)
class ExportResult:
    stems: tuple[ExportedStem, ...]
    total_notes: int = 0


class MidiExportError(Exception):
    """A user-recoverable error while reading, analyzing, or exporting MIDI."""
