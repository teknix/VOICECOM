import os
import importlib
import pytest


def test_resolve_role_privileged():
    os.environ["PRIVILEGED_USERS"] = "teknix:admin,co-pilot:moderator"
    import app.auth as auth_mod
    importlib.reload(auth_mod)
    assert auth_mod.resolve_role("teknix") == "admin"
    assert auth_mod.resolve_role("co-pilot") == "moderator"


def test_resolve_role_unknown_is_member():
    os.environ["PRIVILEGED_USERS"] = "teknix:admin"
    import app.auth as auth_mod
    importlib.reload(auth_mod)
    assert auth_mod.resolve_role("someone") == "member"
    assert auth_mod.resolve_role("Teknix") == "member"  # case-sensitive
    assert auth_mod.resolve_role("TEKNIX") == "member"


def test_empty_passphrase_raises():
    orig = os.environ.pop("ACCESS_PASSPHRASE", None)
    os.environ["ACCESS_PASSPHRASE"] = ""
    with pytest.raises(RuntimeError, match="ACCESS_PASSPHRASE"):
        import app.auth as auth_mod
        importlib.reload(auth_mod)
    if orig:
        os.environ["ACCESS_PASSPHRASE"] = orig
    else:
        os.environ["ACCESS_PASSPHRASE"] = "testpass"


def test_whitespace_passphrase_raises():
    orig = os.environ["ACCESS_PASSPHRASE"]
    os.environ["ACCESS_PASSPHRASE"] = "   "
    with pytest.raises(RuntimeError, match="ACCESS_PASSPHRASE"):
        import app.auth as auth_mod
        importlib.reload(auth_mod)
    os.environ["ACCESS_PASSPHRASE"] = orig


def test_login_uses_hmac_not_equality(client):
    from unittest.mock import patch
    import hmac
    # Use a unique IP to avoid triggering the shared rate-limit bucket from
    # earlier tests in the session (limiter is module-level, storage persists).
    with patch("hmac.compare_digest", wraps=hmac.compare_digest) as mock_cd:
        client.post("/auth/login",
                    data={"display_name": "X", "passphrase": "testpass"},
                    environ_base={"REMOTE_ADDR": "10.0.0.1"})
    assert mock_cd.called, "hmac.compare_digest was never called"
