"""Application service that composes the MIDI export core."""

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from .core.analyzer import analyze_midi
from .core.models import (
    ExportedStem,
    ExportResult,
    MidiBatchItem,
    MidiBatchResult,
    MidiExportError,
    MidiProjectAnalysis,
    MidiSourceSelection,
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
        selected_source_ids: Iterable[str] | None = None,
        name_overrides: Mapping[str, str] | None = None,
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
        return export_all_stems(
            analysis,
            output_dir,
            on_stem=on_stem,
            selected_source_ids=selected_source_ids,
            name_overrides=name_overrides,
        )

    @staticmethod
    def collect_midi_inputs(
        inputs: Iterable[Path], excluded_root: Path | None = None
    ) -> tuple[Path, ...]:
        """Expand files and folders into a sorted, de-duplicated MIDI list."""
        paths: dict[Path, Path] = {}
        excluded = excluded_root.resolve() if excluded_root is not None else None
        for raw_path in inputs:
            path = Path(raw_path)
            if path.is_file():
                if path.suffix.lower() in {".mid", ".midi"}:
                    resolved = path.resolve()
                    paths[resolved] = resolved
                continue
            if path.is_dir():
                for candidate in path.rglob("*"):
                    if excluded is not None and candidate.resolve().is_relative_to(excluded):
                        continue
                    if candidate.is_file() and candidate.suffix.lower() in {
                        ".mid",
                        ".midi",
                    }:
                        resolved = candidate.resolve()
                        paths[resolved] = resolved
                continue
            raise MidiExportError(f"Input path does not exist: '{path}'.")

        if not paths:
            raise MidiExportError("No MIDI files were found in the selected input.")
        return tuple(sorted(paths.values(), key=lambda item: str(item).casefold()))

    def export_many(
        self,
        inputs: Iterable[Path],
        output_root: Path,
        mode: SplitMode = SplitMode.AUTO,
        on_stem: Callable[[ExportedStem], None] | None = None,
        on_file: Callable[[MidiBatchItem], None] | None = None,
        source_selections: Mapping[Path, MidiSourceSelection] | None = None,
    ) -> MidiBatchResult:
        """Export each MIDI input into its own folder below *output_root*."""
        try:
            output_root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise MidiExportError(
                f"Could not create the output folder '{output_root}'. "
                "Choose a writable folder and try again."
            ) from error
        paths = self.collect_midi_inputs(inputs, excluded_root=output_root)

        items: list[MidiBatchItem] = []
        used_output_dirs: set[Path] = set()
        for input_path in paths:
            output_dir = output_root / f"{input_path.stem} - MIDI Stems"
            suffix = 2
            while output_dir in used_output_dirs:
                output_dir = output_root / (
                    f"{input_path.stem} ({suffix}) - MIDI Stems"
                )
                suffix += 1
            used_output_dirs.add(output_dir)
            selection = (source_selections or {}).get(input_path)
            result = self.export(
                input_path,
                output_dir,
                mode,
                on_stem=on_stem,
                selected_source_ids=selection.source_ids if selection else None,
                name_overrides=selection.name_overrides if selection else None,
            )
            item = MidiBatchItem(input_path, output_dir, result)
            items.append(item)
            if on_file is not None:
                on_file(item)
        return MidiBatchResult(tuple(items))


def export_all_stems(
    analysis: MidiProjectAnalysis,
    output_dir: Path,
    on_stem: Callable[[ExportedStem], None] | None = None,
    selected_source_ids: Iterable[str] | None = None,
    name_overrides: Mapping[str, str] | None = None,
) -> ExportResult:
    """Write every non-empty source from *analysis* into *output_dir*."""
    stems: list[ExportedStem] = []
    selected = frozenset(selected_source_ids) if selected_source_ids is not None else None
    overrides = name_overrides or {}
    owned_outputs: list[tuple[Path, OutputFileIdentity]] = []
    try:
        for number, source in enumerate(analysis.sources, start=1):
            if selected is not None and source.id not in selected:
                continue
            events = events_for_source(analysis, source)
            if not events:
                continue
            path = reserve_output_path(
                output_dir,
                suggest_stem_name(source, len(stems) + 1, overrides.get(source.id)),
            )
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
