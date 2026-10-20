"""A user's Zulip key lives server-side only, from login until logout."""
from datetime import timedelta
from unittest import mock

from app import zulipkeys
from app.utils import now_utc


def zulip_login(client, monkeypatch):
    import app.auth as auth
    monkeypatch.setattr(auth, "ENABLE_ZULIP_AUTH", True)
    profile = {"user_id": "77", "full_name": "Zed", "avatar_url": None, "zulip_role": 400,
               "is_admin": False, "is_owner": False, "is_moderator": False,
               "_auth": ("zed@example.com", "SECRETKEY123")}
    with mock.patch.object(auth, "verify_zulip_credentials", return_value=(True, profile)):
        return client.post("/auth/login", data={"username": "zed@example.com", "password": "pw"})


def test_key_kept_server_side_and_dropped_at_logout(client, monkeypatch, mock_mongo):
    r = zulip_login(client, monkeypatch)
    assert r.status_code == 302
    assert b"SECRETKEY123" not in (r.headers.get("Set-Cookie") or "").encode()
    with client.session_transaction() as s:
        sid = s["zk"]
        assert "SECRETKEY123" not in repr(dict(s))
    assert mock_mongo.zulip_keys.find_one({"_id": sid})["api_key"] == "SECRETKEY123"
    client.get("/auth/logout")
    assert mock_mongo.zulip_keys.count_documents({}) == 0


def test_second_login_replaces_the_key(client, monkeypatch, mock_mongo):
    zulip_login(client, monkeypatch)
    zulip_login(client, monkeypatch)
    assert mock_mongo.zulip_keys.count_documents({}) == 1


def test_abandoned_key_expires(app, mock_mongo):
    mock_mongo.zulip_keys.insert_one({"_id": "old", "email": "a", "api_key": "k",
                                      "created_at": now_utc() - zulipkeys.MAX_AGE - timedelta(minutes=1)})
    mock_mongo.zulip_keys.insert_one({"_id": "new", "email": "b", "api_key": "k", "created_at": now_utc()})
    zulipkeys.purge_stale()
    assert [d["_id"] for d in mock_mongo.zulip_keys.find()] == ["new"]
