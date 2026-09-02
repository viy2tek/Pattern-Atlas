"""Write timeline-preserving Type 1 MIDI stem files."""

import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import mido

from .models import MidiExportError, MidiProjectAnalysis, MidiSource, TimedMidiEvent

OutputFileIdentity = tuple[int, int]


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
    on_commit: Callable[[OutputFileIdentity], None] | None = None,
) -> OutputFileIdentity:
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
    descriptor: int | None = None
    temporary_path: Path | None = None
    identity: OutputFileIdentity | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        os.close(descriptor)
        descriptor = None
        midi.save(temporary_path)
        temporary_stat = temporary_path.stat()
        identity = temporary_stat.st_dev, temporary_stat.st_ino
        os.rename(temporary_path, output_path)
        if on_commit is not None:
            on_commit(identity)
        return identity
    except BaseException as error:
        _close_descriptor_quietly(descriptor)
        _remove_file_quietly(temporary_path)
        if identity is not None:
            remove_file_if_owned(output_path, identity)
        if not isinstance(error, (OSError, ValueError)):
            raise
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


def _remove_file_quietly(path: Path | None) -> None:
    """Best-effort cleanup that never masks the operation's original failure."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except BaseException:  # noqa: BLE001 - cleanup must preserve the active failure
        return


def _close_descriptor_quietly(descriptor: int | None) -> None:
    """Close a temporary descriptor while preserving an active exception."""
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except BaseException:  # noqa: BLE001 - cleanup must preserve the active failure
        return


def remove_file_if_owned(path: Path, identity: OutputFileIdentity) -> None:
    """Remove *path* only while it is still the file identified by *identity*."""
    try:
        current = path.stat()
        if (current.st_dev, current.st_ino) == identity:
            path.unlink()
    except BaseException:  # noqa: BLE001 - rollback must preserve the active failure
        return
