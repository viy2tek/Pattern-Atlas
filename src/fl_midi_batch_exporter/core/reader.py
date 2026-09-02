"""Read MIDI files into immutable events with absolute tick positions."""

from dataclasses import dataclass
from pathlib import Path

import mido

from .models import MidiExportError, TimedMidiEvent


@dataclass(frozen=True)
class ReadMidiFile:
    """The file-level metadata and events extracted from a MIDI file."""

    midi_type: int
    ticks_per_beat: int
    tracks: tuple[tuple[TimedMidiEvent, ...], ...]


def validate_input_path(path: Path) -> None:
    """Validate the user-selected path before passing it to the MIDI parser."""
    if path.suffix.lower() not in {".mid", ".midi"}:
        raise MidiExportError("Please select a MIDI file with a .mid or .midi extension.")


def read_midi(path: Path) -> ReadMidiFile:
    """Read *path*, converting every track's delta times to absolute ticks."""
    path = Path(path)
    validate_input_path(path)
    try:
        midi = mido.MidiFile(path)
    except (OSError, EOFError, ValueError) as error:
        raise MidiExportError("The selected file is not a readable MIDI file.") from error
    return to_absolute_ticks(midi)


def to_absolute_ticks(midi: mido.MidiFile) -> ReadMidiFile:
    """Convert a parsed Mido file to stable, absolute-tick event tuples."""
    tracks: list[tuple[TimedMidiEvent, ...]] = []
    for track_index, track in enumerate(midi.tracks):
        tick = 0
        port: int | None = None
        events: list[TimedMidiEvent] = []
        for order, message in enumerate(track):
            tick += message.time
            if message.type == "midi_port":
                port = message.port
            events.append(TimedMidiEvent(tick, order, track_index, port, message))
        tracks.append(tuple(events))
    return ReadMidiFile(midi.type, midi.ticks_per_beat, tuple(tracks))
