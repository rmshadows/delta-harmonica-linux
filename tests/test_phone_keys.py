from delta_harmonica.models import Modifier, PitchKey, PlayNote
from delta_harmonica.player import Player


def test_hash1_uses_physical_1p():
    note = PlayNote(pitch=PitchKey.N1, duration_ms=100, modifier=Modifier.SHARP, octaves=1)
    mod, ui = Player._phone_keys(note)
    assert mod == Modifier.NATURAL
    assert ui == "note_1p"


def test_double_hash1_uses_sharp_1p():
    note = PlayNote(pitch=PitchKey.N1, duration_ms=100, modifier=Modifier.SHARP, octaves=2)
    mod, ui = Player._phone_keys(note)
    assert mod == Modifier.SHARP
    assert ui == "note_1p"


def test_one_prime_stays_natural_1p():
    note = PlayNote(pitch=PitchKey.N1P, duration_ms=100, modifier=Modifier.NATURAL, octaves=0)
    mod, ui = Player._phone_keys(note)
    assert mod == Modifier.NATURAL
    assert ui == "note_1p"


def test_hash3_still_sharp_note3():
    note = PlayNote(pitch=PitchKey.N3, duration_ms=100, modifier=Modifier.SHARP, octaves=1)
    mod, ui = Player._phone_keys(note)
    assert mod == Modifier.SHARP
    assert ui == "note_3"


def test_semitone_maps_to_semitone_bank():
    note = PlayNote(pitch=PitchKey.N4, duration_ms=100, modifier=Modifier.SEMITONE, octaves=0)
    mod, ui = Player._phone_keys(note)
    assert mod == Modifier.SEMITONE
    assert ui == "note_4"
