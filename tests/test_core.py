from collections.abc import Callable
from pathlib import Path

import mido
import pytest

import fl_midi_batch_exporter.core.writer as writer_module
from fl_midi_batch_exporter.core.analyzer import analyze_midi
from fl_midi_batch_exporter.core.models import MidiExportError, SplitMode
from fl_midi_batch_exporter.core.reader import read_midi
from fl_midi_batch_exporter.core.splitter import events_for_source
from fl_midi_batch_exporter.core.writer import write_stem


def _notes(track: mido.MidiTrack) -> list[tuple[str, int, int]]:
    tick = 0
    result: list[tuple[str, int, int]] = []
    for message in track:
        tick += message.time
        if message.type in {"note_on", "note_off"}:
            result.append((message.type, message.note, tick))
    return result


def test_reader_converts_delta_times_to_absolute_ticks(
    midi_file: Callable[..., Path],
) -> None:
    path = midi_file(
        "timing.mid",
        [[
            mido.Message("note_on", note=60, velocity=100, time=120),
            mido.Message("note_off", note=60, velocity=0, time=240),
        ]],
    )

    result = read_midi(path)

    assert [event.tick for event in result.tracks[0] if event.message.type.startswith("note_")] == [120, 360]


def test_reader_rejects_type_2_instead_of_changing_its_timeline(
    midi_file: Callable[..., Path],
) -> None:
    path = midi_file(
        "asynchronous.mid",
        [
            [mido.Message("note_on", note=60, velocity=100)],
            [mido.Message("note_on", note=48, velocity=100)],
        ],
        midi_type=2,
    )

    with pytest.raises(MidiExportError, match="Type 2"):
        read_midi(path)


def test_track_local_text_is_not_copied_to_global_conductor_events(
    midi_file: Callable[..., Path],
) -> None:
    path = midi_file(
        "lyrics.mid",
        [[
            mido.MetaMessage("track_name", name="Lead"),
            mido.MetaMessage("lyrics", text="Lead only"),
            mido.Message("note_on", note=60, velocity=100, time=10),
            mido.Message("note_off", note=60, velocity=0, time=20),
        ]],
    )

    analysis = analyze_midi(read_midi(path), SplitMode.TRACK)
    source_events = events_for_source(analysis, analysis.sources[0])

    assert "lyrics" not in [event.message.type for event in analysis.global_events]
    assert "lyrics" in [event.message.type for event in source_events]


def test_metadata_from_a_non_musical_conductor_track_is_preserved_globally(
    midi_file: Callable[..., Path],
) -> None:
    path = midi_file(
        "conductor.mid",
        [
            [
                mido.MetaMessage("track_name", name="Conductor"),
                mido.MetaMessage("text", text="Project note"),
                mido.MetaMessage("set_tempo", tempo=500_000),
            ],
            [
                mido.MetaMessage("track_name", name="Piano"),
                mido.Message("note_on", note=60, velocity=100),
            ],
        ],
    )

    analysis = analyze_midi(read_midi(path), SplitMode.TRACK)

    assert [event.message.type for event in analysis.global_events] == [
        "track_name",
        "text",
        "set_tempo",
    ]


