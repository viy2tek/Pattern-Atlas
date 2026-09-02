"""Application service that composes the MIDI export core."""

from collections.abc import Callable
from pathlib import Path

from .core.analyzer import analyze_midi
from .core.models import (
    ExportedStem,
    ExportResult,
    MidiExportError,
    MidiProjectAnalysis,
    SplitMode,
)
from .core.naming import reserve_output_path, suggest_stem_name
from .core.reader import read_midi
from .core.splitter import events_for_source
from .core.writer import OutputFileIdentity, remove_file_if_owned, write_stem


class MidiExportService:
    """Analyze MIDI files and export each detected source as a stem."""

    def analyze(
        self, input_path: Path, mode: SplitMode = SplitMode.AUTO
    ) -> MidiProjectAnalysis:
        """Read and classify the MIDI file at *input_path*."""
        return analyze_midi(read_midi(input_path), mode)

    def export(
        self,
        input_path: Path,
        output_dir: Path,
        mode: SplitMode = SplitMode.AUTO,
        on_stem: Callable[[ExportedStem], None] | None = None,
    ) -> ExportResult:
        """Export all detected sources, creating *output_dir* when needed."""
        analysis = self.analyze(input_path, mode)
        if analysis.total_notes == 0:
            raise MidiExportError("No MIDI notes were found in this file.")
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise MidiExportError(
                f"Could not create the output folder '{output_dir}'. "
                "Choose a writable folder and try again."
            ) from error
        return export_all_stems(analysis, output_dir, on_stem=on_stem)


def export_all_stems(
    analysis: MidiProjectAnalysis,
    output_dir: Path,
    on_stem: Callable[[ExportedStem], None] | None = None,
) -> ExportResult:
    """Write every non-empty source from *analysis* into *output_dir*."""
    stems: list[ExportedStem] = []
    owned_outputs: list[tuple[Path, OutputFileIdentity]] = []
    try:
        for number, source in enumerate(analysis.sources, start=1):
            events = events_for_source(analysis, source)
            if not events:
                continue
            path = reserve_output_path(output_dir, suggest_stem_name(source, number))
            write_stem(
                path,
                analysis,
                source,
                events,
                on_commit=lambda identity, path=path: owned_outputs.append(
                    (path, identity)
                ),
            )
            stem = ExportedStem(path, source, len(events), source.note_count)
            stems.append(stem)
            if on_stem is not None:
                on_stem(stem)
    except BaseException:
        for path, identity in owned_outputs:
            remove_file_if_owned(path, identity)
        raise
    return ExportResult(tuple(stems), sum(stem.note_count for stem in stems))
