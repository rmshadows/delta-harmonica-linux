from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Callable

from delta_harmonica.adb_util import get_display_size, get_wm_size, pick_serial
from delta_harmonica.geometry import Rect, fit_content_rect
from delta_harmonica.models import Point, Profile, UI_KEY_LABELS, UI_KEYS
from delta_harmonica.profile_io import save_profile
from delta_harmonica.touch import TouchController
from delta_harmonica.window import (
    WindowError,
    find_scrcpy_window_id,
    get_window_rect,
)


class CalibrateError(RuntimeError):
    pass


def _wait_click(
    mapping_factory: Callable[[], object],
    *,
    timeout: float = 120.0,
) -> Point:
    """Wait for a mouse click inside the scrcpy content area; return device Point."""
    try:
        from pynput import mouse
    except ImportError as exc:
        raise CalibrateError("pynput is required for calibrate") from exc

    result: dict[str, Point | None] = {"point": None}
    error: dict[str, str | None] = {"msg": None}
    done = threading.Event()

    def on_click(x: int, y: int, button: object, pressed: bool) -> None:
        if not pressed:
            return
        try:
            mapping = mapping_factory()  # type: ignore[operator]
            ax, ay = int(x), int(y)
            device = mapping.window_abs_to_device(ax, ay)  # type: ignore[attr-defined]
            if device is None:
                c = mapping.content  # type: ignore[attr-defined]
                print(
                    "  click outside video area — try again "
                    f"(click {ax},{ay}; video "
                    f"{c.width}x{c.height}+{c.x}+{c.y})",
                    file=sys.stderr,
                )
                return
            result["point"] = Point(device[0], device[1])
            done.set()
            return False  # stop listener
        except Exception as exc:  # noqa: BLE001
            error["msg"] = str(exc)
            done.set()
            return False

    listener = mouse.Listener(on_click=on_click)
    listener.start()
    print("  click the key in the scrcpy window…", flush=True)
    if not done.wait(timeout):
        listener.stop()
        raise CalibrateError("timed out waiting for click")
    listener.stop()
    if error["msg"]:
        raise CalibrateError(error["msg"])
    if result["point"] is None:
        raise CalibrateError("no click captured")
    return result["point"]


def run_calibrate(
    profile_name: str,
    *,
    serial: str | None = None,
    window_id: str | None = None,
    window_rect: Rect | None = None,
) -> Path:
    serial = pick_serial(serial)
    physical = get_wm_size(serial)
    dw, dh = get_display_size(serial)

    tracked_wid = window_id
    fixed_geometry = window_rect is not None and window_id is None

    if window_rect is None:
        tracked_wid = window_id or find_scrcpy_window_id()
        window_rect = get_window_rect(tracked_wid)
        print(
            f"scrcpy window {tracked_wid}: "
            f"{window_rect.width}x{window_rect.height}"
            f"+{window_rect.x}+{window_rect.y}"
        )
    else:
        print(
            f"using geometry: {window_rect.width}x{window_rect.height}"
            f"+{window_rect.x}+{window_rect.y}"
        )

    print(f"display size (touch coords): {dw}x{dh}")
    if (physical[0], physical[1]) != (dw, dh):
        print(
            f"physical wm size: {physical[0]}x{physical[1]} "
            f"(rotated — using display size for mapping)"
        )
    mapping0 = fit_content_rect(window_rect, dw, dh)
    print(
        f"video area in window: "
        f"{mapping0.content.width}x{mapping0.content.height}"
        f"+{mapping0.content.x}+{mapping0.content.y} "
        f"(scale={mapping0.scale:.3f})"
    )
    print("Calibrate: click each prompted key on the scrcpy window.")
    print(
        "Note: positions are saved as phone pixels (adb coords), not window pixels.\n"
        "      Maximizing / resizing scrcpy later does NOT require re-calibrate.\n"
        "      Re-calibrate only if phone resolution/orientation or game UI layout changes.\n"
    )

    def mapping_factory() -> object:
        nonlocal tracked_wid
        rect = window_rect
        assert rect is not None
        if not fixed_geometry:
            try:
                wid = tracked_wid or find_scrcpy_window_id()
                tracked_wid = wid
                rect = get_window_rect(wid)
            except WindowError:
                pass
        return fit_content_rect(rect, dw, dh)

    keys: dict[str, Point] = {}
    for key in UI_KEYS:
        label = UI_KEY_LABELS.get(key, key)
        print(f"[{len(keys)+1}/{len(UI_KEYS)}] {label} ({key})")
        pt = _wait_click(mapping_factory)
        keys[key] = pt
        print(f"  -> device ({pt.x}, {pt.y})")
        time.sleep(0.15)

    profile = Profile(
        name=profile_name,
        device_width=dw,
        device_height=dh,
        keys=keys,
    )
    path = save_profile(profile)
    print(f"\nsaved profile: {path}")
    return path


def run_calibrate_test(
    profile: Profile,
    *,
    serial: str | None = None,
    dry_run: bool = False,
    hold_ms: int = 120,
    gap_ms: int = 250,
) -> None:
    serial = None if dry_run else pick_serial(serial)
    touch = TouchController(serial=serial, dry_run=dry_run)
    dw = dh = None
    if not dry_run and serial:
        dw, dh = get_display_size(serial)
        if (dw, dh) != (profile.device_width, profile.device_height):
            print(
                f"display now {dw}x{dh}, profile {profile.device_width}x"
                f"{profile.device_height} — scaling taps"
            )
    print(f"testing profile '{profile.name}' backend={touch.backend.value}")
    for key in UI_KEYS:
        label = UI_KEY_LABELS.get(key, key)
        pt = profile.resolve_key(key, display_width=dw, display_height=dh)
        print(f"  {label}: ({pt.x},{pt.y})")
        touch.tap(pt, hold_ms=hold_ms)
        touch.sleep_ms(gap_ms)
    print("done.")