def test_track_split_round_trip_preserves_notes_and_conductor_timing(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    path = midi_file(
        "song.mid",
        [[
            mido.MetaMessage("set_tempo", tempo=500_000),
            mido.Message("note_on", note=64, velocity=90, time=240),
            mido.Message("note_off", note=64, velocity=0, time=480),
        ]],
    )
    analysis = analyze_midi(read_midi(path), SplitMode.TRACK)
    source = analysis.sources[0]
    output = tmp_path / "stem.mid"

    write_stem(output, analysis, source, events_for_source(analysis, source))
    reopened = mido.MidiFile(output)

    assert _notes(reopened.tracks[1]) == [("note_on", 64, 240), ("note_off", 64, 720)]
    assert reopened.tracks[0][0].type == "set_tempo"


def test_failed_stem_write_never_leaves_a_partial_destination(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = midi_file(
        "source.mid",
        [[
            mido.Message("note_on", note=60, velocity=100),
            mido.Message("note_off", note=60, velocity=0, time=120),
        ]],
    )
    analysis = analyze_midi(read_midi(path), SplitMode.TRACK)
    source = analysis.sources[0]
    output = tmp_path / "partial.mid"

    def interrupted_save(self: mido.MidiFile, filename: Path) -> None:
        Path(filename).write_bytes(b"partial")
        raise OSError("disk interrupted")

    monkeypatch.setattr(mido.MidiFile, "save", interrupted_save)

    with pytest.raises(MidiExportError, match="Could not write MIDI stem"):
        write_stem(output, analysis, source, events_for_source(analysis, source))

    assert not output.exists()
    assert list(tmp_path.iterdir()) == [path]


def test_interrupted_stem_write_removes_its_temporary_file(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = midi_file(
        "interrupt-source.mid",
        [[mido.Message("note_on", note=60, velocity=100)]],
    )
    analysis = analyze_midi(read_midi(path), SplitMode.TRACK)
    source = analysis.sources[0]

    def interrupted_save(self: mido.MidiFile, filename: Path) -> None:
        Path(filename).write_bytes(b"partial")
        raise KeyboardInterrupt

    monkeypatch.setattr(mido.MidiFile, "save", interrupted_save)

    with pytest.raises(KeyboardInterrupt):
        write_stem(
            tmp_path / "interrupt.mid",
            analysis,
            source,
            events_for_source(analysis, source),
        )

    assert [item.name for item in tmp_path.iterdir()] == [path.name]


def test_cleanup_failure_does_not_hide_the_original_write_error(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = midi_file(
        "cleanup-source.mid",
        [[mido.Message("note_on", note=60, velocity=100)]],
    )
    analysis = analyze_midi(read_midi(path), SplitMode.TRACK)
    source = analysis.sources[0]
    real_unlink = Path.unlink

    def failed_save(self: mido.MidiFile, filename: Path) -> None:
        raise OSError("write failed")

    def failed_cleanup(self: Path, *args: object, **kwargs: object) -> None:
        if self.suffix == ".tmp":
            raise PermissionError("cleanup failed")
        real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(mido.MidiFile, "save", failed_save)
    monkeypatch.setattr(Path, "unlink", failed_cleanup)

    with pytest.raises(MidiExportError, match="Could not write MIDI stem"):
        write_stem(
            tmp_path / "cleanup.mid",
            analysis,
            source,
            events_for_source(analysis, source),
        )


def test_atomic_commit_never_overwrites_a_concurrently_created_destination(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = midi_file(
        "race-source.mid",
        [[mido.Message("note_on", note=60, velocity=100)]],
    )
    analysis = analyze_midi(read_midi(path), SplitMode.TRACK)
    source = analysis.sources[0]
    destination = tmp_path / "race.mid"
    real_save = mido.MidiFile.save

    def competing_save(self: mido.MidiFile, filename: Path) -> None:
        real_save(self, filename)
        destination.write_bytes(b"foreign export")

    monkeypatch.setattr(mido.MidiFile, "save", competing_save)

    with pytest.raises(MidiExportError, match="Could not write MIDI stem"):
        write_stem(
            destination,
            analysis,
            source,
            events_for_source(analysis, source),
        )

    assert destination.read_bytes() == b"foreign export"


def test_interrupt_while_closing_temporary_file_does_not_leak_it(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = midi_file(
        "close-source.mid",
        [[mido.Message("note_on", note=60, velocity=100)]],
    )
    analysis = analyze_midi(read_midi(path), SplitMode.TRACK)
    source = analysis.sources[0]
    real_close = writer_module.os.close

    def interrupted_close(descriptor: int) -> None:
        real_close(descriptor)
        raise KeyboardInterrupt

    monkeypatch.setattr(writer_module.os, "close", interrupted_close)

    with pytest.raises(KeyboardInterrupt):
        write_stem(
            tmp_path / "close.mid",
            analysis,
            source,
            events_for_source(analysis, source),
        )

    assert [item.name for item in tmp_path.iterdir()] == [path.name]


def test_interrupt_after_commit_removes_the_just_committed_destination(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = midi_file(
        "commit-source.mid",
        [[mido.Message("note_on", note=60, velocity=100)]],
    )
    analysis = analyze_midi(read_midi(path), SplitMode.TRACK)
    source = analysis.sources[0]
    destination = tmp_path / "commit.mid"
    real_rename = writer_module.os.rename

    def interrupted_rename(source_path: Path, destination_path: Path) -> None:
        real_rename(source_path, destination_path)
        raise KeyboardInterrupt

    monkeypatch.setattr(writer_module.os, "rename", interrupted_rename)

    with pytest.raises(KeyboardInterrupt):
        write_stem(
            destination,
            analysis,
            source,
            events_for_source(analysis, source),
        )

    assert not destination.exists()
