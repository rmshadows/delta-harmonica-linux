import re

from delta_harmonica import adb_util


SAMPLE_INPUT = """
      Viewport INTERNAL: displayId=0, uniqueId=local:1, port=131, orientation=1, logicalFrame=[0, 0, 2480, 1116], physicalFrame=[0, 0, 2480, 1116], deviceSize=[2480, 1116], isActive=[1]
"""

SAMPLE_INPUT_INACTIVE_FIRST = """
      Viewport INTERNAL: displayId=1, uniqueId=local:x, port=1, orientation=0, logicalFrame=[0, 0, 100, 100], physicalFrame=[0, 0, 100, 100], deviceSize=[100, 100], isActive=[0]
      Viewport INTERNAL: displayId=0, uniqueId=local:1, port=131, orientation=1, logicalFrame=[0, 0, 2480, 1116], physicalFrame=[0, 0, 2480, 1116], deviceSize=[2480, 1116], isActive=[1]
"""

SAMPLE_DISPLAY = """
    mOverrideDisplayInfo=DisplayInfo{"内置屏幕", displayId 0, real 1116 x 2480, rotation 0
    mOverrideDisplayInfo=DisplayInfo{"scrcpy", displayId 16, FLAG_PRIVATE, real 2480 x 1116, rotation 0
"""


def test_viewport_regex_active():
    m = re.search(
        r"Viewport INTERNAL:.*?logicalFrame="
        r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]"
        r".*?isActive=\[([01])\]",
        SAMPLE_INPUT,
        re.DOTALL,
    )
    assert m is not None
    assert m.group(5) == "1"
    assert int(m.group(3)) - int(m.group(1)) == 2480
    assert int(m.group(4)) - int(m.group(2)) == 1116


def test_get_display_size_from_input_dumpsys(monkeypatch):
    class FakeProc:
        stdout = SAMPLE_INPUT_INACTIVE_FIRST
        returncode = 0

    def fake_run_adb(args, **kwargs):
        assert args[:2] == ["shell", "dumpsys"]
        return FakeProc()

    monkeypatch.setattr(adb_util, "run_adb", fake_run_adb)
    assert adb_util.get_display_size("serial") == (2480, 1116)


def test_get_scrcpy_virtual_size(monkeypatch):
    class FakeProc:
        stdout = SAMPLE_DISPLAY
        returncode = 0

    monkeypatch.setattr(adb_util, "run_adb", lambda *a, **k: FakeProc())
    assert adb_util.get_scrcpy_virtual_size("s") == (2480, 1116)


def test_resolve_swaps_portrait_when_scrcpy_is_landscape(monkeypatch):
    """First-calibrate bug: adb reports 1116x2480 while scrcpy mirrors 2480x1116."""
    monkeypatch.setattr(adb_util, "get_display_size", lambda serial=None: (1116, 2480))
    monkeypatch.setattr(
        adb_util, "get_scrcpy_virtual_size", lambda serial=None: (2480, 1116)
    )
    assert adb_util.resolve_display_size_for_window(None, 1920, 1043) == (2480, 1116)


def test_resolve_keeps_landscape_when_already_correct(monkeypatch):
    monkeypatch.setattr(adb_util, "get_display_size", lambda serial=None: (2480, 1116))
    monkeypatch.setattr(
        adb_util, "get_scrcpy_virtual_size", lambda serial=None: (2480, 1116)
    )
    assert adb_util.resolve_display_size_for_window(None, 1920, 1043) == (2480, 1116)


def test_resolve_fill_fallback_without_scrcpy(monkeypatch):
    monkeypatch.setattr(adb_util, "get_display_size", lambda serial=None: (1116, 2480))
    monkeypatch.setattr(adb_util, "get_scrcpy_virtual_size", lambda serial=None: None)
    # Wide window → prefer landscape orientation that fills better
    assert adb_util.resolve_display_size_for_window(None, 1920, 1043) == (2480, 1116)
