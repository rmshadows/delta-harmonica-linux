from __future__ import annotations

import select
import sys
import termios
import tty
import threading
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
        press_early_ms: int = 0,
        speed: float = 1.0,
        assume_modifier: Modifier = Modifier.NATURAL,
        display_width: int | None = None,
        display_height: int | None = None,
    ) -> None:
        self.profile = profile
        self.touch = touch
        self.modifier_tap_ms = modifier_tap_ms
        # Mode 2: hold each key longer so the game has time to sound.
        self.hold_extra_ms = max(0, int(hold_extra_ms))
        # Mode 1: start the next key this many ms early (legato / cover latency).
        self.press_early_ms = max(0, int(press_early_ms))
        self.speed = max(0.25, min(3.0, float(speed)))
        self.current_modifier = assume_modifier
        self.display_width = display_width or profile.device_width
        self.display_height = display_height or profile.device_height
        self._stop = False

    def _scale_ms(self, ms: int) -> int:
        return max(1, int(round(ms / self.speed)))

    def _note_hold_ms(self, duration_ms: int) -> int:
        return max(1, int(duration_ms) + self.hold_extra_ms)

    def _onset_gap_ms(self, duration_ms: int) -> int:
        """Wall-clock from this press to the next press."""
        return max(1, int(duration_ms) + self.hold_extra_ms - self.press_early_ms)

    def _resolve(self, key: str):
        return self.profile.resolve_key(
            key,
            display_width=self.display_width,
            display_height=self.display_height,
        )

    def _tap_ui(self, key: str, hold_ms: int) -> None:
        self.touch.tap(self._resolve(key), hold_ms=hold_ms)

    def _press_note(self, key: str, duration_ms: int) -> None:
        """Press one note honoring hold_extra + press_early (single finger).

        interval = duration + hold_extra - press_early  (next onset)
        hold     = duration + hold_extra
        """
        from delta_harmonica.touch import TouchBackend

        hold_ms = self._scale_ms(self._note_hold_ms(duration_ms))
        gap_ms = self._scale_ms(self._onset_gap_ms(duration_ms))
        pt = self._resolve(key)
        down_ms = min(hold_ms, gap_ms)
        idle_ms = max(0, gap_ms - hold_ms)
        if self.touch.backend == TouchBackend.MOTIONEVENT:
            self.touch.down(pt)
            self.touch.sleep_ms(down_ms)
            self.touch.up(pt)
        else:
            # swipe / dry-run: atomic press for the down portion
            self.touch.press(pt, down_ms)
        if idle_ms:
            self.touch.sleep_ms(idle_ms)

    def _ensure_modifier(self, modifier: Modifier) -> None:
        if modifier == self.current_modifier:
            return
        ui = MODIFIER_TO_UI[modifier]
        self._tap_ui(ui, self._scale_ms(self.modifier_tap_ms))
        self.current_modifier = modifier
        self.touch.sleep_ms(self._scale_ms(40))

    @staticmethod
    def _phone_keys(note: PlayNote) -> tuple[Modifier, str]:
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

    def _speed_listener(self) -> None:
        """Background: +/- or [] change speed; q/Esc stop. Needs a TTY."""
        if not sys.stdin.isatty():
            return
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not self._stop:
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not r:
                    continue
                ch = sys.stdin.read(1)
                if ch in ("+", "=", "]"):
                    self.speed = min(3.0, round(self.speed + 0.05, 2))
                    print(f"\n  ▶ speed ×{self.speed:.2f}", flush=True)
                elif ch in ("-", "["):
                    self.speed = max(0.25, round(self.speed - 0.05, 2))
                    print(f"\n  ▶ speed ×{self.speed:.2f}", flush=True)
                elif ch in ("q", "Q", "\x1b"):
                    self._stop = True
                    print("\n  ▶ stop", flush=True)
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:  # noqa: BLE001
                pass

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
            bits = []
            if self.hold_extra_ms:
                bits.append(f"hold_extra={self.hold_extra_ms}ms")
            if self.press_early_ms:
                bits.append(f"press_early={self.press_early_ms}ms")
            bits.append(f"speed=×{self.speed:.2f}")
            print(
                f"playing '{score.title}' bpm={score.bpm:.1f} "
                f"backend={self.touch.backend.value} {' '.join(bits)}",
                flush=True,
            )
            print(
                "  keys: +/] faster · -/ [ slower · q stop",
                flush=True,
            )

        self._stop = False
        aborted = False
        listener = threading.Thread(target=self._speed_listener, daemon=True)
        listener.start()

        try:
            for ev in score.events:
                if self._stop:
                    aborted = True
                    break
                if isinstance(ev, SetRegister):
                    continue
                if isinstance(ev, SetModifier):
                    self._ensure_modifier(ev.modifier)
                elif isinstance(ev, PlayNote):
                    mod, ui = self._phone_keys(ev)
                    self._ensure_modifier(mod)
                    hold = self._scale_ms(self._note_hold_ms(ev.duration_ms))
                    gap = self._scale_ms(self._onset_gap_ms(ev.duration_ms))
                    if verbose:
                        print(
                            f"  {self._acc_label(ev)}{ev.pitch.value} "
                            f"hold={hold}ms gap={gap}ms ×{self.speed:.2f}",
                            flush=True,
                        )
                    self._press_note(ui, ev.duration_ms)
                elif isinstance(ev, Rest):
                    ms = max(1, int(round(ev.duration_ms * score.rest_scale)))
                    ms = self._scale_ms(ms)
                    if verbose:
                        print(f"  rest {ms}ms ×{self.speed:.2f}", flush=True)
                    self.touch.sleep_ms(ms)
                elif isinstance(ev, LyricMark):
                    if verbose:
                        print(f"  ▶ {ev.text}", flush=True)
                else:
                    print(f"  unknown event {ev!r}", file=sys.stderr)
        finally:
            self._stop = True

        if verbose:
            print("stopped." if aborted else "done.", flush=True)


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
