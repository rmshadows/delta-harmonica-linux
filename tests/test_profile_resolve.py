from delta_harmonica.models import Point, Profile


def test_resolve_key_same_size():
    p = Profile(
        name="t",
        device_width=2480,
        device_height=1116,
        keys={"note_1": Point(620, 900)},
    )
    assert p.resolve_key("note_1") == Point(620, 900)
    assert p.resolve_key("note_1", display_width=2480, display_height=1116) == Point(
        620, 900
    )


def test_resolve_key_scales():
    p = Profile(
        name="t",
        device_width=2480,
        device_height=1116,
        keys={"note_1": Point(1240, 558)},  # center
    )
    got = p.resolve_key("note_1", display_width=1240, display_height=558)
    assert got == Point(620, 279)


def test_profile_roundtrip_keeps_rx_ry():
    p = Profile(
        name="t",
        device_width=1000,
        device_height=500,
        keys={"semitone": Point(250, 400)},
    )
    data = p.to_dict()
    assert data["keys"]["semitone"]["rx"] == 0.25
    assert data["keys"]["semitone"]["ry"] == 0.8
    p2 = Profile.from_dict(data)
    assert p2.keys["semitone"] == Point(250, 400)


def test_profile_from_rx_only():
    p = Profile.from_dict(
        {
            "name": "t",
            "device_width": 2000,
            "device_height": 1000,
            "keys": {"flat": {"rx": 0.5, "ry": 0.25}},
        }
    )
    assert p.keys["flat"] == Point(1000, 250)