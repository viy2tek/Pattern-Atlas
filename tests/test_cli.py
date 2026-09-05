from collections.abc import Callable
from pathlib import Path

import mido

from fl_midi_batch_exporter.cli import main


def test_cli_exports_stems_and_reports_count(
    midi_file: Callable[..., Path], tmp_path: Path, capsys
) -> None:
    path = midi_file(
        "song.mid",
        [[mido.Message("note_on", note=60, velocity=100)]],
    )
    output = tmp_path / "output"

    exit_code = main([str(path), "--output", str(output), "--mode", "track"])

    assert exit_code == 0
    assert capsys.readouterr().out == "1 MIDI files exported\n"
    assert len(list(output.glob("*.mid"))) == 1


def test_cli_reports_user_error_without_traceback(tmp_path: Path, capsys) -> None:
    exit_code = main([str(tmp_path / "missing.mid")])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.startswith("Error:")


def test_cli_exports_multiple_files_into_separate_folders(
    midi_file: Callable[..., Path], tmp_path: Path, capsys
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

    exit_code = main(
        [str(first), str(second), "--output", str(output_root), "--mode", "track"]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "2 MIDI files exported from 2 inputs\n"
    assert len(list((output_root / "Song 01 - MIDI Stems").glob("*.mid"))) == 1
    assert len(list((output_root / "Song 02 - MIDI Stems").glob("*.mid"))) == 1
