"""Classify MIDI metadata by the timeline scope it belongs to."""

from .models import TimedMidiEvent

CONDUCTOR_METADATA_TYPES = frozenset(
    {"key_signature", "set_tempo", "smpte_offset", "time_signature"}
)


def is_global_event(event: TimedMidiEvent) -> bool:
    """Return whether *event* belongs on the shared conductor timeline."""
    return event.message.is_meta and event.message.type in CONDUCTOR_METADATA_TYPES
