from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom


@dataclass(frozen=True)
class ContentMapping:
    """Map window client-area coordinates to device pixels (letterbox-aware)."""

    window: Rect
    device_width: int
    device_height: int
    content: Rect  # absolute screen coords of fitted video
    scale: float

    def window_abs_to_device(self, abs_x: int, abs_y: int) -> tuple[int, int] | None:
        if not self.content.contains(abs_x, abs_y):
            return None
        rel_x = abs_x - self.content.x
        rel_y = abs_y - self.content.y
        dx = int(rel_x / self.scale)
        dy = int(rel_y / self.scale)
        dx = max(0, min(self.device_width - 1, dx))
        dy = max(0, min(self.device_height - 1, dy))
        return dx, dy


def fit_content_rect(
    window: Rect,
    device_width: int,
    device_height: int,
) -> ContentMapping:
    """Contain-fit device frame into window (scrcpy-style letterboxing)."""
    if device_width <= 0 or device_height <= 0:
        raise ValueError("invalid device size")
    if window.width <= 0 or window.height <= 0:
        raise ValueError("invalid window size")

    scale = min(window.width / device_width, window.height / device_height)
    content_w = int(round(device_width * scale))
    content_h = int(round(device_height * scale))
    offset_x = window.x + (window.width - content_w) // 2
    offset_y = window.y + (window.height - content_h) // 2
    content = Rect(offset_x, offset_y, content_w, content_h)
    return ContentMapping(
        window=window,
        device_width=device_width,
        device_height=device_height,
        content=content,
        scale=scale,
    )
