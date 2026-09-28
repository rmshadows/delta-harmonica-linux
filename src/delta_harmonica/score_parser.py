from __future__ import annotations

import re
from pathlib import Path

from delta_harmonica.models import (
    LyricMark,
    Modifier,
    PitchKey,
    PlayNote,
    Rest,
    Score,
    ScoreEvent,
    SetModifier,
    SetRegister,
)

_META_RE = re.compile(
    r"^(title|bpm|ms_beat|register|rest_scale|speed|transpose|press_early|hold_extra)"
    r"\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)

# optional s, one or more # or b, pitch, optional /duration with optional dotted
# ##1 = +2 octaves (再高八度的 #1); bb1 = -2 octaves
_TOKEN_RE = re.compile(
    r"^(?P<semi>s)?"
    r"(?P<acc>#{1,3}|b{1,3})?"
    r"(?P<pitch>0|[1-7]'?)"
    r"(?:/(?P<dur>1|2|4|8|16)\.?(?P<dot>\.)?)?$"
)
_ABS_REST_RE = re.compile(r"^0:(\d+)$")
_ABS_NOTE_RE = re.compile(
    r"^(?P<semi>s)?(?P<acc>#{1,3}|b{1,3})?(?P<pitch>[1-7]'?):(?P<ms>\d+)$"
)

_DUR_BEATS = {
    "1": 4.0,
    "2": 2.0,
    "4": 1.0,
    "8": 0.5,
    "16": 0.25,
}


class ScoreParseError(ValueError):
    pass


def _pitch_key(raw: str) -> PitchKey | None:
    if raw == "0":
        return None
    mapping = {
        "1": PitchKey.N1,
        "2": PitchKey.N2,
        "3": PitchKey.N3,
        "4": PitchKey.N4,
        "5": PitchKey.N5,
        "6": PitchKey.N6,
        "7": PitchKey.N7,
        "1'": PitchKey.N1P,
    }
    if raw not in mapping:
        raise ScoreParseError(f"unknown pitch: {raw!r}")
    return mapping[raw]


def _duration_ms(dur_token: str | None, dotted: bool, ms_beat: float) -> int:
    key = dur_token or "4"
    if key not in _DUR_BEATS:
        raise ScoreParseError(f"bad duration /{key}")
    beats = _DUR_BEATS[key]
    if dotted:
        beats *= 1.5
    return max(1, int(round(ms_beat * beats)))


def _octaves(acc: str | None) -> int:
    if not acc:
        return 0
    if acc[0] == "#":
        return len(acc)
    if acc[0] == "b":
        return -len(acc)
    return 0


def _modifier(semi: str | None, acc: str | None) -> Modifier:
    """UI modifier key: 半音 / 升调 / 降调 / 自然音."""
    if semi:
        return Modifier.SEMITONE
    n = _octaves(acc)
    if n > 0:
        return Modifier.SHARP
    if n < 0:
        return Modifier.FLAT
    return Modifier.NATURAL


def _append_play(
    events: list[ScoreEvent],
    *,
    pitch: PitchKey,
    duration_ms: int,
    modifier: Modifier,
    octaves: int,
    tied: bool,
) -> None:
    """Emit a note; if ``tied`` and same as previous note, extend hold (连音线)."""
    if tied and events and isinstance(events[-1], PlayNote):
        prev = events[-1]
        if (
            prev.pitch == pitch
            and prev.modifier == modifier
            and prev.octaves == octaves
        ):
            events[-1] = PlayNote(
                pitch=prev.pitch,
                duration_ms=prev.duration_ms + duration_ms,
                modifier=prev.modifier,
                octaves=prev.octaves,
            )
            return
    events.append(SetModifier(modifier))
    events.append(
        PlayNote(
            pitch=pitch,
            duration_ms=duration_ms,
            modifier=modifier,
            octaves=octaves,
        )
    )


def _append_rest(
    events: list[ScoreEvent], *, duration_ms: int, tied: bool
) -> None:
    if tied and events and isinstance(events[-1], Rest):
        prev = events[-1]
        events[-1] = Rest(duration_ms=prev.duration_ms + duration_ms)
        return
    events.append(Rest(duration_ms=duration_ms))


def _parse_atomic_token(
    tok: str, ms_beat: float, events: list[ScoreEvent], *, tied: bool
) -> None:
    """Parse one note/rest token (no ``+`` inside)."""
    if tok in ("-", "0"):
        _append_rest(
            events, duration_ms=_duration_ms("4", False, ms_beat), tied=tied
        )
        return

    if re.fullmatch(r"@[123]", tok):
        if tied:
            raise ScoreParseError(f"cannot tie register token: {tok!r}")
        reg = int(tok[1])
        if (
            events
            and isinstance(events[-1], SetRegister)
            and events[-1].register == reg
        ):
            return
        events.append(SetRegister(reg))
        return

    abs_rest = _ABS_REST_RE.fullmatch(tok)
    if abs_rest:
        _append_rest(
            events, duration_ms=max(1, int(abs_rest.group(1))), tied=tied
        )
        return

    abs_note = _ABS_NOTE_RE.fullmatch(tok)
    if abs_note:
        pitch = _pitch_key(abs_note.group("pitch"))
        assert pitch is not None
        mod = _modifier(abs_note.group("semi"), abs_note.group("acc"))
        octaves = 0 if abs_note.group("semi") else _octaves(abs_note.group("acc"))
        _append_play(
            events,
            pitch=pitch,
            duration_ms=max(1, int(abs_note.group("ms"))),
            modifier=mod,
            octaves=octaves,
            tied=tied,
        )
        return

    if tok.startswith("-") and tok != "-":
        m = re.fullmatch(r"-/(?P<dur>1|2|4|8|16)\.?", tok)
        if not m:
            raise ScoreParseError(f"bad rest token: {tok!r}")
        dotted = tok.endswith(".")
        _append_rest(
            events,
            duration_ms=_duration_ms(m.group("dur"), dotted, ms_beat),
            tied=tied,
        )
        return

    dotted = False
    token_for_re = tok
    if re.search(r"/(1|2|4|8|16)\.$", tok):
        dotted = True
        token_for_re = tok[:-1]

    m = _TOKEN_RE.fullmatch(token_for_re)
    if not m:
        raise ScoreParseError(f"bad token: {tok!r}")

    pitch_raw = m.group("pitch")
    dur = m.group("dur")
    if m.group("dot"):
        dotted = True
    duration_ms = _duration_ms(dur, dotted, ms_beat)

    if pitch_raw == "0":
        _append_rest(events, duration_ms=duration_ms, tied=tied)
        return

    pitch = _pitch_key(pitch_raw)
    assert pitch is not None
    mod = _modifier(m.group("semi"), m.group("acc"))
    octaves = 0 if m.group("semi") else _octaves(m.group("acc"))
    _append_play(
        events,
        pitch=pitch,
        duration_ms=duration_ms,
        modifier=mod,
        octaves=octaves,
        tied=tied,
    )


def parse_score_text(text: str, *, source: str | None = None) -> Score:
    title = "untitled"
    bpm: float | None = None
    ms_beat: float | None = None
    register = 2
    rest_scale = 1.0
    speed: float | None = None
    transpose: int | None = None
    press_early: int | None = None
    hold_extra: int | None = None
    body_tokens: list[str] = []
    lyrics: list[str] = []

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        # Lyric / phrase marker: "> 忘了有多久"
        if line.startswith(">") and not line.startswith(">>"):
            lyric = line[1:].strip()
            if lyric:
                lyrics.append(lyric)
                body_tokens.append(f"__LYRIC__{lyric}")
            continue
        # Full-line comments: "# comment" — but NOT octave-up notes like "#1/4"
        if re.match(r"^#(\s|$)", line):
            continue

        meta = _META_RE.match(line)
        if meta and not body_tokens:
            key = meta.group(1).lower()
            val = meta.group(2).strip()
            try:
                if key == "title":
                    title = val
                elif key == "bpm":
                    bpm = float(val)
                elif key == "ms_beat":
                    ms_beat = float(val)
                elif key == "register":
                    register = int(val)
                    if register not in (1, 2, 3):
                        raise ScoreParseError("register must be 1..3")
                elif key == "rest_scale":
                    rest_scale = float(val)
                    if rest_scale <= 0:
                        raise ScoreParseError("rest_scale must be positive")
                elif key == "speed":
                    speed = max(0.25, min(3.0, float(val)))
                elif key == "transpose":
                    transpose = max(-24, min(24, int(val)))
                elif key == "press_early":
                    press_early = max(0, int(val))
                elif key == "hold_extra":
                    hold_extra = max(0, int(val))
            except ScoreParseError:
                raise
            except ValueError as exc:
                raise ScoreParseError(
                    f"line {lineno}: invalid {key}: {val!r}"
                ) from exc
            continue

        # Inline comments require "# " (hash + space), so "#2/4" stays 升调
        line = re.sub(r"\s+#\s.*$", "", line).strip()
        if not line:
            continue

        # Normalize tie: "5/16 + 5/8" → "5/16+5/8"
        line = re.sub(r"\s*\+\s*", "+", line)

        for tok in line.split():
            if tok == "|":
                # True barline — visual only (rests must be written as 0)
                continue
            body_tokens.append(tok)

    if ms_beat is None:
        if bpm is None:
            bpm = 96.0
        if bpm <= 0:
            raise ScoreParseError("bpm must be positive")
        ms_beat = 60000.0 / bpm
    else:
        if ms_beat <= 0:
            raise ScoreParseError("ms_beat must be positive")
        if bpm is None:
            bpm = 60000.0 / ms_beat

    events: list[ScoreEvent] = []
    events.append(SetRegister(register))

    for tok in body_tokens:
        if tok.startswith("__LYRIC__"):
            events.append(LyricMark(text=tok[len("__LYRIC__") :]))
            continue

        # 连音线：#5/16+#5/8 → 同音合并时值；异音则依次发出（圆滑）
        parts = tok.split("+")
        if any(not p for p in parts):
            raise ScoreParseError(f"bad tie token: {tok!r}")
        for i, part in enumerate(parts):
            _parse_atomic_token(part, ms_beat, events, tied=(i > 0))

    return Score(
        title=title,
        bpm=bpm,
        ms_beat=ms_beat,
        register=register,
        events=events,
        source=source,
        lyrics=lyrics,
        rest_scale=rest_scale,
        speed=speed,
        transpose=transpose,
        press_early=press_early,
        hold_extra=hold_extra,
    )


def parse_score_file(path: Path) -> Score:
    text = path.read_text(encoding="utf-8")
    return parse_score_text(text, source=str(path))


_PLAYBACK_META_ORDER = ("speed", "transpose", "press_early", "hold_extra")
_PLAYBACK_LINE = {
    "speed": re.compile(r"(?m)^(speed\s*:\s*)[^\n#]+(.*)$"),
    "transpose": re.compile(r"(?m)^(transpose\s*:\s*)[^\n#]+(.*)$"),
    "press_early": re.compile(r"(?m)^(press_early\s*:\s*)[^\n#]+(.*)$"),
    "hold_extra": re.compile(r"(?m)^(hold_extra\s*:\s*)[^\n#]+(.*)$"),
}


def update_score_playback(
    path: Path,
    *,
    speed: float | None = None,
    transpose: int | None = None,
    press_early: int | None = None,
    hold_extra: int | None = None,
) -> Path:
    """Write playback prefs into the score ``.txt`` (not dharm.toml)."""
    values: dict[str, str] = {}
    if speed is not None:
        values["speed"] = f"{max(0.25, min(3.0, float(speed))):.2f}"
    if transpose is not None:
        values["transpose"] = str(max(-24, min(24, int(transpose))))
    if press_early is not None:
        values["press_early"] = str(max(0, int(press_early)))
    if hold_extra is not None:
        values["hold_extra"] = str(max(0, int(hold_extra)))
    if not values:
        return path

    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines_to_append: list[str] = []
    for key in _PLAYBACK_META_ORDER:
        if key not in values:
            continue
        pat = _PLAYBACK_LINE[key]
        if pat.search(text):
            text = pat.sub(rf"\g<1>{values[key]}\2", text, count=1)
        else:
            lines_to_append.append(f"{key}: {values[key]}")

    if lines_to_append:
        # Insert after header comments / title / bpm. "#3/4" is a note, not a comment.
        insert_at = 0
        raw_lines = text.splitlines(keepends=True)
        if not raw_lines:
            text = "\n".join(lines_to_append) + "\n"
        else:
            for i, ln in enumerate(raw_lines):
                s = ln.strip()
                if not s or re.match(r"^#(\s|$)", s) or _META_RE.match(s):
                    insert_at = i + 1
                    continue
                break
            block = "".join(f"{x}\n" for x in lines_to_append)
            raw_lines.insert(insert_at, block)
            text = "".join(raw_lines)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
