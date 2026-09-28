from __future__ import annotations

import time
from enum import Enum

from delta_harmonica.adb_util import AdbError, shell
from delta_harmonica.models import Point


class TouchBackend(str, Enum):
    MOTIONEVENT = "motionevent"
    SWIPE = "swipe"
    DRY_RUN = "dry-run"


class TouchController:
    """Send press/hold/release using adb (device coordinates)."""

    def __init__(
        self,
        *,
        serial: str | None = None,
        dry_run: bool = False,
        backend: TouchBackend | None = None,
    ) -> None:
        self.serial = serial
        self.dry_run = dry_run
        if dry_run:
            self.backend = TouchBackend.DRY_RUN
        elif backend is not None:
            self.backend = backend
        else:
            self.backend = self._detect_backend()

    def _detect_backend(self) -> TouchBackend:
        try:
            proc = shell("input", serial=self.serial, check=False)
            help_text = (proc.stdout or "") + (proc.stderr or "")
            if "motionevent" in help_text.lower():
                return TouchBackend.MOTIONEVENT
        except AdbError:
            pass
        # Probe: motionevent with invalid args often still mentions the subcommand
        try:
            proc = shell(
                "input motionevent",
                serial=self.serial,
                check=False,
            )
            text = (proc.stdout or "") + (proc.stderr or "")
            if "motionevent" in text.lower() or proc.returncode in (1, 255):
                # Many builds print usage and exit non-zero — treat as available
                if "unknown" not in text.lower() and "error" not in text.lower()[:40]:
                    return TouchBackend.MOTIONEVENT
                if "usage" in text.lower() or "DOWN" in text:
                    return TouchBackend.MOTIONEVENT
        except AdbError:
            pass
        return TouchBackend.SWIPE

    def tap(self, point: Point, hold_ms: int = 50) -> None:
        self.press(point, hold_ms)

    def down(self, point: Point) -> None:
        if self.backend == TouchBackend.DRY_RUN:
            print(f"[dry-run] down ({point.x},{point.y})")
            return
        if self.backend == TouchBackend.MOTIONEVENT:
            shell(
                f"input motionevent DOWN {point.x} {point.y}",
                serial=self.serial,
            )
            return
        # swipe backend: remember point; actual hold done in up()/press()
        self._swipe_point = point

    def up(self, point: Point | None = None) -> None:
        if self.backend == TouchBackend.DRY_RUN:
            print("[dry-run] up")
            return
        if self.backend == TouchBackend.MOTIONEVENT:
            if point is None:
                raise AdbError("motionevent UP needs coordinates")
            shell(
                f"input motionevent UP {point.x} {point.y}",
                serial=self.serial,
            )
            return
        # swipe: zero-length done in press(); up alone is no-op after press
        return

    def press(self, point: Point, hold_ms: int) -> None:
        hold_ms = max(1, int(hold_ms))
        if self.backend == TouchBackend.DRY_RUN:
            print(f"[dry-run] press ({point.x},{point.y}) {hold_ms}ms")
            time.sleep(hold_ms / 1000.0)
            return

        if self.backend == TouchBackend.MOTIONEVENT:
            self._motionevent_press(point, hold_ms)
        else:
            self._swipe_press(point, hold_ms)

    def _motionevent_press(self, point: Point, hold_ms: int) -> None:
        shell(
            f"input motionevent DOWN {point.x} {point.y}",
            serial=self.serial,
        )
        time.sleep(hold_ms / 1000.0)
        shell(
            f"input motionevent UP {point.x} {point.y}",
            serial=self.serial,
        )

    def _swipe_press(self, point: Point, hold_ms: int) -> None:
        # swipe with zero travel approximates a hold
        shell(
            f"input swipe {point.x} {point.y} {point.x} {point.y} {hold_ms}",
            serial=self.serial,
            timeout=max(30.0, hold_ms / 1000.0 + 5),
        )

    def sleep_ms(self, ms: int) -> None:
        ms = max(0, int(ms))
        if self.backend == TouchBackend.DRY_RUN:
            print(f"[dry-run] sleep {ms}ms")
        time.sleep(ms / 1000.0)
