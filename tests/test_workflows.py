from collections.abc import Callable
from pathlib import Path

import mido
import pytest

from fl_midi_batch_exporter.application import MidiExportService
from fl_midi_batch_exporter.core.analyzer import analyze_midi
from fl_midi_batch_exporter.core.models import MidiExportError, SplitMode
from fl_midi_batch_exporter.core.naming import reserve_output_path, suggest_stem_name
from fl_midi_batch_exporter.core.reader import read_midi


def test_auto_uses_tracks_when_multiple_tracks_have_notes(
    midi_file: Callable[..., Path],
) -> None:
    path = midi_file(
        "tracks.mid",
        [
            [mido.Message("note_on", note=60, velocity=100)],
            [mido.Message("note_on", note=48, velocity=100)],
        ],
    )

    analysis = analyze_midi(read_midi(path))

    assert [(source.track_index, source.channel) for source in analysis.sources] == [
        (0, None),
        (1, None),
    ]


def test_auto_uses_channels_when_one_track_has_multiple_channels(
    midi_file: Callable[..., Path],
) -> None:
    path = midi_file(
        "channels.mid",
        [[
            mido.Message("note_on", channel=0, note=60, velocity=100),
            mido.Message("note_on", channel=9, note=36, velocity=100),
        ]],
    )

    analysis = analyze_midi(read_midi(path))

    assert [source.channel for source in analysis.sources] == [0, 9]


def test_channel_split_keeps_same_channel_on_different_tracks_separate(
    midi_file: Callable[..., Path],
) -> None:
    path = midi_file(
        "same-channel.mid",
        [
            [mido.Message("note_on", channel=0, note=60, velocity=100)],
            [mido.Message("note_on", channel=0, note=48, velocity=100)],
        ],
    )

    analysis = analyze_midi(read_midi(path), SplitMode.CHANNEL)

    assert [source.id for source in analysis.sources] == ["t0-pnone-c0", "t1-pnone-c0"]


def test_empty_midi_is_rejected_before_output_directory_is_created(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    path = midi_file("empty.mid", [[mido.MetaMessage("set_tempo", tempo=500_000)]])
    output = tmp_path / "stems"

    with pytest.raises(MidiExportError, match="No MIDI notes"):
        MidiExportService().export(path, output)

    assert not output.exists()


def test_generated_names_are_windows_safe_and_do_not_overwrite(tmp_path: Path) -> None:
    from fl_midi_batch_exporter.core.models import MidiSource

    source = MidiSource("lead", 0, 'Lead: A/B?*', None, None, 2, 1, 0, 120)
    filename = suggest_stem_name(source, 1)
    first = tmp_path / filename
    first.write_bytes(b"existing")

    reserved = reserve_output_path(tmp_path, filename)

    assert filename == "01 - Lead AB.mid"
    assert reserved.name == "01 - Lead AB (2).mid"


def test_export_preserves_existing_stems_by_choosing_a_suffix(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    path = midi_file(
        "lead.mid",
        [[
            mido.MetaMessage("track_name", name="Lead"),
            mido.Message("note_on", note=60, velocity=100),
        ]],
    )
    output = tmp_path / "stems"
    output.mkdir()
    existing = output / "01 - Lead.mid"
    existing.write_bytes(b"do not replace")

    result = MidiExportService().export(path, output, SplitMode.TRACK)

    assert existing.read_bytes() == b"do not replace"
    assert result.stems[0].path.name == "01 - Lead (2).mid"
