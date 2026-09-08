import json
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


def test_cli_analyze_reports_diagnostics_without_writing_files(
    midi_file: Callable[..., Path], tmp_path: Path, capsys
) -> None:
    path = midi_file(
        "inspect.mid",
        [
            [mido.MetaMessage("set_tempo", tempo=600_000)],
            [
                mido.MetaMessage("track_name", name="Lead"),
                mido.Message("note_on", channel=0, note=60, velocity=100),
            ],
        ],
    )

    exit_code = main([str(path), "--analyze"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "MIDI Type: 1" in output
    assert "Tracks: 2 (1 musical)" in output
    assert "Channels: 1" in output
    assert "Notes: 1" in output
    assert "Tempo: 100 BPM" in output
    assert "Resolution: 480 PPQ" in output
    assert "Split: Smart (Hybrid)" in output
    assert not (tmp_path / "inspect - MIDI Stems").exists()


def test_cli_analyze_json_is_machine_readable(midi_file: Callable[..., Path], capsys) -> None:
    path = midi_file(
        "inspect-json.mid",
        [[mido.MetaMessage("track_name", name="Lead"), mido.Message("note_on", note=60)]],
    )

    exit_code = main([str(path), "--analyze", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "analyze"
    assert payload["mode"] == "smart"
    assert payload["inputs"][0]["path"] == str(path.resolve())
    assert payload["inputs"][0]["inspector"]["midi_type"] == 1
    assert payload["inputs"][0]["inspector"]["note_count"] == 1
    assert payload["inputs"][0]["sources"][0]["name"] == "Lead"


def test_cli_json_export_reports_outputs(midi_file: Callable[..., Path], tmp_path: Path, capsys) -> None:
    path = midi_file("export-json.mid", [[mido.Message("note_on", note=60)]])
    output = tmp_path / "output"

    exit_code = main([str(path), "--output", str(output), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "export"
    assert payload["total_stems"] == 1
    assert payload["inputs"][0]["output_dir"] == str(output.resolve())
    assert Path(payload["inputs"][0]["stems"][0]["path"]).exists()


def test_cli_json_errors_are_machine_readable(tmp_path: Path, capsys) -> None:
    exit_code = main([str(tmp_path / "missing.mid"), "--json"])

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "error": "Input path does not exist: '" + str(tmp_path / "missing.mid") + "'."
    }
