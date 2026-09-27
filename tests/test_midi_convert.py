from pathlib import Path

import mido

from delta_harmonica.midi_convert import convert_midi, midi_to_token


def test_midi_to_token_natural():
    tok, warns = midi_to_token(60, midi_root=60)  # type: ignore[misc]
    assert tok == "1"
    assert warns == []


def test_midi_to_token_semitone():
    tok, _ = midi_to_token(61, midi_root=60)  # type: ignore[misc]
    assert tok == "s1"


def test_midi_to_token_octave_up():
    tok, _ = midi_to_token(72, midi_root=60)  # type: ignore[misc]
    # 同排高音 1' 优先于 #1
    assert tok == "1'"


def test_convert_simple_mid(tmp_path: Path):
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    track.append(mido.Message("note_on", note=60, velocity=64, time=0))
    track.append(mido.Message("note_off", note=60, velocity=0, time=480))
    track.append(mido.Message("note_on", note=62, velocity=64, time=0))
    track.append(mido.Message("note_off", note=62, velocity=0, time=480))
    path = tmp_path / "t.mid"
    mid.save(path)

    result = convert_midi(path, bpm=120, midi_root=60)
    assert "title: t" in result.text
    assert "@1" not in result.text
    assert "register:" not in result.text
    assert "1/" in result.text
    assert "2/" in result.text
