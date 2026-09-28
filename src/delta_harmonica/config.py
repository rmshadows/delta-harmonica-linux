from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from delta_harmonica.paths import project_root


@dataclass(frozen=True)
class AppConfig:
    """Defaults from ``dharm.toml`` (CLI flags override)."""

    profile: str | None = None
    hold_extra: int = 0
    press_early: int = 0
    countdown: int = 3
    speed: float = 1.0
    serial: str | None = None
    path: Path | None = None


def config_path() -> Path:
    env = os.environ.get("DHARM_CONFIG")
    if env:
        return Path(env).expanduser()
    return project_root() / "dharm.toml"


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
    speed = max(0.25, min(3.0, speed))

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
        serial=serial,
        path=p,
    )
