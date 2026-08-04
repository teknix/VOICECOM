"""Self-check for the Matrix -> internal-DB fallthrough and role matching.
Run: python3 test_matrix_fallthrough.py

Three regression guards:
 1. An MXID-shaped internal record is a ROLE CARRIER, never a password login — otherwise
    every role grant is a way in with no Matrix account (this was live once, and tested).
 2. Same rule the Zulip path learned the hard way — a rejection hint must not return
    early, or an internal-DB account with a non-MXID username is locked out.
 3. Matrix role elevation matches the FULL MXID only. Matching the localpart would let
    @ingo:evil.example inherit the local 'ingo' account's role.

Matrix and mongo are both faked — no network, no DB.
"""
import os

os.environ["ENABLE_MATRIX_AUTH"] = "true"
os.environ["MATRIX_ALLOWED_HOMESERVERS"] = "turbulent.net"

import bcrypt
from app import auth
from app.matrix import _split_mxid

PW = "correct-horse"
LOCAL_USERS = {}


class FakeUsers:
    def find_one(self, query):
        return LOCAL_USERS.get(query.get("username"))


class FakeDB:
    users = FakeUsers()


def fake_matrix(login, password):
    """Stubs only the network call — MXID parsing uses the real _split_mxid so this
    fake can't drift from the app's actual accept/reject boundary."""
    mxid, server = _split_mxid(login)
    if not mxid:
        return False, {"hint": "mxid_required"}
    if server != "turbulent.net":
        return False, {"hint": "homeserver_not_allowed", "server": server}
    if mxid == "@ingo:turbulent.net" and password == PW:
        return True, {"user_id": mxid, "full_name": "Ingo", "avatar_url": None}
    return False, None


auth.db = FakeDB()
auth.verify_matrix_credentials = fake_matrix


def test_mxid_record_is_role_only_never_a_password_login():
    """THE BACKDOOR GUARD. An MXID-shaped record carries a role for a federated user;
    it must never be usable as a local password login, or every role grant becomes a
    way in without any Matrix account. Verified live before the guard existed."""
    LOCAL_USERS.clear()
    LOCAL_USERS["@rolegrant:turbulent.net"] = {
        "_id": "x1", "username": "@rolegrant:turbulent.net", "display_name": "Role Grant",
        "role": "admin",
        "password_hash": bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode(),
    }
    # Correct local password, and Matrix would reject this user — must NOT log in.
    ok, info = auth.authenticate("@rolegrant:turbulent.net", PW)
    assert not ok, "MXID-shaped record must not accept a local password"

    # Same for an MXID on a homeserver that isn't even allowlisted.
    LOCAL_USERS["@svc:other.example"] = {
        "_id": "x9", "username": "@svc:other.example", "display_name": "Service",
        "role": "moderator",
        "password_hash": bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode(),
    }
    ok, info = auth.authenticate("@svc:other.example", PW)
    assert not ok, "disallowed-homeserver MXID must not fall back to a local password"


def test_non_mxid_local_account_still_falls_through():
    """The fallthrough main fixed for Zulip still holds for anything NOT MXID-shaped.
    'foo:' has a colon (so it reaches the Matrix path and trips mxid_required) but is
    not a valid MXID, so it must still reach the internal DB and log in."""
    LOCAL_USERS.clear()
    LOCAL_USERS["foo:"] = {
        "_id": "x5", "username": "foo:", "display_name": "Odd Name", "role": "moderator",
        "password_hash": bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode(),
    }
    ok, info = auth.authenticate("foo:", PW)
    assert ok, "non-MXID username must still fall through to the internal DB"
    assert info["role"] == "moderator"


def test_hint_still_shown_when_nothing_matches():
    LOCAL_USERS.clear()
    ok, info = auth.authenticate("@someone:evil.example", PW)
    assert not ok
    assert "evil.example" in info["error"], info

    ok, info = auth.authenticate("@bad:", PW)
    assert not ok
    assert "full Matrix ID" in info["error"], info


def test_role_matches_full_mxid_only():
    """The escalation guard: a local 'ingo' must NOT elevate @ingo:turbulent.net."""
    LOCAL_USERS.clear()
    LOCAL_USERS["ingo"] = {"_id": "x2", "username": "ingo", "display_name": "Local Ingo",
                           "role": "admin", "password_hash": "unused"}
    ok, info = auth.authenticate("@ingo:turbulent.net", PW)
    assert ok
    assert info["role"] == "member", "localpart must NOT grant the local account's role"

    # ...but a record keyed on the full MXID does elevate.
    LOCAL_USERS["@ingo:turbulent.net"] = {"_id": "x3", "username": "@ingo:turbulent.net",
                                          "display_name": "Ingo", "role": "admin",
                                          "password_hash": "unused"}
    ok, info = auth.authenticate("@ingo:turbulent.net", PW)
    assert ok and info["role"] == "admin"
    assert info["user_id"] == "@ingo:turbulent.net"


if __name__ == "__main__":
    test_mxid_record_is_role_only_never_a_password_login()
    test_non_mxid_local_account_still_falls_through()
    test_hint_still_shown_when_nothing_matches()
    test_role_matches_full_mxid_only()
    print("OK — 4/4")
