"""Unit tests for Player hotkey helpers (no real TTY / adb)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from delta_harmonica.models import Point, Profile
from delta_harmonica.player import Player
from delta_harmonica.score_parser import parse_score_file


def _player(tmp_path: Path) -> Player:
    score = tmp_path / "song.txt"
    score.write_text("title: t\nbpm: 120\n1/4\n", encoding="utf-8")
    prof = Profile(
        name="t",
        device_width=100,
        device_height=100,
        keys={
            "semitone": Point(1, 1),
            "sharp": Point(2, 1),
            "natural": Point(3, 1),
            "flat": Point(4, 1),
            "note_1": Point(1, 2),
            "note_2": Point(2, 2),
            "note_3": Point(3, 2),
            "note_4": Point(4, 2),
            "note_5": Point(5, 2),
            "note_6": Point(6, 2),
            "note_7": Point(7, 2),
            "note_1p": Point(8, 2),
        },
    )
    touch = MagicMock()
    return Player(prof, touch, score_path=score, speed=1.0, transpose=0)


def test_nudge_speed_does_not_auto_write(tmp_path: Path):
    p = _player(tmp_path)
    p._nudge_speed(-0.1, "test")
    text = p.score_path.read_text(encoding="utf-8")
    assert "speed:" not in text
    assert p.speed == 0.9


def test_s_persists_speed_to_score(tmp_path: Path):
    p = _player(tmp_path)
    p._nudge_speed(-0.1, "test")
    p._persist_score(reason="key")
    text = p.score_path.read_text(encoding="utf-8")
    assert "speed: 0.90" in text
    again = parse_score_file(p.score_path)
    assert again.speed == 0.9


def test_apply_arrow_does_not_auto_write(tmp_path: Path):
    p = _player(tmp_path)
    p._apply_arrow("right")  # C→D = +2
    text = p.score_path.read_text(encoding="utf-8")
    assert "transpose:" not in text
    assert p.transpose == 2
    p._persist_score(reason="key")
    assert "transpose: 2" in p.score_path.read_text(encoding="utf-8")


def test_read_arrow_csi(monkeypatch):
    import io
    import sys

    buf = io.StringIO("[A")
    monkeypatch.setattr(sys, "stdin", buf)

    # select must say data is ready
    import select as select_mod

    monkeypatch.setattr(
        select_mod, "select", lambda *a, **k: ([sys.stdin], [], [])
    )
    assert Player._read_arrow() == "up"


def test_read_arrow_ss3(monkeypatch):
    import io
    import sys
    import select as select_mod

    buf = io.StringIO("OC")
    monkeypatch.setattr(sys, "stdin", buf)
    monkeypatch.setattr(
        select_mod, "select", lambda *a, **k: ([sys.stdin], [], [])
    )
    assert Player._read_arrow() == "right"


def test_pause_toggle_and_sleep(tmp_path: Path):
    p = _player(tmp_path)
    assert p._paused is False
    p._paused = True
    # stop should unblock wait
    def unpause():
        import time as _t

        _t.sleep(0.08)
        p._paused = False

    import threading

    threading.Thread(target=unpause, daemon=True).start()
    t0 = __import__("time").monotonic()
    p._wait_while_paused()
    assert __import__("time").monotonic() - t0 >= 0.05
    assert p._paused is False
