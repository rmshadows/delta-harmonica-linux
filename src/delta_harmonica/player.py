from __future__ import annotations

import select
import sys
import termios
import tty
import threading
import time
from pathlib import Path

from delta_harmonica.config import clamp_transpose, save_latency
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
from delta_harmonica.score_parser import update_score_playback
from delta_harmonica.touch import TouchController
from delta_harmonica.transpose import (
    diatonic_key_label,
    nudge_diatonic_key,
    transpose_note,
)

# High-contrast ANSI so live changes stay visible between note lines.
_C = {
    "speed": "\033[1;30;46m",  # black on cyan
    "key": "\033[1;97;45m",  # white on magenta
    "octave": "\033[1;97;44m",  # white on blue
    "early": "\033[1;30;42m",  # black on green
    "hold": "\033[1;30;43m",  # black on yellow
    "save": "\033[1;30;102m",  # black on bright green
    "dim": "\033[2m",
    "reset": "\033[0m",
}


def _cprint(kind: str, msg: str) -> None:
    print(f"{_C.get(kind, '')}{msg}{_C['reset']}", flush=True)


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
        transpose: int = 0,
        score_path: Path | None = None,
        assume_modifier: Modifier = Modifier.NATURAL,
        display_width: int | None = None,
        display_height: int | None = None,
    ) -> None:
        self.profile = profile
        self.touch = touch
        self.modifier_tap_ms = modifier_tap_ms
        self.hold_extra_ms = max(0, int(hold_extra_ms))
        self.press_early_ms = max(0, int(press_early_ms))
        self.speed = max(0.25, min(3.0, float(speed)))
        self.transpose = clamp_transpose(transpose)
        self.score_path = Path(score_path) if score_path else None
        self.current_modifier = assume_modifier
        self.display_width = display_width or profile.device_width
        self.display_height = display_height or profile.device_height
        self._stop = False
        self._paused = False
        self._saved_score = (self.speed, self.transpose)
        self._saved_latency = (self.press_early_ms, self.hold_extra_ms)

    def _scale_ms(self, ms: int) -> int:
        return max(1, int(round(ms / self.speed)))

    def _note_hold_ms(self, duration_ms: int) -> int:
        return max(1, int(duration_ms) + self.hold_extra_ms)

    def _onset_gap_ms(self, duration_ms: int) -> int:
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
        from delta_harmonica.touch import TouchBackend

        hold_ms = self._scale_ms(self._note_hold_ms(duration_ms))
        gap_ms = self._scale_ms(self._onset_gap_ms(duration_ms))
        pt = self._resolve(key)
        down_ms = min(hold_ms, gap_ms)
        idle_ms = max(0, gap_ms - hold_ms)
        if self.touch.backend == TouchBackend.MOTIONEVENT:
            self.touch.down(pt)
            # Hold itself is not pause-aware (finger must come up);
            # pause applies between notes / during rests.
            self.touch.sleep_ms(down_ms)
            self.touch.up(pt)
        else:
            self.touch.press(pt, down_ms)
        if idle_ms:
            self._sleep_ms(idle_ms)

    def _wait_while_paused(self) -> None:
        """Block while paused; returns immediately if stopped."""
        shown = False
        while self._paused and not self._stop:
            if not shown:
                _cprint("dim", "\n  ▶ 已暂停 — 再按 p 继续，q 停止")
                shown = True
            time.sleep(0.05)

    def _sleep_ms(self, ms: int) -> None:
        """Sleep that freezes while paused and aborts on stop."""
        remaining = max(0, int(ms)) / 1000.0
        while remaining > 0:
            if self._stop:
                return
            if self._paused:
                self._wait_while_paused()
                continue
            slice_s = min(0.05, remaining)
            time.sleep(slice_s)
            remaining -= slice_s

    def _ensure_modifier(self, modifier: Modifier) -> None:
        if modifier == self.current_modifier:
            return
        # 游戏里「半音」是开关：点一下开、再点一下关；点「自然音」关不掉。
        if self.current_modifier == Modifier.SEMITONE:
            self._tap_ui(
                MODIFIER_TO_UI[Modifier.SEMITONE],
                self._scale_ms(self.modifier_tap_ms),
            )
            self.current_modifier = Modifier.NATURAL
            self.touch.sleep_ms(self._scale_ms(40))
            if modifier == Modifier.NATURAL:
                return
        ui = MODIFIER_TO_UI[modifier]
        self._tap_ui(ui, self._scale_ms(self.modifier_tap_ms))
        self.current_modifier = modifier
        self.touch.sleep_ms(self._scale_ms(40))

    def _clear_semitone(self) -> None:
        """Turn off 半音 by tapping it again (toggle), not 自然音."""
        if self.current_modifier == Modifier.SEMITONE:
            self._ensure_modifier(Modifier.NATURAL)

    @staticmethod
    def _phone_keys(note: PlayNote) -> tuple[Modifier, str]:
        if note.modifier == Modifier.SEMITONE:
            return Modifier.SEMITONE, PITCH_TO_UI[note.pitch]
        if note.octaves >= 2 and note.pitch == PitchKey.N1:
            return Modifier.SHARP, PITCH_TO_UI[PitchKey.N1P]
        if note.octaves >= 1 and note.pitch == PitchKey.N1P:
            return Modifier.SHARP, PITCH_TO_UI[PitchKey.N1P]
        if (
            note.modifier == Modifier.SHARP
            and note.octaves == 1
            and note.pitch == PitchKey.N1
        ):
            return Modifier.NATURAL, PITCH_TO_UI[PitchKey.N1P]
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

    def _persist_score(self, *, reason: str) -> None:
        if self.score_path is None:
            _cprint("save", f"\n  ▶ 无乐谱路径，无法保存 ({reason})")
            return
        try:
            path = update_score_playback(
                self.score_path,
                speed=self.speed,
                transpose=self.transpose,
            )
        except OSError as exc:
            _cprint("save", f"\n  ▶ 写入乐谱失败: {exc}")
            return
        self._saved_score = (self.speed, self.transpose)
        self._flash(
            "save",
            f"已写入乐谱 {path.name}  speed=×{self.speed:.2f} "
            f"transpose={self.transpose:+d} ({reason})",
        )

    def _persist_latency(self, *, reason: str) -> None:
        try:
            path = save_latency(self.press_early_ms, self.hold_extra_ms)
        except OSError as exc:
            _cprint("save", f"\n  ▶ 写入配置失败: {exc}")
            return
        self._saved_latency = (self.press_early_ms, self.hold_extra_ms)
        self._flash("save", f"已写入 {path.name} early/hold ({reason})")

    def _flash(self, kind: str, headline: str) -> None:
        """One high-contrast line plus the current playback numbers."""
        _cprint(kind, f"\n  {headline}")
        print(
            f"  {_C['speed']} ×{self.speed:.2f} {_C['reset']}"
            f" {_C['key']} {diatonic_key_label(self.transpose)} {_C['reset']}"
            f" {_C['octave']} {self.transpose:+d}半音 {_C['reset']}"
            f" {_C['early']} early {self.press_early_ms} {_C['reset']}"
            f" {_C['hold']} hold {self.hold_extra_ms} {_C['reset']}",
            flush=True,
        )

    @staticmethod
    def _read_arrow() -> str | None:
        """Parse CSI/SS3 arrow after ESC already consumed. Never treat as quit.

        Normal: ESC [ A/B/C/D   Application: ESC O A/B/C/D
        Modified: ESC [ 1 ; N A  → still ends with A/B/C/D
        """
        # Under load the rest of the sequence can lag past 40ms — that race
        # used to look like bare Esc and abort playback.
        if not select.select([sys.stdin], [], [], 0.15)[0]:
            return None
        ch2 = sys.stdin.read(1)
        if ch2 == "[":
            body = ""
            while select.select([sys.stdin], [], [], 0.15)[0]:
                c = sys.stdin.read(1)
                if not c:
                    break
                body += c
                if ("A" <= c <= "Z") or ("a" <= c <= "z") or c == "~":
                    break
            if not body:
                return None
            final = body[-1]
        elif ch2 == "O":
            if not select.select([sys.stdin], [], [], 0.15)[0]:
                return None
            final = sys.stdin.read(1)
        else:
            return None
        return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(final)

    def _apply_arrow(self, direction: str) -> None:
        if direction == "up":
            self.transpose = clamp_transpose(self.transpose + 12)
            self._flash("octave", "▲ 升八度")
        elif direction == "down":
            self.transpose = clamp_transpose(self.transpose - 12)
            self._flash("octave", "▼ 降八度")
        elif direction == "right":
            self.transpose = clamp_transpose(nudge_diatonic_key(self.transpose, +1))
            self._flash("key", "→ 升调")
        elif direction == "left":
            self.transpose = clamp_transpose(nudge_diatonic_key(self.transpose, -1))
            self._flash("key", "← 降调")

    def _nudge_speed(self, delta: float, label: str) -> None:
        self.speed = max(0.25, min(3.0, round(self.speed + delta, 2)))
        self._flash("speed", label)

    def _input_listener(self) -> None:
        """TTY hotkeys. Arrow keys: ESC [ A/B/C/D or ESC O A/B/C/D."""
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
                if ch == "\x1b":
                    direction = self._read_arrow()
                    if direction:
                        self._apply_arrow(direction)
                    # bare Esc / unknown sequence: ignore (only q stops)
                elif ch in ("]", "+", "="):
                    self._nudge_speed(+0.05, f"{ch} 加速")
                elif ch in ("[", "-", "_"):
                    self._nudge_speed(-0.05, f"{ch} 减速")
                elif ch in ("z", "Z"):
                    self.press_early_ms = max(0, self.press_early_ms - 50)
                    self._flash("early", "z press_early −50")
                elif ch in ("x", "X"):
                    self.press_early_ms = self.press_early_ms + 50
                    self._flash("early", "x press_early +50")
                elif ch in ("c", "C"):
                    self.hold_extra_ms = max(0, self.hold_extra_ms - 50)
                    self._flash("hold", "c hold_extra −50")
                elif ch in ("v", "V"):
                    self.hold_extra_ms = self.hold_extra_ms + 50
                    self._flash("hold", "v hold_extra +50")
                elif ch in ("s", "S"):
                    self._persist_score(reason="key")
                    self._persist_latency(reason="key")
                elif ch in ("p", "P"):
                    self._paused = not self._paused
                    if self._paused:
                        _cprint("dim", "\n  ▶ 暂停")
                    else:
                        _cprint("dim", "\n  ▶ 继续")
                elif ch in ("q", "Q"):
                    self._paused = False
                    self._stop = True
                    _cprint("dim", "\n  ▶ stop")
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

        self._saved_score = (self.speed, self.transpose)
        self._saved_latency = (self.press_early_ms, self.hold_extra_ms)

        if verbose:
            bits = [
                f"speed=×{self.speed:.2f}",
                f"调={diatonic_key_label(self.transpose)}({self.transpose:+d})",
                f"early={self.press_early_ms}",
                f"hold={self.hold_extra_ms}",
            ]
            print(
                f"playing '{score.title}' bpm={score.bpm:.1f} "
                f"backend={self.touch.backend.value} {' '.join(bits)}",
                flush=True,
            )
            print(
                f"{_C['dim']}  键: [/][+/-] 减速加速  "
                f"{_C['key']}←→ 降调升调(CDEFGAB){_C['dim']}  "
                f"{_C['octave']}↑↓ ±八度{_C['dim']}  "
                f"{_C['early']}z/x early±50{_C['dim']}  "
                f"{_C['hold']}c/v hold±50{_C['dim']}  "
                f"{_C['save']}s 写入乐谱  "
                f"{_C['dim']}p 暂停/继续  q 停"
                f"{_C['reset']}",
                flush=True,
            )

        self._stop = False
        self._paused = False
        aborted = False
        listener = threading.Thread(target=self._input_listener, daemon=True)
        listener.start()

        try:
            for ev in score.events:
                if self._stop:
                    aborted = True
                    break
                self._wait_while_paused()
                if self._stop:
                    aborted = True
                    break
                if isinstance(ev, (SetRegister, SetModifier)):
                    continue
                if isinstance(ev, PlayNote):
                    note = transpose_note(ev, self.transpose) or ev
                    mod, ui = self._phone_keys(note)
                    self._ensure_modifier(mod)
                    hold = self._scale_ms(self._note_hold_ms(note.duration_ms))
                    gap = self._scale_ms(self._onset_gap_ms(note.duration_ms))
                    if verbose:
                        print(
                            f"  {self._acc_label(note)}{note.pitch.value} "
                            f"hold={hold}ms gap={gap}ms ×{self.speed:.2f}",
                            flush=True,
                        )
                    self._press_note(ui, note.duration_ms)
                    if mod == Modifier.SEMITONE:
                        self._clear_semitone()
                elif isinstance(ev, Rest):
                    ms = max(1, int(round(ev.duration_ms * score.rest_scale)))
                    ms = self._scale_ms(ms)
                    if verbose:
                        print(f"  rest {ms}ms ×{self.speed:.2f}", flush=True)
                    self._sleep_ms(ms)
                elif isinstance(ev, LyricMark):
                    if verbose:
                        print(f"  ▶ {ev.text}", flush=True)
                else:
                    print(f"  unknown event {ev!r}", file=sys.stderr)
        finally:
            self._stop = True
            try:
                self._clear_semitone()
            except Exception:  # noqa: BLE001
                pass
            # Persist even on KeyboardInterrupt — 倍速/移调只进当前乐谱
            reason = "stop" if aborted else "end"
            try:
                if (self.speed, self.transpose) != self._saved_score:
                    self._persist_score(reason=reason)
                if (self.press_early_ms, self.hold_extra_ms) != self._saved_latency:
                    self._persist_latency(reason=reason)
            except Exception:  # noqa: BLE001
                pass

        if verbose:
            print("stopped." if aborted else "done.", flush=True)


def format_timeline(score: Score) -> str:
    lines = [
        f"# {score.title}  bpm={score.bpm:.1f}  ms_beat={score.ms_beat:.1f}",
    ]
    t = 0
    for ev in score.events:
        if isinstance(ev, SetRegister):
            continue
        if isinstance(ev, SetModifier):
            lines.append(f"{t:6d}ms  SET modifier={ev.modifier.value}")
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
