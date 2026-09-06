# Changelog

All notable changes to Pattern Atlas are documented here.

## [0.3.1] - 2026-09-06

### Added

- Added Smart (Hybrid) splitting: single-channel tracks stay intact while multi-channel tracks split by channel.

### Changed

- Renamed the default interface mode to Smart (Hybrid); the CLI keeps `--mode auto` as a compatibility alias.
- Updated the README interface screenshot to match the current Smart (Hybrid) layout.

## [0.3.0] - 2026-09-06

### Added

- Added a MIDI sources preview with file, source, track, channel, note count, and note range details.
- Added source selection and per-source renaming before export.
- Added an Expand/Collapse control for inspecting the complete source list.

### Changed

- Export now includes only the sources selected in the preview.
- Batch export preserves each input file's source selections and custom names.
- Output numbering follows the selected source order.

### Fixed

- Fixed the Exported files card footer being clipped at the bottom of the window.

### Improved

- Improved source naming and note-range visibility in the interface.
- Added regression coverage for source preview, filtering, renaming, expansion, and layout bounds.
