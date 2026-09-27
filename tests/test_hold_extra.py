from delta_harmonica.models import Point, Profile
from delta_harmonica.player import Player
from delta_harmonica.touch import TouchController


def test_note_hold_adds_extra():
    profile = Profile(
        name="t",
        device_width=100,
        device_height=100,
        keys={"note_1": Point(1, 1)},
    )
    player = Player(profile, TouchController(dry_run=True), hold_extra_ms=80)
    assert player._note_hold_ms(200) == 280
    assert player._note_hold_ms(1) == 81


def test_note_hold_extra_clamped_non_negative():
    profile = Profile(
        name="t",
        device_width=100,
        device_height=100,
        keys={"note_1": Point(1, 1)},
    )
    player = Player(profile, TouchController(dry_run=True), hold_extra_ms=-10)
    assert player.hold_extra_ms == 0
    assert player._note_hold_ms(50) == 50