"""Command-line entry point for the batch exporter."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .application import MidiExportService
from .core.models import (
    ExportResult,
    MidiBatchResult,
    MidiExportError,
    MidiInspector,
    MidiProjectAnalysis,
    MidiSource,
    SplitMode,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the MIDI stem-export command."""
    parser = argparse.ArgumentParser(description="Export stems from MIDI files.")
    parser.add_argument(
        "input",
        type=Path,
        nargs="+",
        help="MIDI file(s) or folder(s) to export recursively",
    )
    parser.add_argument("-o", "--output", type=Path, help="Directory for exported stems")
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in SplitMode),
        default=SplitMode.SMART.value,
        help="How to split the MIDI file (default: smart)",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Inspect MIDI metadata and sources without exporting files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the human summary",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Export MIDI stems and return a process-compatible exit code."""
    args = build_parser().parse_args(argv)

    try:
        service = MidiExportService()
        inputs = service.collect_midi_inputs(args.input)
        mode = SplitMode(args.mode)
        if args.analyze:
            if args.output is not None:
                raise MidiExportError("--output cannot be used with --analyze.")
            analyses = tuple((path, service.analyze(path, mode)) for path in inputs)
            if args.json:
                print(json.dumps(_analysis_payload(analyses, mode), indent=2, sort_keys=True))
            else:
                print(_format_analysis(analyses))
            return 0

        is_single_file = len(args.input) == 1 and args.input[0].is_file()
        if is_single_file:
            output_dir = args.output or inputs[0].with_name(
                f"{inputs[0].stem} - MIDI Stems"
            )
            result = service.export(inputs[0], output_dir, mode)
        else:
            output_dir = args.output or _default_batch_output(inputs, args.input)
            result = service.export_many(inputs, output_dir, mode)
    except MidiExportError as error:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(_export_json(result, inputs, output_dir, mode))
        return 0

    if is_single_file:
        print(f"{len(result.stems)} MIDI files exported")
    else:
        print(f"{len(result.stems)} MIDI files exported from {len(result.items)} inputs")
    return 0


def _analysis_payload(
    analyses: Sequence[tuple[Path, MidiProjectAnalysis]], mode: SplitMode
) -> dict[str, object]:
    """Build the stable JSON document returned by ``--analyze --json``."""
    return {
        "operation": "analyze",
        "mode": mode.value,
        "inputs": [
            {"path": str(path.resolve()), **_analysis_to_dict(analysis)}
            for path, analysis in analyses
        ],
    }


def _analysis_to_dict(analysis: MidiProjectAnalysis) -> dict[str, object]:
    inspector = analysis.inspector
    if inspector is None:
        raise MidiExportError("MIDI analysis did not include diagnostic metadata.")
    return {
        "inspector": _inspector_to_dict(inspector),
        "sources": [_source_to_dict(source) for source in analysis.sources],
    }


def _inspector_to_dict(inspector: MidiInspector) -> dict[str, object]:
    return {
        "midi_type": inspector.midi_type,
        "track_count": inspector.track_count,
        "musical_track_count": inspector.musical_track_count,
        "channel_count": inspector.channel_count,
        "note_count": inspector.note_count,
        "tempo_bpm": inspector.tempo_bpm,
        "ticks_per_beat": inspector.ticks_per_beat,
        "split_mode": inspector.split_mode.value,
        "split_reason": inspector.split_reason,
    }


def _source_to_dict(source: MidiSource) -> dict[str, object]:
    return {
        "id": source.id,
        "name": source.name,
        "track": source.track_index + 1,
        "channel": source.channel + 1 if source.channel is not None else None,
        "event_count": source.event_count,
        "note_count": source.note_count,
        "range": {
            "lowest": source.lowest_note,
            "highest": source.highest_note,
        },
    }


def _format_analysis(
    analyses: Sequence[tuple[Path, MidiProjectAnalysis]],
) -> str:
    """Format diagnostics for people reading a terminal."""
    sections: list[str] = []
    for path, analysis in analyses:
        inspector = analysis.inspector
        if inspector is None:
            raise MidiExportError("MIDI analysis did not include diagnostic metadata.")
        sections.append(
            "\n".join(
                (
                    f"Input: {path}",
                    f"MIDI Type: {inspector.midi_type}",
                    f"Tracks: {inspector.track_count} ({inspector.musical_track_count} musical)",
                    f"Channels: {inspector.channel_count}",
                    f"Notes: {inspector.note_count}",
                    f"Tempo: {_format_bpm(inspector.tempo_bpm)} BPM",
                    f"Resolution: {inspector.ticks_per_beat} PPQ",
                    f"Sources: {len(analysis.sources)}",
                    f"Split: {_display_mode(inspector.split_mode)} — {inspector.split_reason}",
                )
            )
        )
    return "\n\n".join(sections)


def _export_json(
    result: ExportResult | MidiBatchResult,
    inputs: Sequence[Path],
    output_dir: Path,
    mode: SplitMode,
) -> str:
    """Build the stable JSON document returned after an export."""
    if isinstance(result, ExportResult):
        items = (
            {
                "path": str(inputs[0].resolve()),
                "output_dir": str(output_dir.resolve()),
                "stems": [_stem_to_dict(stem) for stem in result.stems],
            },
        )
    else:
        items = tuple(
            {
                "path": str(item.input_path.resolve()),
                "output_dir": str(item.output_dir.resolve()),
                "stems": [_stem_to_dict(stem) for stem in item.result.stems],
            }
            for item in result.items
        )
    return json.dumps(
        {
            "operation": "export",
            "mode": mode.value,
            "inputs": items,
            "total_stems": len(result.stems),
            "total_notes": result.total_notes,
        },
        indent=2,
        sort_keys=True,
    )


def _stem_to_dict(stem: object) -> dict[str, object]:
    return {
        "path": str(stem.path.resolve()),
        "source_id": stem.source.id,
        "event_count": stem.event_count,
        "note_count": stem.note_count,
    }


def _display_mode(mode: SplitMode) -> str:
    return {
        SplitMode.SMART: "Smart (Hybrid)",
        SplitMode.TRACK: "By track",
        SplitMode.CHANNEL: "By MIDI channel",
        SplitMode.AUTO: "Smart (Hybrid)",
    }[mode]


def _format_bpm(tempo_bpm: float) -> str:
    return str(int(tempo_bpm)) if tempo_bpm.is_integer() else f"{tempo_bpm:.1f}"


def _default_batch_output(inputs: Sequence[Path], requested: Sequence[Path]) -> Path:
    """Choose a predictable batch root when the user omits ``--output``."""
    if len(requested) == 1 and requested[0].is_dir():
        return requested[0] / "Pattern Atlas Batch"
    common_parent = Path(os.path.commonpath([str(path.parent) for path in inputs]))
    return common_parent / "Pattern Atlas Batch"


if __name__ == "__main__":
    raise SystemExit(main())
