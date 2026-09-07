"""Immutable data models shared by the MIDI exporter core."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import mido


class SplitMode(StrEnum):
    AUTO = "auto"
    SMART = "smart"
    TRACK = "track"
    CHANNEL = "channel"


@dataclass(frozen=True)
class MidiInspector:
    """Compact diagnostic facts shown after a MIDI file is analyzed."""

    midi_type: int
    track_count: int
    musical_track_count: int
    channel_count: int
    note_count: int
    tempo_bpm: float
    ticks_per_beat: int
    split_mode: SplitMode
    split_reason: str


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
    lowest_note: int | None = None
    highest_note: int | None = None


@dataclass(frozen=True)
class MidiProjectAnalysis:
    ticks_per_beat: int
    global_events: tuple[TimedMidiEvent, ...]
    sources: tuple[MidiSource, ...]
    total_notes: int
    source_events: Mapping[str, tuple[TimedMidiEvent, ...]] = field(default_factory=dict)
    inspector: MidiInspector | None = None

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


@dataclass(frozen=True)
class MidiSourceSelection:
    """Optional source filter and display-name overrides for one input."""

    source_ids: frozenset[str] | None = None
    name_overrides: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze caller-provided selection collections."""
        if self.source_ids is not None:
            object.__setattr__(self, "source_ids", frozenset(self.source_ids))
        object.__setattr__(
            self, "name_overrides", MappingProxyType(dict(self.name_overrides))
        )


@dataclass(frozen=True)
class MidiBatchItem:
    """The exported result and destination for one input MIDI file."""

    input_path: Path
    output_dir: Path
    result: ExportResult


@dataclass(frozen=True)
class MidiBatchResult:
    """Results from exporting multiple MIDI input files."""

    items: tuple[MidiBatchItem, ...]

    @property
    def stems(self) -> tuple[ExportedStem, ...]:
        """Return all exported stems in input order."""
        return tuple(stem for item in self.items for stem in item.result.stems)

    @property
    def total_notes(self) -> int:
        """Return the total note count across all exported inputs."""
        return sum(item.result.total_notes for item in self.items)


class MidiExportError(Exception):
    """A user-recoverable error while reading, analyzing, or exporting MIDI."""
