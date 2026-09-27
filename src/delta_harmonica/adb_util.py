from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass


class AdbError(RuntimeError):
    pass


@dataclass
class DeviceInfo:
    serial: str
    state: str


def which_adb() -> str | None:
    return shutil.which("adb")


def which_scrcpy() -> str | None:
    return shutil.which("scrcpy")


def run_adb(
    args: list[str],
    *,
    serial: str | None = None,
    check: bool = True,
    timeout: float | None = 30,
) -> subprocess.CompletedProcess[str]:
    adb = which_adb()
    if not adb:
        raise AdbError("adb not found in PATH")
    cmd = [adb]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb timed out: {' '.join(cmd)}") from exc
    if check and proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise AdbError(f"adb failed ({proc.returncode}): {err}")
    return proc


def list_devices() -> list[DeviceInfo]:
    proc = run_adb(["devices"], check=True)
    devices: list[DeviceInfo] = []
    for line in proc.stdout.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append(DeviceInfo(serial=parts[0], state=parts[1]))
    return devices


def ready_devices() -> list[DeviceInfo]:
    return [d for d in list_devices() if d.state == "device"]


def pick_serial(serial: str | None = None) -> str:
    devices = ready_devices()
    if serial:
        if not any(d.serial == serial for d in devices):
            raise AdbError(f"device not ready: {serial}")
        return serial
    if not devices:
        raise AdbError("no adb device in 'device' state")
    if len(devices) > 1:
        raise AdbError(
            "multiple devices; pass --serial. Connected: "
            + ", ".join(d.serial for d in devices)
        )
    return devices[0].serial


def get_wm_size(serial: str | None = None) -> tuple[int, int]:
    """Physical / override size from ``wm size`` (may ignore current rotation)."""
    proc = run_adb(["shell", "wm", "size"], serial=serial)
    text = proc.stdout.strip()
    # Prefer Override size when present
    m = re.search(r"Override size:\s*(\d+)\s*x\s*(\d+)", text, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"Physical size:\s*(\d+)\s*x\s*(\d+)", text, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    matches = re.findall(r"(\d+)\s*x\s*(\d+)", text)
    if not matches:
        raise AdbError(f"cannot parse wm size: {text!r}")
    w, h = matches[-1]
    return int(w), int(h)


def get_display_size(serial: str | None = None) -> tuple[int, int]:
    """Current logical display size used by ``input tap`` (respects rotation).

    ``wm size`` often stays at the physical portrait size while the device is
    landscape (games / harmonica UI). Scrcpy then shows a wide frame; letterbox
    math must use the *current* size or clicks land in fake pillarbox gutters.
    """
    # 1) Active input viewport (best: matches touch coordinate space)
    try:
        proc = run_adb(
            ["shell", "dumpsys", "input"],
            serial=serial,
            check=False,
            timeout=15,
        )
        text = proc.stdout or ""
        for m in re.finditer(
            r"Viewport INTERNAL:.*?logicalFrame="
            r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]"
            r".*?isActive=\[([01])\]",
            text,
            re.DOTALL,
        ):
            x1, y1, x2, y2, active = m.groups()
            if active != "1":
                continue
            w, h = int(x2) - int(x1), int(y2) - int(y1)
            if w >= 200 and h >= 200:
                return w, h
        # any INTERNAL viewport if active flag missing / format differs
        for m in re.finditer(
            r"Viewport INTERNAL:.*?logicalFrame="
            r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]",
            text,
            re.DOTALL,
        ):
            x1, y1, x2, y2 = m.groups()
            w, h = int(x2) - int(x1), int(y2) - int(y1)
            if w >= 200 and h >= 200:
                return w, h
    except AdbError:
        pass

    # 2) dumpsys display override "real W x H" for built-in display
    try:
        proc = run_adb(
            ["shell", "dumpsys", "display"],
            serial=serial,
            check=False,
            timeout=15,
        )
        text = proc.stdout or ""
        m = re.search(
            r"mOverrideDisplayInfo=DisplayInfo\{"
            r'"[^"]*".*?\breal\s+(\d+)\s+x\s+(\d+)',
            text,
            re.DOTALL,
        )
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            if w >= 200 and h >= 200:
                return w, h
    except AdbError:
        pass

    # 3) Fallback: wm size (+ swap if orientation is 90/270)
    w, h = get_wm_size(serial)
    try:
        proc = run_adb(
            ["shell", "dumpsys", "display"],
            serial=serial,
            check=False,
            timeout=15,
        )
        # First built-in display orientation 1 or 3 → landscape relative to physical
        if re.search(r"\bmCurrentOrientation=[13]\b", proc.stdout or ""):
            if w < h:
                return h, w
    except AdbError:
        pass
    return w, h


def shell(
    command: str,
    *,
    serial: str | None = None,
    check: bool = True,
    timeout: float | None = 30,
) -> subprocess.CompletedProcess[str]:
    return run_adb(["shell", command], serial=serial, check=check, timeout=timeout)
