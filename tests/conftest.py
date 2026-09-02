from collections.abc import Callable
from pathlib import Path

import mido
import pytest


@pytest.fixture
def midi_file(tmp_path: Path) -> Callable[..., Path]:
    """Create a Standard MIDI File with caller-supplied tracks."""

    def create(
        name: str,
        tracks: list[list[mido.Message | mido.MetaMessage]],
        *,
        midi_type: int = 1,
    ) -> Path:
        path = tmp_path / name
        midi = mido.MidiFile(type=midi_type, ticks_per_beat=480)
        midi.tracks.clear()
        for messages in tracks:
            midi.tracks.append(mido.MidiTrack(messages))
        midi.save(path)
        return path

    return create
