"""Analyze absolute-tick MIDI events into global data and exportable sources."""

from collections.abc import Iterable

from .metadata import is_global_event
from .models import MidiProjectAnalysis, MidiSource, SplitMode, TimedMidiEvent
from .reader import ReadMidiFile


def analyze_midi(read: ReadMidiFile, mode: SplitMode = SplitMode.AUTO) -> MidiProjectAnalysis:
    """Identify a conservative track- or channel-based split for *read*."""
    musical_tracks = tuple(index for index, track in enumerate(read.tracks) if has_note_on(track))
    strategy = resolve_strategy(mode, musical_tracks)
    sources, source_events = detect_sources(read.tracks, strategy)
    return MidiProjectAnalysis(
        read.ticks_per_beat,
        global_events(read.tracks),
        sources,
        total_notes(sources),
        source_events,
    )


def has_note_on(events: Iterable[TimedMidiEvent]) -> bool:
    """Return whether *events* contains an audible note-on event."""
    return any(is_note_on(event) for event in events)


def resolve_strategy(mode: SplitMode, musical_tracks: tuple[int, ...]) -> SplitMode:
    """Choose tracks only when AUTO finds notes in more than one track."""
    if mode is not SplitMode.AUTO:
        return mode
    return SplitMode.TRACK if len(musical_tracks) > 1 else SplitMode.CHANNEL


def global_events(tracks: tuple[tuple[TimedMidiEvent, ...], ...]) -> tuple[TimedMidiEvent, ...]:
    """Return conductor metadata in deterministic timeline order."""
    events: list[TimedMidiEvent] = []
    for track in tracks:
        is_conductor_track = not has_note_on(track)
        events.extend(
            event
            for event in track
            if is_global_event(event)
            or (
                is_conductor_track
                and event.message.type != "end_of_track"
                and (event.message.is_meta or event.message.type == "sysex")
            )
        )
    return tuple(sorted(events, key=event_sort_key))


def detect_sources(
    tracks: tuple[tuple[TimedMidiEvent, ...], ...], strategy: SplitMode
) -> tuple[tuple[MidiSource, ...], dict[str, tuple[TimedMidiEvent, ...]]]:
    """Build sources and their non-conductor event streams for *strategy*."""
    if strategy is SplitMode.TRACK:
        candidates = _track_candidates(tracks)
    else:
        candidates = _channel_candidates(tracks)

    sources: list[MidiSource] = []
    source_events: dict[str, tuple[TimedMidiEvent, ...]] = {}
    for track_index, port, channel, events in candidates:
        source = _make_source(track_index, port, channel, events, tracks[track_index])
        sources.append(source)
        source_events[source.id] = events
    return tuple(sources), source_events


def total_notes(sources: Iterable[MidiSource]) -> int:
    """Count audible note-on events across the detected sources."""
    return sum(source.note_count for source in sources)


def _track_candidates(
    tracks: tuple[tuple[TimedMidiEvent, ...], ...]
) -> tuple[tuple[int, int | None, None, tuple[TimedMidiEvent, ...]], ...]:
    candidates = []
    for track_index, track in enumerate(tracks):
        if not has_note_on(track):
            continue
        events = tuple(event for event in track if not is_global_event(event))
        ports = {event.port for event in events if is_channel_event(event)}
        port = next(iter(ports)) if len(ports) == 1 else None
        candidates.append((track_index, port, None, events))
    return tuple(candidates)


def _channel_candidates(
    tracks: tuple[tuple[TimedMidiEvent, ...], ...]
) -> tuple[tuple[int, int | None, int, tuple[TimedMidiEvent, ...]], ...]:
    candidates = []
    for track_index, track in enumerate(tracks):
        identities = {
            (event.port, event.message.channel)
            for event in track
            if is_note_on(event)
        }
        for port, channel in sorted(identities, key=lambda item: (item[0] is not None, item[0] or 0, item[1])):
            events = tuple(
                event
                for event in track
                if _belongs_to_channel_source(event, port, channel)
            )
            candidates.append((track_index, port, channel, events))
    return tuple(candidates)


def _belongs_to_channel_source(event: TimedMidiEvent, port: int | None, channel: int) -> bool:
    if is_global_event(event):
        return False
    if event.message.type == "end_of_track":
        return False
    if event.message.type == "sysex":
        # SysEx has no channel.  It belongs to every channel stem sharing its
        # source track/port, which conservatively preserves port-scoped device
        # data instead of discarding it during a channel split.
        return event.port == port
    if event.message.is_meta:
        if event.message.type in {"channel_prefix", "midi_port"}:
            return event.port == port and (
                event.message.type == "midi_port"
                or event.message.channel == channel
            )
        return True
    if is_channel_event(event):
        return event.port == port and event.message.channel == channel
    return True


def _make_source(
    track_index: int,
    port: int | None,
    channel: int | None,
    events: tuple[TimedMidiEvent, ...],
    track: tuple[TimedMidiEvent, ...],
) -> MidiSource:
    name = _source_name(track, track_index, channel)
    source_id = f"t{track_index}-p{port if port is not None else 'none'}-c{channel if channel is not None else 'all'}"
    note_events = tuple(event for event in events if is_note_on(event))
    return MidiSource(
        source_id,
        track_index,
        name,
        port,
        channel,
        len(events),
        len(note_events),
        min(event.tick for event in events),
        max(event.tick for event in events),
    )


def _source_name(track: tuple[TimedMidiEvent, ...], track_index: int, channel: int | None) -> str:
    for message_type in ("track_name", "instrument_name"):
        for event in track:
            if event.message.type == message_type and getattr(event.message, "name", ""):
                return event.message.name
    if channel is not None:
        return f"Channel {channel + 1}"
    return f"Track {track_index + 1}"


def is_note_on(event: TimedMidiEvent) -> bool:
    """Return true only for note_on messages whose velocity is nonzero."""
    return event.message.type == "note_on" and event.message.velocity > 0


def is_channel_event(event: TimedMidiEvent) -> bool:
    return hasattr(event.message, "channel")


def event_sort_key(event: TimedMidiEvent) -> tuple[int, int, int]:
    return event.tick, event.track_index, event.order
