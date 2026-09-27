from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Modifier(str, Enum):
    """Game harmonica modifiers (UI labels), not Western accidentals.

    SEMITONE = 半音 (+1 semitone)
    SHARP = 升调 (+1 octave)
    FLAT = 降调 (-1 octave)
    NATURAL = 自然音
    """

    NATURAL = "natural"
    SHARP = "sharp"  # 升调 → +octave
    FLAT = "flat"  # 降调 → -octave
    SEMITONE = "semitone"  # 半音 → +1


class PitchKey(str, Enum):
    N1 = "1"
    N2 = "2"
    N3 = "3"
    N4 = "4"
    N5 = "5"
    N6 = "6"
    N7 = "7"
    N1P = "1'"  # high 1 on the same row


# Logical UI keys that must be calibrated
UI_KEYS: tuple[str, ...] = (
    "semitone",
    "sharp",
    "natural",
    "flat",
    "note_1",
    "note_2",
    "note_3",
    "note_4",
    "note_5",
    "note_6",
    "note_7",
    "note_1p",
)

UI_KEY_LABELS: dict[str, str] = {
    "semitone": "半音",
    "sharp": "升调",
    "natural": "自然音",
    "flat": "降调",
    "note_1": "音符 1",
    "note_2": "音符 2",
    "note_3": "音符 3",
    "note_4": "音符 4",
    "note_5": "音符 5",
    "note_6": "音符 6",
    "note_7": "音符 7",
    "note_1p": "音符 1'（高音 1）",
}

PITCH_TO_UI: dict[PitchKey, str] = {
    PitchKey.N1: "note_1",
    PitchKey.N2: "note_2",
    PitchKey.N3: "note_3",
    PitchKey.N4: "note_4",
    PitchKey.N5: "note_5",
    PitchKey.N6: "note_6",
    PitchKey.N7: "note_7",
    PitchKey.N1P: "note_1p",
}

MODIFIER_TO_UI: dict[Modifier, str] = {
    Modifier.SEMITONE: "semitone",
    Modifier.SHARP: "sharp",
    Modifier.NATURAL: "natural",
    Modifier.FLAT: "flat",
}


@dataclass(frozen=True)
class Point:
    x: int
    y: int

    def as_tuple(self) -> tuple[int, int]:
        return self.x, self.y

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Point:
        return cls(x=int(data["x"]), y=int(data["y"]))


@dataclass
class Profile:
    """Key positions in **device** pixels (adb ``input`` space).

    Window size is irrelevant after calibrate: clicks on scrcpy are converted
    to device coords once and stored. On play we only need adb. If the phone
    resolution/orientation changes, ``resolve_key`` scales by current display
    size vs the size recorded at calibrate time.
    """

    name: str
    device_width: int
    device_height: int
    keys: dict[str, Point] = field(default_factory=dict)

    def require_key(self, key: str) -> Point:
        if key not in self.keys:
            raise KeyError(f"profile '{self.name}' missing key '{key}'")
        return self.keys[key]

    def resolve_key(
        self,
        key: str,
        *,
        display_width: int | None = None,
        display_height: int | None = None,
    ) -> Point:
        """Map a stored key to current display pixels (proportional scale)."""
        pt = self.require_key(key)
        dw = display_width or self.device_width
        dh = display_height or self.device_height
        if dw == self.device_width and dh == self.device_height:
            return pt
        if self.device_width <= 0 or self.device_height <= 0:
            return pt
        x = int(round(pt.x * dw / self.device_width))
        y = int(round(pt.y * dh / self.device_height))
        x = max(0, min(dw - 1, x))
        y = max(0, min(dh - 1, y))
        return Point(x, y)

    def to_dict(self) -> dict[str, Any]:
        # Also persist normalized fractions so profiles stay readable / portable
        keys_out: dict[str, Any] = {}
        for k, v in self.keys.items():
            entry = v.to_dict()
            if self.device_width > 0 and self.device_height > 0:
                entry["rx"] = round(v.x / self.device_width, 6)
                entry["ry"] = round(v.y / self.device_height, 6)
            keys_out[k] = entry
        return {
            "name": self.name,
            "device_width": self.device_width,
            "device_height": self.device_height,
            "keys": keys_out,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        dw = int(data["device_width"])
        dh = int(data["device_height"])
        keys: dict[str, Point] = {}
        for k, v in data.get("keys", {}).items():
            if not isinstance(v, dict):
                continue
            if "x" in v and "y" in v:
                keys[k] = Point.from_dict(v)
            elif "rx" in v and "ry" in v and dw > 0 and dh > 0:
                keys[k] = Point(
                    x=int(round(float(v["rx"]) * dw)),
                    y=int(round(float(v["ry"]) * dh)),
                )
        return cls(
            name=str(data["name"]),
            device_width=dw,
            device_height=dh,
            keys=keys,
        )


@dataclass(frozen=True)
class SetRegister:
    register: int  # 1..3


@dataclass(frozen=True)
class SetModifier:
    modifier: Modifier


@dataclass(frozen=True)
class PlayNote:
    pitch: PitchKey
    duration_ms: int
    modifier: Modifier
    # net octave shift from # / b count: #=1, ##=2, b=-1, bb=-2
    octaves: int = 0


@dataclass(frozen=True)
class Rest:
    duration_ms: int


@dataclass(frozen=True)
class LyricMark:
    """Lyric / phrase marker for preview highlighting (no sound)."""

    text: str


ScoreEvent = SetRegister | SetModifier | PlayNote | Rest | LyricMark


@dataclass
class Score:
    title: str
    bpm: float
    ms_beat: float
    register: int
    events: list[ScoreEvent] = field(default_factory=list)
    source: str | None = None
    lyrics: list[str] = field(default_factory=list)
    rest_scale: float = 1.0
