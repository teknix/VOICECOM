"""Self-check for the Zulip role mapping. Run: python3 test_zulip_role_mapping.py

Regression guard: Zulip's user object exposes is_admin / is_owner / is_guest but has
NO is_moderator field (verified against the API docs; wtp is Zulip 11.5, feature level
421). Reading `is_moderator` therefore always yielded False and every Zulip moderator
signed in as a plain member. Pure mapping only — no network.
"""
from app.zulip import _profile_from_user
from app.auth import ROLE_PRIORITY


def app_role(profile):
    """The mapping app/auth.py:authenticate() applies to a Zulip profile."""
    if profile.get("is_admin") or profile.get("is_owner"):
        return "admin"
    if profile.get("is_moderator"):
        return "moderator"
    return "member"


def user(role, **flags):
    u = {"user_id": 7, "full_name": "Z", "avatar_url": None}
    if role is not None:
        u["role"] = role
    u.update(flags)
    return u


def test_role_integers():
    assert app_role(_profile_from_user(user(100), 0, "e")) == "admin"      # owner
    assert app_role(_profile_from_user(user(200), 0, "e")) == "admin"
    assert app_role(_profile_from_user(user(300), 0, "e")) == "moderator"  # the bug
    assert app_role(_profile_from_user(user(400), 0, "e")) == "member"
    assert app_role(_profile_from_user(user(600), 0, "e")) == "member"     # guest


def test_booleans_still_honoured():
    # Zulip does send these; they must keep working alongside `role`.
    assert app_role(_profile_from_user(user(400, is_admin=True), 0, "e")) == "admin"
    assert app_role(_profile_from_user(user(400, is_owner=True), 0, "e")) == "admin"
    # and a server that ever grows an is_moderator field is honoured too
    assert app_role(_profile_from_user(user(400, is_moderator=True), 0, "e")) == "moderator"


def test_no_role_field_is_not_an_error():
    p = _profile_from_user(user(None), 42, "who@example.com")
    assert app_role(p) == "member"
    assert p["user_id"] == "7"
    assert _profile_from_user({}, 42, "who@example.com")["user_id"] == "42"


def test_moderator_clears_the_tea_time_gate():
    from app.auth import can_join
    room = {"min_role": "moderator"}
    assert can_join(app_role(_profile_from_user(user(300), 0, "e")), room)
    assert not can_join(app_role(_profile_from_user(user(400), 0, "e")), room)


if __name__ == "__main__":
    test_role_integers()
    test_booleans_still_honoured()
    test_no_role_field_is_not_an_error()
    test_moderator_clears_the_tea_time_gate()
    print("OK — 4/4")
