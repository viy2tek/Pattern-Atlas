"""Command-line entry point for the batch exporter."""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .application import MidiExportService
from .core.models import MidiExportError, SplitMode


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
        default=SplitMode.AUTO.value,
        help="How to split the MIDI file (default: auto)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Export MIDI stems and return a process-compatible exit code."""
    args = build_parser().parse_args(argv)

    try:
        service = MidiExportService()
        inputs = service.collect_midi_inputs(args.input)
        mode = SplitMode(args.mode)
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
        print(f"Error: {error}", file=sys.stderr)
        return 2

    if is_single_file:
        print(f"{len(result.stems)} MIDI files exported")
    else:
        print(f"{len(result.stems)} MIDI files exported from {len(result.items)} inputs")
    return 0


def _default_batch_output(inputs: Sequence[Path], requested: Sequence[Path]) -> Path:
    """Choose a predictable batch root when the user omits ``--output``."""
    if len(requested) == 1 and requested[0].is_dir():
        return requested[0] / "Pattern Atlas Batch"
    common_parent = Path(os.path.commonpath([str(path.parent) for path in inputs]))
    return common_parent / "Pattern Atlas Batch"


if __name__ == "__main__":
    raise SystemExit(main())
