"""Self-check for the per-room `min_role` gate. Run: python3 test_room_access.py

Pure logic only — can_join() touches neither mongo nor livekit.
"""
from app.auth import can_join


def test_open_room():
    for role in ("member", "operator", "moderator", "admin"):
        assert can_join(role, {})                      # field absent
        assert can_join(role, {"min_role": ""})        # field empty


def test_mods_and_admins_only():
    room = {"min_role": "moderator"}
    assert can_join("admin", room)
    assert can_join("moderator", room)
    assert not can_join("operator", room)
    assert not can_join("member", room)
    assert not can_join(None, room)


def test_unknown_values_fail_closed():
    # a typo'd min_role must not open the room
    assert not can_join("member", {"min_role": "moderatr"})
    assert not can_join("moderator", {"min_role": "moderatr"})
    assert can_join("admin", {"min_role": "moderatr"})
    # an unknown *user* role has no priority at all
    assert not can_join("wizard", {"min_role": "moderator"})


if __name__ == "__main__":
    test_open_room()
    test_mods_and_admins_only()
    test_unknown_values_fail_closed()
    print("OK — 3/3")
