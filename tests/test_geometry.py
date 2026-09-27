from delta_harmonica.geometry import Rect, fit_content_rect


def test_letterbox_horizontal():
    # Window wider than device aspect → pillarbox
    window = Rect(100, 50, 2000, 500)
    # device 1000x500 → scale = min(2, 1) = 1 → content 1000x500 centered
    m = fit_content_rect(window, 1000, 500)
    assert m.scale == 1.0
    assert m.content.width == 1000
    assert m.content.height == 500
    assert m.content.x == 100 + 500  # (2000-1000)/2 = 500 offset
    assert m.content.y == 50

    mid = m.window_abs_to_device(100 + 500 + 100, 50 + 100)
    assert mid == (100, 100)


def test_outside_returns_none():
    # Wider window → horizontal letterbox gutters
    window = Rect(0, 0, 200, 50)
    m = fit_content_rect(window, 50, 50)
    assert m.content.x > 0
    assert m.window_abs_to_device(0, 0) is None
    assert m.window_abs_to_device(-1, -1) is None
    inside = m.window_abs_to_device(m.content.x + 10, m.content.y + 10)
    assert inside == (10, 10)


def test_landscape_phone_fills_wide_window():
    """Rotated game UI 2480x1116 in 2560x1362 window ≈ full width (not portrait pillarbox)."""
    window = Rect(0, 115, 2560, 1362)
    m = fit_content_rect(window, 2480, 1116)
    assert m.content.width >= 2500
    # Left/right gutters tiny; center click maps near device center
    mid = m.window_abs_to_device(1280, 115 + 681)
    assert mid is not None
    assert 1100 < mid[0] < 1400


def test_portrait_wm_in_wide_window_is_narrow_pillarbox():
    """Bug regress: using physical 1116x2480 makes a ~613px strip — easy to 'miss'."""
    window = Rect(0, 115, 2560, 1362)
    m = fit_content_rect(window, 1116, 2480)
    assert m.content.width < 700
    # Click on left side of scrcpy (still on visible landscape video) → rejected
    assert m.window_abs_to_device(200, 700) is None
