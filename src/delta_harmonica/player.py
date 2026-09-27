from __future__ import annotations

import sys
import time

from delta_harmonica.models import (
    MODIFIER_TO_UI,
    PITCH_TO_UI,
    LyricMark,
    Modifier,
    PitchKey,
    PlayNote,
    Profile,
    Rest,
    Score,
    SetModifier,
    SetRegister,
)
from delta_harmonica.touch import TouchController


class Player:
    """Drive harmonica UI from a parsed score using a calibrated profile."""

    def __init__(
        self,
        profile: Profile,
        touch: TouchController,
        *,
        modifier_tap_ms: int = 60,
        hold_extra_ms: int = 0,
        assume_modifier: Modifier = Modifier.NATURAL,
        display_width: int | None = None,
        display_height: int | None = None,
    ) -> None:
        self.profile = profile
        self.touch = touch
        self.modifier_tap_ms = modifier_tap_ms
        # Game needs a short press before the harmonica sounds; add to each note.
        self.hold_extra_ms = max(0, int(hold_extra_ms))
        self.current_modifier = assume_modifier
        # Current phone display size (adb touch space). Window size unused.
        self.display_width = display_width or profile.device_width
        self.display_height = display_height or profile.device_height

    def _note_hold_ms(self, duration_ms: int) -> int:
        return max(1, int(duration_ms) + self.hold_extra_ms)

    def _tap_ui(self, key: str, hold_ms: int) -> None:
        pt = self.profile.resolve_key(
            key,
            display_width=self.display_width,
            display_height=self.display_height,
        )
        self.touch.tap(pt, hold_ms=hold_ms)

    def _ensure_modifier(self, modifier: Modifier) -> None:
        if modifier == self.current_modifier:
            return
        ui = MODIFIER_TO_UI[modifier]
        self._tap_ui(ui, self.modifier_tap_ms)
        self.current_modifier = modifier
        self.touch.sleep_ms(40)

    @staticmethod
    def _phone_keys(note: PlayNote) -> tuple[Modifier, str]:
        """Map score note onto game UI keys.

        ##1 (+2 octaves) → 升调 + 1' (same sounding as #1').
        """
        if note.modifier == Modifier.SEMITONE:
            return Modifier.SEMITONE, PITCH_TO_UI[note.pitch]
        if note.octaves >= 2 and note.pitch == PitchKey.N1:
            return Modifier.SHARP, PITCH_TO_UI[PitchKey.N1P]
        if note.octaves <= -2 and note.pitch == PitchKey.N1P:
            return Modifier.FLAT, PITCH_TO_UI[PitchKey.N1]
        return note.modifier, PITCH_TO_UI[note.pitch]

    @staticmethod
    def _acc_label(note: PlayNote) -> str:
        if note.modifier == Modifier.SEMITONE:
            return "s"
        if note.octaves > 0:
            return "#" * note.octaves
        if note.octaves < 0:
            return "b" * (-note.octaves)
        return ""

    def play(
        self,
        score: Score,
        *,
        countdown: int = 3,
        verbose: bool = True,
    ) -> None:
        if countdown > 0:
            for i in range(countdown, 0, -1):
                print(f"starting in {i}…", flush=True)
                time.sleep(1)

        if verbose:
            extra = (
                f" hold_extra={self.hold_extra_ms}ms" if self.hold_extra_ms else ""
            )
            print(
                f"playing '{score.title}' bpm={score.bpm:.1f} "
                f"backend={self.touch.backend.value}{extra}",
                flush=True,
            )

        for ev in score.events:
            if isinstance(ev, SetRegister):
                # 游戏里音域数字只是状态显示，不是可点按键；八度用升调/降调
                continue
            if isinstance(ev, SetModifier):
                self._ensure_modifier(ev.modifier)
            elif isinstance(ev, PlayNote):
                mod, ui = self._phone_keys(ev)
                self._ensure_modifier(mod)
                hold = self._note_hold_ms(ev.duration_ms)
                if verbose:
                    print(
                        f"  {self._acc_label(ev)}{ev.pitch.value} {hold}ms",
                        flush=True,
                    )
                self._tap_ui(ui, hold)
            elif isinstance(ev, Rest):
                ms = max(1, int(round(ev.duration_ms * score.rest_scale)))
                if verbose:
                    print(f"  rest {ms}ms", flush=True)
                self.touch.sleep_ms(ms)
            elif isinstance(ev, LyricMark):
                if verbose:
                    print(f"  ▶ {ev.text}", flush=True)
            else:
                print(f"  unknown event {ev!r}", file=sys.stderr)

        if verbose:
            print("done.", flush=True)


def format_timeline(score: Score) -> str:
    lines = [
        f"# {score.title}  bpm={score.bpm:.1f}  ms_beat={score.ms_beat:.1f}",
    ]
    t = 0
    mod = Modifier.NATURAL
    for ev in score.events:
        if isinstance(ev, SetRegister):
            continue
        if isinstance(ev, SetModifier):
            mod = ev.modifier
            lines.append(f"{t:6d}ms  SET modifier={mod.value}")
        elif isinstance(ev, PlayNote):
            acc = Player._acc_label(ev) or ev.modifier.value
            lines.append(
                f"{t:6d}ms  NOTE {acc}{ev.pitch.value} "
                f"hold={ev.duration_ms}ms"
            )
            t += ev.duration_ms
        elif isinstance(ev, Rest):
            ms = max(1, int(round(ev.duration_ms * score.rest_scale)))
            lines.append(f"{t:6d}ms  REST {ms}ms")
            t += ms
        elif isinstance(ev, LyricMark):
            lines.append(f"{t:6d}ms  ▶ {ev.text}")
    lines.append(f"total ~{t}ms")
    return "\n".join(lines)
