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


def _parse_override_real_sizes(text: str) -> list[tuple[str, int, int]]:
    """Return (name, w, h) for each mOverrideDisplayInfo real size."""
    out: list[tuple[str, int, int]] = []
    for m in re.finditer(
        r'mOverrideDisplayInfo=DisplayInfo\{"([^"]*)".*?\breal\s+(\d+)\s+x\s+(\d+)',
        text,
        re.DOTALL,
    ):
        name, w_s, h_s = m.group(1), m.group(2), m.group(3)
        w, h = int(w_s), int(h_s)
        if w >= 200 and h >= 200:
            out.append((name, w, h))
    return out


def get_scrcpy_virtual_size(serial: str | None = None) -> tuple[int, int] | None:
    """Encoder frame size from the scrcpy virtual display (matches mirrored video)."""
    try:
        proc = run_adb(
            ["shell", "dumpsys", "display"],
            serial=serial,
            check=False,
            timeout=15,
        )
    except AdbError:
        return None
    for name, w, h in _parse_override_real_sizes(proc.stdout or ""):
        if name.lower().startswith("scrcpy"):
            return w, h
    return None


def get_display_size(serial: str | None = None) -> tuple[int, int]:
    """Current logical display size used by ``input tap`` (respects rotation).

    ``wm size`` often stays at the physical portrait size while the device is
    landscape (game / harmonica UI). Scrcpy then shows a wide frame; letterbox
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
        # Prefer deviceSize= when present (explicit WxH)
        for m in re.finditer(
            r"Viewport INTERNAL:.*?deviceSize=\[(\d+),\s*(\d+)\].*?isActive=\[([01])\]",
            text,
            re.DOTALL,
        ):
            w, h, active = int(m.group(1)), int(m.group(2)), m.group(3)
            if active == "1" and w >= 200 and h >= 200:
                return w, h
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
        for m in re.finditer(
            r"Viewport INTERNAL:.*?deviceSize=\[(\d+),\s*(\d+)\]",
            text,
            re.DOTALL,
        ):
            w, h = int(m.group(1)), int(m.group(2))
            if w >= 200 and h >= 200:
                return w, h
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

    # 2) dumpsys display override "real W x H" for built-in (skip scrcpy virtual)
    try:
        proc = run_adb(
            ["shell", "dumpsys", "display"],
            serial=serial,
            check=False,
            timeout=15,
        )
        text = proc.stdout or ""
        for name, w, h in _parse_override_real_sizes(text):
            if name.lower().startswith("scrcpy"):
                continue
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
        if re.search(r"\bmCurrentOrientation=[13]\b", proc.stdout or ""):
            if w < h:
                return h, w
    except AdbError:
        pass
    return w, h


def resolve_display_size_for_window(
    serial: str | None,
    window_width: int,
    window_height: int,
) -> tuple[int, int]:
    """Pick touch/video size that matches the scrcpy window (fix wrong rotation).

    If ``get_display_size`` briefly returns physical portrait while scrcpy is
    mirroring landscape, letterbox math invents a narrow pillarbox and every
    click looks \"outside video\". Prefer the scrcpy virtual display size when
    present (that is the mirrored frame). Otherwise pick the orientation that
    fills the window better among reported size and its swap.
    """
    dw, dh = get_display_size(serial)
    sc = get_scrcpy_virtual_size(serial)
    # Scrcpy encoder size is ground truth for what is drawn in the window.
    if sc is not None:
        return sc

    candidates: list[tuple[int, int]] = [(dw, dh)]
    if (dh, dw) != (dw, dh):
        candidates.append((dh, dw))

    def fill_score(size: tuple[int, int]) -> float:
        w, h = size
        if w <= 0 or h <= 0 or window_width <= 0 or window_height <= 0:
            return 0.0
        return min(window_width / w, window_height / h)

    return max(candidates, key=fill_score)


def shell(
    command: str,
    *,
    serial: str | None = None,
    check: bool = True,
    timeout: float | None = 30,
) -> subprocess.CompletedProcess[str]:
    return run_adb(["shell", command], serial=serial, check=check, timeout=timeout)
