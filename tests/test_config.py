from pathlib import Path

from delta_harmonica.config import load_config


def test_load_missing_returns_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.profile is None
    assert cfg.hold_extra == 0
    assert cfg.countdown == 3


def test_load_hold_extra_and_profile(tmp_path: Path):
    p = tmp_path / "dharm.toml"
    p.write_text(
        'profile = "z60u"\nhold_extra = 120\npress_early = 80\ncountdown = 1\nspeed = 0.8\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.profile == "z60u"
    assert cfg.hold_extra == 120
    assert cfg.press_early == 80
    assert cfg.countdown == 1
    assert cfg.speed == 0.8
    assert cfg.path == p


def test_hold_extra_clamped(tmp_path: Path):
    p = tmp_path / "dharm.toml"
    p.write_text("hold_extra = -5\npress_early = -3\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.hold_extra == 0
    assert cfg.press_early == 0
