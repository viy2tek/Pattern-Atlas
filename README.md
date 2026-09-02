# Pattern Atlas

Pattern Atlas is a simple MIDI exporter for turning one MIDI file into organized
stems.

## What it does

- Splits `.mid` and `.midi` files into separate stems
- Detects sources by track or MIDI channel
- Preserves notes, timing, tempo, and MIDI metadata
- Works offline on Windows

## Split modes

- **Automatic** chooses the most useful split for the file: by track when
  multiple musical tracks are present, otherwise by MIDI channel.
- **By track** creates one stem for each track that contains notes.
- **By MIDI channel** creates one stem for each channel (and MIDI port) that
  contains notes.

## Download

Download `Pattern Atlas.exe` from the repository's **Releases** page and open
it. No command line is required.

## How to use

1. Open Pattern Atlas.
2. Select **Browse…** or drop a MIDI file anywhere in the window.
3. Choose an output folder.
4. Click **Export MIDI Stems**.

The exported files appear in the result list and are saved in the selected
folder.

## Example output

```text
01 - Piano.mid
02 - Bass.mid
03 - Pad.mid
```

## Command line (optional)

For scripting or automation, install the project and run:

```powershell
python -m pip install -e .
midi-exporter song.mid -o output
```

## Notes

Pattern Atlas works with Standard MIDI files. It does not open proprietary DAW
project files or render audio.
