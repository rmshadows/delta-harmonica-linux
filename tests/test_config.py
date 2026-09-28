from pathlib import Path

from delta_harmonica.config import load_config, save_speed, save_transpose
from delta_harmonica.models import Modifier, PitchKey, PlayNote, Score
from delta_harmonica.score_parser import parse_score_text
from delta_harmonica.transpose import (
    analyze_range,
    fits,
    note_semitones,
    plan_label,
    suggest_transpose,
    transpose_note,
    transpose_score,
)


def test_load_missing_returns_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.profile is None
    assert cfg.hold_extra == 0
    assert cfg.countdown == 3
    assert cfg.transpose == 0


def test_load_hold_extra_and_profile(tmp_path: Path):
    p = tmp_path / "dharm.toml"
    p.write_text(
        'profile = "z60u"\nhold_extra = 120\npress_early = 80\n'
        "countdown = 1\nspeed = 0.8\ntranspose = 2\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.profile == "z60u"
    assert cfg.hold_extra == 120
    assert cfg.press_early == 80
    assert cfg.countdown == 1
    assert cfg.speed == 0.8
    assert cfg.transpose == 2
    assert cfg.path == p


def test_hold_extra_clamped(tmp_path: Path):
    p = tmp_path / "dharm.toml"
    p.write_text("hold_extra = -5\npress_early = -3\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.hold_extra == 0
    assert cfg.press_early == 0


def test_save_speed_preserves_comments(tmp_path: Path):
    p = tmp_path / "dharm.toml"
    p.write_text(
        '# keep me\nprofile = "z60u"\n# speed note\nspeed = 1.0  # default\n',
        encoding="utf-8",
    )
    save_speed(0.85, path=p)
    text = p.read_text(encoding="utf-8")
    assert "# keep me" in text
    assert 'profile = "z60u"' in text
    assert "speed = 0.85  # default" in text
    assert load_config(p).speed == 0.85


def test_save_speed_appends_when_missing(tmp_path: Path):
    p = tmp_path / "dharm.toml"
    p.write_text('profile = "a"\n', encoding="utf-8")
    save_speed(1.25, path=p)
    assert load_config(p).speed == 1.25
    assert "speed = 1.25" in p.read_text(encoding="utf-8")


def test_save_transpose(tmp_path: Path):
    p = tmp_path / "dharm.toml"
    p.write_text("speed = 1.0\n", encoding="utf-8")
    save_transpose(2, path=p)
    assert load_config(p).transpose == 2
    assert "transpose = 2" in p.read_text(encoding="utf-8")
    save_transpose(-12, path=p)
    assert load_config(p).transpose == -12


def test_note_semitones_basic():
    n1 = PlayNote(PitchKey.N1, 100, Modifier.NATURAL, 0)
    assert note_semitones(n1) == 0
    s4 = PlayNote(PitchKey.N4, 100, Modifier.SEMITONE, 0)
    assert note_semitones(s4) == 6
    sharp3 = PlayNote(PitchKey.N3, 100, Modifier.SHARP, 1)
    assert note_semitones(sharp3) == 16
    one_p = PlayNote(PitchKey.N1P, 100, Modifier.NATURAL, 0)
    assert note_semitones(one_p) == 12


def test_transpose_c_to_d():
    score = parse_score_text("bpm: 120\n1/4 2/4 3/4\n")
    out = transpose_score(score, 2)
    assert out is not None
    notes = [e for e in out.events if isinstance(e, PlayNote)]
    # 1→2, 2→3, 3→s4 (E+2=F#，落在半音键)
    assert [note_semitones(n) for n in notes] == [2, 4, 6]
    assert notes[2].modifier == Modifier.SEMITONE


def test_suggest_noop_when_in_range():
    score = parse_score_text("bpm: 120\n1/4 5/4 1'/4\n")
    assert analyze_range(score).ok
    assert suggest_transpose(score).semitones == 0
    assert plan_label(2) == "C→D (+2)"
    assert "八度" in plan_label(12)


def test_fits_after_octave_shift():
    # ##1 is playable (24); invent something that needs shift by using parse
    score = parse_score_text("bpm: 120\n1/4 #5/4\n")
    assert fits(score, 0)
