"""Select the timeline events that belong to an exportable MIDI source."""

from .metadata import is_global_event
from .models import MidiProjectAnalysis, MidiSource, TimedMidiEvent


def events_for_source(
    analysis: MidiProjectAnalysis, source: MidiSource
) -> tuple[TimedMidiEvent, ...]:
    """Return *source* events in deterministic absolute-tick order.

    ``MidiProjectAnalysis.source_events`` is the authoritative per-source
    stream.  Filtering again here protects the export boundary when an
    analysis is assembled programmatically: channel messages must match the
    source's original track, port, and channel, while track-local metadata is
    retained with that source.
    """
    candidates = analysis.source_events.get(source.id, ())
    selected = (event for event in candidates if _belongs_to_source(event, source))
    return tuple(sorted(selected, key=lambda event: (event.tick, event.order)))


def _belongs_to_source(event: TimedMidiEvent, source: MidiSource) -> bool:
    """Return whether an event can be written to one source stem."""
    if event.track_index != source.track_index:
        return False
    if event.message.type == "end_of_track" or is_global_event(event):
        return False
    if event.message.type == "sysex":
        if source.channel is None:
            return True
        # SysEx is not channel-addressed.  For a channel split, keep it with
        # every source on its matching track/port; this intentional duplication
        # avoids dropping device-specific data shared by those channels.
        return event.port == source.port
    if not hasattr(event.message, "channel"):
        # Track names, port declarations, and other source-track metadata
        # describe the stem even when their own port context is unavailable.
        return True
    if source.channel is None:
        return True
    return event.port == source.port and event.message.channel == source.channel
