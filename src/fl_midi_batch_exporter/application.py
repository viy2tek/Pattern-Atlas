"""Application service that composes the MIDI export core."""

from pathlib import Path

from .core.analyzer import analyze_midi
from .core.models import (
    ExportResult,
    ExportedStem,
    MidiExportError,
    MidiProjectAnalysis,
    SplitMode,
)
from .core.naming import reserve_output_path, suggest_stem_name
from .core.reader import read_midi
from .core.splitter import events_for_source
from .core.writer import write_stem


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
    ) -> ExportResult:
        """Export all detected sources, creating *output_dir* when needed."""
        analysis = self.analyze(input_path, mode)
        if analysis.total_notes == 0:
            raise MidiExportError("No MIDI notes were found in this file.")
        output_dir.mkdir(parents=True, exist_ok=True)
        return export_all_stems(analysis, output_dir)


def export_all_stems(analysis: MidiProjectAnalysis, output_dir: Path) -> ExportResult:
    """Write every non-empty source from *analysis* into *output_dir*."""
    stems: list[ExportedStem] = []
    for number, source in enumerate(analysis.sources, start=1):
        events = events_for_source(analysis, source)
        if not events:
            continue
        path = reserve_output_path(output_dir, suggest_stem_name(source, number))
        write_stem(path, analysis, source, events)
        stems.append(ExportedStem(path, source, len(events), source.note_count))
    return ExportResult(tuple(stems), sum(stem.note_count for stem in stems))
