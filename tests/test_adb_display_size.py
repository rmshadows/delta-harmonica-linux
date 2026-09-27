import re

from delta_harmonica import adb_util


SAMPLE_INPUT = """
      Viewport INTERNAL: displayId=0, uniqueId=local:1, port=131, orientation=1, logicalFrame=[0, 0, 2480, 1116], physicalFrame=[0, 0, 2480, 1116], deviceSize=[2480, 1116], isActive=[1]
"""

SAMPLE_INPUT_INACTIVE_FIRST = """
      Viewport INTERNAL: displayId=1, uniqueId=local:x, port=1, orientation=0, logicalFrame=[0, 0, 100, 100], physicalFrame=[0, 0, 100, 100], deviceSize=[100, 100], isActive=[0]
      Viewport INTERNAL: displayId=0, uniqueId=local:1, port=131, orientation=1, logicalFrame=[0, 0, 2480, 1116], physicalFrame=[0, 0, 2480, 1116], deviceSize=[2480, 1116], isActive=[1]
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
