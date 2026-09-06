from collections.abc import Callable
from pathlib import Path

import mido
import pytest

from fl_midi_batch_exporter import application
from fl_midi_batch_exporter.application import MidiExportService
from fl_midi_batch_exporter.core.models import (
    MidiExportError,
    MidiSourceSelection,
    SplitMode,
)


def _two_track_file(midi_file: Callable[..., Path]) -> Path:
    return midi_file(
        "two-tracks.mid",
        [
            [
                mido.MetaMessage("track_name", name="Lead"),
                mido.Message("note_on", note=60, velocity=100),
                mido.Message("note_off", note=60, velocity=0, time=120),
            ],
            [
                mido.MetaMessage("track_name", name="Bass"),
                mido.Message("note_on", note=48, velocity=100),
                mido.Message("note_off", note=48, velocity=0, time=120),
            ],
        ],
    )


def test_output_path_errors_use_the_public_domain_exception(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    input_path = _two_track_file(midi_file)
    output_path = tmp_path / "not-a-directory"
    output_path.write_text("occupied", encoding="utf-8")

    with pytest.raises(MidiExportError, match="output folder"):
        MidiExportService().export(input_path, output_path)


def test_failed_batch_removes_stems_created_by_that_batch(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _two_track_file(midi_file)
    output_dir = tmp_path / "stems"
    real_write_stem = application.write_stem
    calls = 0

    def fail_second_stem(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise MidiExportError("simulated write failure")
        return real_write_stem(*args, **kwargs)

    monkeypatch.setattr(application, "write_stem", fail_second_stem)

    with pytest.raises(MidiExportError, match="simulated write failure"):
        MidiExportService().export(input_path, output_dir, SplitMode.TRACK)

    assert list(output_dir.iterdir()) == []


def test_interrupted_batch_removes_stems_created_by_that_batch(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _two_track_file(midi_file)
    output_dir = tmp_path / "stems"
    real_write_stem = application.write_stem
    calls = 0

    def interrupt_second_stem(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return real_write_stem(*args, **kwargs)

    monkeypatch.setattr(application, "write_stem", interrupt_second_stem)

    with pytest.raises(KeyboardInterrupt):
        MidiExportService().export(input_path, output_dir, SplitMode.TRACK)

    assert list(output_dir.iterdir()) == []


def test_rollback_does_not_delete_a_file_replaced_by_another_process(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _two_track_file(midi_file)
    output_dir = tmp_path / "stems"
    real_write_stem = application.write_stem
    first_output: Path | None = None
    calls = 0

    def replace_then_fail(path: Path, *args: object, **kwargs: object) -> object:
        nonlocal calls, first_output
        calls += 1
        if calls == 1:
            identity = real_write_stem(path, *args, **kwargs)
            first_output = path
            return identity
        assert first_output is not None
        first_output.unlink()
        first_output.write_bytes(b"foreign export")
        raise MidiExportError("simulated later failure")

    monkeypatch.setattr(application, "write_stem", replace_then_fail)

    with pytest.raises(MidiExportError, match="simulated later failure"):
        MidiExportService().export(input_path, output_dir, SplitMode.TRACK)

    assert first_output is not None
    assert first_output.read_bytes() == b"foreign export"


def test_interrupt_immediately_after_writer_returns_still_rolls_back(
    midi_file: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = _two_track_file(midi_file)
    output_dir = tmp_path / "stems"
    real_write_stem = application.write_stem

    def interrupt_after_commit(*args: object, **kwargs: object) -> object:
        real_write_stem(*args, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(application, "write_stem", interrupt_after_commit)

    with pytest.raises(KeyboardInterrupt):
        MidiExportService().export(input_path, output_dir, SplitMode.TRACK)

    assert list(output_dir.iterdir()) == []


def test_successful_batch_exports_reopenable_stems(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    result = MidiExportService().export(
        _two_track_file(midi_file), tmp_path / "stems", SplitMode.TRACK
    )

    assert [stem.path.name for stem in result.stems] == ["01 - Lead.mid", "02 - Bass.mid"]
    assert all(mido.MidiFile(stem.path).tracks for stem in result.stems)


def test_export_reports_each_stem_after_it_is_committed(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    progress: list[object] = []

    result = MidiExportService().export(
        _two_track_file(midi_file),
        tmp_path / "stems",
        SplitMode.TRACK,
        on_stem=progress.append,
    )

    assert progress == list(result.stems)


def test_export_can_select_and_rename_sources(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    input_path = midi_file(
        "song.mid",
        [
            [
                mido.MetaMessage("track_name", name="Piano"),
                mido.Message("note_on", note=60, velocity=100),
            ],
            [
                mido.MetaMessage("track_name", name="Bass"),
                mido.Message("note_on", note=48, velocity=100),
            ],
        ],
    )
    analysis = MidiExportService().analyze(input_path, SplitMode.TRACK)
    selected = analysis.sources[1].id

    result = MidiExportService().export(
        input_path,
        tmp_path / "stems",
        SplitMode.TRACK,
        selected_source_ids={selected},
        name_overrides={selected: "Low Bass"},
    )

    assert [stem.path.name for stem in result.stems] == ["01 - Low Bass.mid"]


def test_export_many_applies_source_selection_per_input(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    input_path = midi_file(
        "song.mid",
        [
            [mido.MetaMessage("track_name", name="Piano"), mido.Message("note_on", note=60, velocity=100)],
            [mido.MetaMessage("track_name", name="Bass"), mido.Message("note_on", note=48, velocity=100)],
        ],
    )
    analysis = MidiExportService().analyze(input_path, SplitMode.TRACK)
    source = analysis.sources[0]
    selection = MidiSourceSelection({source.id}, {source.id: "Main Piano"})

    result = MidiExportService().export_many(
        [input_path],
        tmp_path / "batch",
        SplitMode.TRACK,
        source_selections={input_path.resolve(): selection},
    )

    assert [stem.path.name for stem in result.stems] == ["01 - Main Piano.mid"]


def test_export_many_creates_one_output_folder_per_input(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    first = midi_file(
        "Song 01.mid",
        [[mido.Message("note_on", note=60, velocity=100)]],
    )
    second = midi_file(
        "Song 02.mid",
        [[mido.Message("note_on", note=48, velocity=100)]],
    )
    output_root = tmp_path / "batch-output"

    result = MidiExportService().export_many(
        [first, second], output_root, SplitMode.TRACK
    )

    assert [item.input_path for item in result.items] == [first, second]
    assert all(
        item.output_dir == output_root / f"{item.input_path.stem} - MIDI Stems"
        for item in result.items
    )
    assert all(item.result.stems for item in result.items)


def test_collect_midi_inputs_expands_folders_recursively(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    first = midi_file("top.mid", [[mido.Message("note_on", note=60, velocity=100)]])
    second = nested / "nested.midi"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.Message("note_on", note=48, velocity=100)]))
    midi.save(second)
    (nested / "ignore.txt").write_text("not MIDI", encoding="utf-8")

    assert MidiExportService.collect_midi_inputs([tmp_path]) == tuple(
        sorted((first.resolve(), second.resolve()), key=lambda item: str(item).casefold())
    )


def test_export_many_does_not_reprocess_previous_output(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    source = input_root / "Song.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.Message("note_on", note=60, velocity=100)]))
    midi.save(source)
    output_root = input_root / "Pattern Atlas Batch"

    service = MidiExportService()
    service.export_many([input_root], output_root, SplitMode.TRACK)
    result = service.export_many([input_root], output_root, SplitMode.TRACK)

    assert [item.input_path for item in result.items] == [source.resolve()]


def test_export_many_disambiguates_duplicate_input_names(
    midi_file: Callable[..., Path], tmp_path: Path
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = midi_file("placeholder.mid", [[mido.Message("note_on", note=60, velocity=100)]])
    first.rename(first_dir / "song.mid")
    second = second_dir / "song.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.Message("note_on", note=48, velocity=100)]))
    midi.save(second)

    result = MidiExportService().export_many(
        [first_dir, second_dir], tmp_path / "output", SplitMode.TRACK
    )

    assert [item.output_dir.name for item in result.items] == [
        "song - MIDI Stems",
        "song (2) - MIDI Stems",
    ]
