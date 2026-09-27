from __future__ import annotations

import re
import shutil
import subprocess

from delta_harmonica.geometry import Rect


class WindowError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise WindowError(f"command not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise WindowError(f"command timed out: {' '.join(cmd)}") from exc
    if proc.returncode != 0:
        raise WindowError(
            f"{' '.join(cmd)} failed: {(proc.stderr or proc.stdout).strip()}"
        )
    return proc.stdout


def find_scrcpy_window_id() -> str:
    if not shutil.which("xdotool"):
        raise WindowError(
            "xdotool not found; install it or pass --window-id for calibrate"
        )

    # Prefer WM_CLASS / name containing scrcpy
    for search in (
        ["xdotool", "search", "--class", "scrcpy"],
        ["xdotool", "search", "--name", "scrcpy"],
        ["xdotool", "search", "--name", "Scrcpy"],
    ):
        proc = subprocess.run(
            search, capture_output=True, text=True, check=False, timeout=10
        )
        if proc.returncode == 0 and proc.stdout.strip():
            # Last match is often the most recently focused/created
            ids = proc.stdout.strip().splitlines()
            return ids[-1].strip()
    raise WindowError("no scrcpy window found (is scrcpy running under X11?)")


def get_window_rect(window_id: str) -> Rect:
    if shutil.which("xdotool"):
        out = _run(
            ["xdotool", "getwindowgeometry", "--shell", window_id]
        )
        data: dict[str, int] = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                    data[k] = int(v)
        if not all(k in data for k in ("X", "Y", "WIDTH", "HEIGHT")):
            raise WindowError(f"cannot parse window geometry: {out!r}")
        return Rect(data["X"], data["Y"], data["WIDTH"], data["HEIGHT"])

    raise WindowError("xdotool required to read window geometry")


def parse_geometry_string(value: str) -> Rect:
    """Parse WIDTHxHEIGHT+X+Y (xdotool-like) or X,Y,W,H."""
    m = re.fullmatch(
        r"(\d+)x(\d+)([+-]\d+)([+-]\d+)",
        value.strip(),
    )
    if m:
        w, h, x, y = m.groups()
        return Rect(int(x), int(y), int(w), int(h))
    parts = [p.strip() for p in value.split(",")]
    if len(parts) == 4 and all(
        re.fullmatch(r"-?\d+", p) for p in parts
    ):
        x, y, w, h = (int(p) for p in parts)
        return Rect(x, y, w, h)
    raise WindowError(
        f"invalid geometry {value!r}; use WIDTHxHEIGHT+X+Y or X,Y,W,H"
    )
