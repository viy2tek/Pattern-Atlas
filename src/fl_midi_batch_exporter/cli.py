"""Command-line entry point for the batch exporter."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .application import MidiExportService
from .core.models import MidiExportError, SplitMode


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the MIDI stem-export command."""
    parser = argparse.ArgumentParser(description="Export stems from a MIDI file.")
    parser.add_argument("input", type=Path, help="MIDI file to export")
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
    output_dir = args.output or args.input.with_name(f"{args.input.stem} - MIDI Stems")

    try:
        result = MidiExportService().export(args.input, output_dir, SplitMode(args.mode))
    except MidiExportError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print(f"{len(result.stems)} MIDI files exported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
