from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from delta_harmonica.paths import project_root

_SPEED_LINE = re.compile(r"(?m)^(speed\s*=\s*)[^\s#]+(.*)$")
_TRANSPOSE_LINE = re.compile(r"(?m)^(transpose\s*=\s*)[^\s#]+(.*)$")
_PRESS_EARLY_LINE = re.compile(r"(?m)^(press_early\s*=\s*)[^\s#]+(.*)$")
_HOLD_EXTRA_LINE = re.compile(r"(?m)^(hold_extra\s*=\s*)[^\s#]+(.*)$")


@dataclass(frozen=True)
class AppConfig:
    """Defaults from ``dharm.toml`` (CLI flags override)."""

    profile: str | None = None
    hold_extra: int = 0
    press_early: int = 0
    countdown: int = 3
    speed: float = 1.0
    # Global pitch shift in semitones (octave=±12; C→D=+2). Auto-suggest if score OOR.
    transpose: int = 0
    serial: str | None = None
    path: Path | None = None


def config_path() -> Path:
    env = os.environ.get("DHARM_CONFIG")
    if env:
        return Path(env).expanduser()
    return project_root() / "dharm.toml"


def clamp_speed(speed: float) -> float:
    return max(0.25, min(3.0, round(float(speed), 2)))


def clamp_transpose(semitones: int) -> int:
    return max(-24, min(24, int(semitones)))


def _int_ge0(data: dict, key: str, default: int = 0) -> int:
    try:
        return max(0, int(data.get(key, default)))
    except (TypeError, ValueError):
        return default


def load_config(path: Path | None = None) -> AppConfig:
    p = path or config_path()
    if not p.is_file():
        return AppConfig()
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return AppConfig(path=p)

    hold_extra = _int_ge0(data, "hold_extra", 0)
    press_early = _int_ge0(data, "press_early", 0)
    countdown = _int_ge0(data, "countdown", 3)

    try:
        speed = float(data.get("speed", 1.0))
    except (TypeError, ValueError):
        speed = 1.0
    speed = clamp_speed(speed)

    try:
        transpose = clamp_transpose(int(data.get("transpose", 0)))
    except (TypeError, ValueError):
        transpose = 0

    profile = data.get("profile")
    if profile is not None:
        profile = str(profile).strip() or None

    serial = data.get("serial")
    if serial is not None:
        serial = str(serial).strip() or None

    return AppConfig(
        profile=profile,
        hold_extra=hold_extra,
        press_early=press_early,
        countdown=countdown,
        speed=speed,
        transpose=transpose,
        serial=serial,
        path=p,
    )


def _upsert_line(text: str, pattern: re.Pattern[str], key: str, value: str) -> str:
    if pattern.search(text):
        return pattern.sub(rf"\g<1>{value}\2", text, count=1)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + f"{key} = {value}\n"


def save_speed(speed: float, path: Path | None = None) -> Path:
    """Write ``speed`` into ``dharm.toml``, preserving comments / other keys."""
    speed = clamp_speed(speed)
    p = path or config_path()
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    text = _upsert_line(text, _SPEED_LINE, "speed", f"{speed:.2f}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def save_transpose(semitones: int, path: Path | None = None) -> Path:
    """Write ``transpose`` (semitones) into ``dharm.toml``."""
    semitones = clamp_transpose(semitones)
    p = path or config_path()
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    text = _upsert_line(text, _TRANSPOSE_LINE, "transpose", str(semitones))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def save_latency(press_early: int, hold_extra: int, path: Path | None = None) -> Path:
    """Write global ``press_early`` / ``hold_extra`` into ``dharm.toml``."""
    p = path or config_path()
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    text = _upsert_line(text, _PRESS_EARLY_LINE, "press_early", str(max(0, int(press_early))))
    text = _upsert_line(text, _HOLD_EXTRA_LINE, "hold_extra", str(max(0, int(hold_extra))))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p
