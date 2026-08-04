"""Self-check for the Zulip -> internal-DB fallthrough. Run: python3 test_auth_fallthrough.py

Regression guard: with Zulip auth on, Zulip 400s any non-email username, which used to
return immediately and lock every internal-DB account with a plain username out entirely.
Zulip and mongo are both faked — no network, no DB.
"""
import os

os.environ["ENABLE_ZULIP_AUTH"] = "true"

import bcrypt
from app import auth

PW = "correct-horse"
LOCAL_USERS = {
    "local-admin": {
        "_id": "abc123",
        "username": "local-admin",
        "display_name": "Local Admin",
        "role": "admin",
        "password_hash": bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode(),
    }
}


class FakeUsers:
    def find_one(self, query):
        return LOCAL_USERS.get(query.get("username"))


class FakeDB:
    users = FakeUsers()


def fake_zulip(username, password):
    """Mirrors the real thing: Zulip rejects non-email usernames with a 400."""
    if "@" not in username:
        return False, {"hint": "email_required"}
    if username == "zuser@example.com" and password == PW:
        return True, {"user_id": "z1", "full_name": "Z User", "avatar_url": None,
                      "is_admin": False, "is_owner": False, "is_moderator": True}
    return False, None


auth.db = FakeDB()
auth.verify_zulip_credentials = fake_zulip


def test_internal_user_with_plain_username_can_log_in():
    ok, info = auth.authenticate("local-admin", PW)
    assert ok, "internal-DB account must survive Zulip's email_required rejection"
    assert info["role"] == "admin"
    assert info["display_name"] == "Local Admin"


def test_hint_still_shown_when_nothing_matches():
    # A real Zulip user who typed their bare username still gets the useful message.
    ok, info = auth.authenticate("zuser", PW)
    assert not ok
    assert "full email address" in info["error"]
    # ...and so does an internal user with the wrong password (no account enumeration).
    ok, info = auth.authenticate("local-admin", "wrong")
    assert not ok
    assert "full email address" in info["error"]


def test_zulip_path_unchanged():
    ok, info = auth.authenticate("zuser@example.com", PW)
    assert ok and info["role"] == "moderator" and info["user_id"] == "z1"
    ok, info = auth.authenticate("nobody@example.com", PW)
    assert not ok and info is None


if __name__ == "__main__":
    test_internal_user_with_plain_username_can_log_in()
    test_hint_still_shown_when_nothing_matches()
    test_zulip_path_unchanged()
    print("OK — 3/3")
