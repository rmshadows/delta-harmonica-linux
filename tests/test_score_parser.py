from delta_harmonica.models import LyricMark, Modifier, PitchKey, PlayNote, Rest, SetRegister
from delta_harmonica.score_parser import parse_score_text


def test_parse_basic():
    text = """
title: t
bpm: 120
register: 2

@2 1/4 0/8 #2/4 b3/2 1'/4
"""
    score = parse_score_text(text)
    assert score.title == "t"
    assert score.bpm == 120
    assert abs(score.ms_beat - 500.0) < 1e-6
    assert score.register == 2

    assert isinstance(score.events[0], SetRegister)
    assert score.events[0].register == 2

    notes = [e for e in score.events if isinstance(e, PlayNote)]
    assert notes[0].pitch == PitchKey.N1
    assert notes[0].duration_ms == 500
    assert notes[1].pitch == PitchKey.N2
    assert notes[1].modifier == Modifier.SHARP
    assert notes[2].modifier == Modifier.FLAT
    assert notes[3].pitch == PitchKey.N1P

    rests = [e for e in score.events if isinstance(e, Rest)]
    assert rests[0].duration_ms == 250


def test_ms_beat_override():
    score = parse_score_text("ms_beat: 625\nregister: 1\n1/4\n")
    assert score.ms_beat == 625
    assert abs(score.bpm - 96.0) < 1e-6


def test_lyric_and_dotted_and_barline():
    text = """
title: x
bpm: 80
register: 2

> 忘了有多久
0/8 5/8 1/4. | 5/4
"""
    score = parse_score_text(text)
    assert score.lyrics == ["忘了有多久"]
    assert any(isinstance(e, LyricMark) and e.text == "忘了有多久" for e in score.events)

    # barline does not insert rest
    rests = [e for e in score.events if isinstance(e, Rest)]
    assert len(rests) == 1
    assert rests[0].duration_ms == int(round(60000 / 80 * 0.5))

    notes = [e for e in score.events if isinstance(e, PlayNote)]
    # 1/4. at 80bpm = 1.5 * 750 = 1125
    dotted = [n for n in notes if n.pitch == PitchKey.N1][0]
    assert dotted.duration_ms == 1125


def test_abs_rest_and_rest_scale():
    text = """
title: t
bpm: 120
rest_scale: 2
register: 2

1/4 0:100 2/4
"""
    score = parse_score_text(text)
    assert score.rest_scale == 2.0
    rests = [e for e in score.events if isinstance(e, Rest)]
    assert rests[0].duration_ms == 100
    # player applies scale
    from delta_harmonica.player import format_timeline

    tl = format_timeline(score)
    assert "REST 200ms" in tl


def test_double_sharp_octave():
    """##1 = +2 octaves (再高八度的 #1), not a parse error."""
    score = parse_score_text("bpm: 120\n##1/8 #1'/8\n")
    notes = [e for e in score.events if isinstance(e, PlayNote)]
    assert notes[0].pitch == PitchKey.N1
    assert notes[0].octaves == 2
    assert notes[0].modifier == Modifier.SHARP
    assert notes[1].pitch == PitchKey.N1P
    assert notes[1].octaves == 1


def test_tie_merges_same_pitch():
    """#5/16+#5/8 → one hold of 16th+8th (= dotted 8th at 120bpm: 375ms)."""
    score = parse_score_text("bpm: 120\n#5/16+#5/8\n")
    notes = [e for e in score.events if isinstance(e, PlayNote)]
    assert len(notes) == 1
    assert notes[0].pitch == PitchKey.N5
    assert notes[0].modifier == Modifier.SHARP
    assert notes[0].duration_ms == 375


def test_tie_different_pitch_keeps_two():
    score = parse_score_text("bpm: 120\n5/8+6/8\n")
    notes = [e for e in score.events if isinstance(e, PlayNote)]
    assert len(notes) == 2
    assert notes[0].pitch == PitchKey.N5
    assert notes[1].pitch == PitchKey.N6


def test_tonghua_file_parses():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scores" / "tonghua.txt"
    score = parse_score_text(path.read_text(encoding="utf-8"))
    assert score.bpm == 78
    assert "我愿变成童话里" in score.lyrics
    assert any(isinstance(e, Rest) for e in score.events)
    dbl = [e for e in score.events if isinstance(e, PlayNote) and e.octaves == 2]
    assert dbl, "tonghua should contain ## notes"
    assert all(n.pitch == PitchKey.N1 for n in dbl)
