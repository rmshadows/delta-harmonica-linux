from delta_harmonica.models import Point, Profile
from delta_harmonica.player import Player
from delta_harmonica.touch import TouchController


def _player(**kwargs) -> Player:
    profile = Profile(
        name="t",
        device_width=100,
        device_height=100,
        keys={"note_1": Point(1, 1)},
    )
    return Player(profile, TouchController(dry_run=True), **kwargs)


def test_note_hold_adds_extra():
    player = _player(hold_extra_ms=80)
    assert player._note_hold_ms(200) == 280
    assert player._note_hold_ms(1) == 81


def test_note_hold_extra_clamped_non_negative():
    player = _player(hold_extra_ms=-10)
    assert player.hold_extra_ms == 0
    assert player._note_hold_ms(50) == 50


def test_press_early_shortens_onset_gap():
    player = _player(hold_extra_ms=0, press_early_ms=100)
    assert player._onset_gap_ms(500) == 400


def test_hold_extra_and_press_early_net_gap():
    # gap = duration + hold_extra - press_early
    player = _player(hold_extra_ms=200, press_early_ms=120)
    assert player._note_hold_ms(500) == 700
    assert player._onset_gap_ms(500) == 580
