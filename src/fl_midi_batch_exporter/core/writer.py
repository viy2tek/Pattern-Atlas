"""Write timeline-preserving Type 1 MIDI stem files."""

from collections.abc import Sequence
from pathlib import Path

import mido

from .models import MidiExportError, MidiProjectAnalysis, MidiSource, TimedMidiEvent


def to_delta_messages(
    events: Sequence[TimedMidiEvent],
) -> list[mido.Message | mido.MetaMessage]:
    """Copy absolute-tick events with MIDI delta times reconstructed."""
    previous_tick = 0
    result: list[mido.Message | mido.MetaMessage] = []
    for event in sorted(events, key=lambda item: (item.tick, item.order)):
        result.append(event.message.copy(time=event.tick - previous_tick))
        previous_tick = event.tick
    return result


def write_stem(
    path: Path,
    analysis: MidiProjectAnalysis,
    source: MidiSource,
    events: Sequence[TimedMidiEvent],
) -> None:
    """Write one source as a two-track Type 1 MIDI file.

    The conductor track contains global events and the second track contains
    the supplied source stream.  Both tracks receive a single terminal
    ``end_of_track`` event after their absolute timing has been reconstructed.
    """
    source_events = tuple(event for event in events if event.message.type != "end_of_track")
    if not source_events:
        raise MidiExportError(f"Cannot write MIDI stem '{source.name}': source has no events.")

    midi = mido.MidiFile(type=1, ticks_per_beat=analysis.ticks_per_beat)
    midi.tracks.append(_track_with_end_of_track(analysis.global_events))
    midi.tracks.append(_track_with_end_of_track(source_events))

    output_path = Path(path)
    try:
        midi.save(output_path)
    except (OSError, ValueError) as error:
        raise MidiExportError(
            f"Could not write MIDI stem '{source.name}' to '{output_path}'. "
            "Check that the output folder is writable and try again."
        ) from error


def _track_with_end_of_track(events: Sequence[TimedMidiEvent]) -> mido.MidiTrack:
    """Build one track while guaranteeing exactly one terminal event."""
    track = mido.MidiTrack()
    track.extend(
        to_delta_messages(
            tuple(event for event in events if event.message.type != "end_of_track")
        )
    )
    track.append(mido.MetaMessage("end_of_track", time=0))
    return track
