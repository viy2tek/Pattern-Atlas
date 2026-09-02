from collections.abc import Callable
from pathlib import Path

import mido
import pytest

from fl_midi_batch_exporter import application
from fl_midi_batch_exporter.application import MidiExportService
from fl_midi_batch_exporter.core.models import MidiExportError, SplitMode


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
