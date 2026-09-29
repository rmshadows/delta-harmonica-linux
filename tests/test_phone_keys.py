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


def test_clear_semitone_retaps_semitone_not_natural():
    """半音是开关：取消时必须再点半音，不能点自然音。"""
    from unittest.mock import MagicMock

    from delta_harmonica.models import Point, Profile

    keys = {
        "semitone": Point(10, 10),
        "sharp": Point(20, 10),
        "natural": Point(30, 10),
        "flat": Point(40, 10),
        "note_1": Point(10, 20),
        "note_2": Point(20, 20),
        "note_3": Point(30, 20),
        "note_4": Point(40, 20),
        "note_5": Point(50, 20),
        "note_6": Point(60, 20),
        "note_7": Point(70, 20),
        "note_1p": Point(80, 20),
    }
    prof = Profile(name="t", device_width=100, device_height=100, keys=keys)
    touch = MagicMock()
    player = Player(prof, touch)
    player.current_modifier = Modifier.SEMITONE
    tapped: list[str] = []

    def capture_tap(key: str, hold_ms: int = 50) -> None:
        tapped.append(key)

    player._tap_ui = capture_tap  # type: ignore[method-assign]
    player._clear_semitone()
    assert tapped == ["semitone"]
    assert player.current_modifier == Modifier.NATURAL


def test_leave_semitone_for_sharp_retaps_semitone_first():
    from unittest.mock import MagicMock

    from delta_harmonica.models import Point, Profile

    keys = {
        "semitone": Point(10, 10),
        "sharp": Point(20, 10),
        "natural": Point(30, 10),
        "flat": Point(40, 10),
        "note_1": Point(10, 20),
        "note_2": Point(20, 20),
        "note_3": Point(30, 20),
        "note_4": Point(40, 20),
        "note_5": Point(50, 20),
        "note_6": Point(60, 20),
        "note_7": Point(70, 20),
        "note_1p": Point(80, 20),
    }
    prof = Profile(name="t", device_width=100, device_height=100, keys=keys)
    touch = MagicMock()
    player = Player(prof, touch)
    player.current_modifier = Modifier.SEMITONE
    tapped: list[str] = []
    player._tap_ui = lambda key, hold_ms=50: tapped.append(key)  # type: ignore[method-assign]
    player._ensure_modifier(Modifier.SHARP)
    assert tapped == ["semitone", "sharp"]
    assert player.current_modifier == Modifier.SHARP
