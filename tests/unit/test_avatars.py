from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app import avatars

NAME = "2/4275d6f140433802b3cf47dfa695b35f1e4bc662.png"
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64


def _resp(status=200, ctype="image/png", body=PNG):
    r = MagicMock()
    r.status_code = status
    r.headers = {"content-type": ctype}
    r.content = body
    return r


@pytest.fixture(autouse=True)
def zulip_url(monkeypatch):
    monkeypatch.setattr("app.zulip.ZULIP_URL", "https://zulip.test")


def test_invalid_names_never_fetch():
    with patch("app.avatars.requests.get") as get:
        for bad in ["../etc/passwd", "2/abc.png", "2/" + "a" * 40 + ".svg",
                    "x/" + "a" * 40 + ".png", "2/" + "a" * 40 + ".png/../../x"]:
            assert avatars.get_avatar(bad) is None
        get.assert_not_called()


def test_first_use_fetches_then_serves_from_store(mock_mongo):
    with patch("app.avatars.requests.get", return_value=_resp()) as get:
        assert avatars.get_avatar(NAME) == (PNG, "image/png")
        assert avatars.get_avatar(NAME) == (PNG, "image/png")
    get.assert_called_once_with("https://zulip.test/user_avatars/" + NAME, timeout=5)
    assert mock_mongo.avatars.find_one({"_id": NAME})["content_type"] == "image/png"


def test_miss_is_remembered_then_retried_after_ttl(mock_mongo):
    with patch("app.avatars.requests.get", return_value=_resp(status=404)) as get:
        assert avatars.get_avatar(NAME) is None
        assert avatars.get_avatar(NAME) is None
        assert get.call_count == 1
        stale = datetime.now(timezone.utc) - avatars.MISS_TTL - timedelta(seconds=1)
        mock_mongo.avatars.update_one({"_id": NAME}, {"$set": {"missing_at": stale}})
        assert avatars.get_avatar(NAME) is None
        assert get.call_count == 2


def test_non_image_and_oversize_rejected():
    for r in [_resp(ctype="text/html"), _resp(body=b"x" * (avatars.MAX_BYTES + 1))]:
        with patch("app.avatars.requests.get", return_value=r):
            assert avatars._fetch(NAME) is None


def test_fetch_error_is_a_miss():
    with patch("app.avatars.requests.get", side_effect=OSError("boom")):
        assert avatars.get_avatar(NAME) is None


def test_prefetch_only_zulip_relative_and_strips_query():
    with patch("app.avatars.get_avatar") as ga:
        avatars.prefetch(None)
        avatars.prefetch("https://secure.gravatar.com/avatar/abc")
        ga.assert_not_called()
        avatars.prefetch("/user_avatars/" + NAME + "?version=3")
        ga.assert_called_once_with(NAME)


def test_prefetch_never_raises():
    with patch("app.avatars.get_avatar", side_effect=RuntimeError("db down")):
        avatars.prefetch("/user_avatars/" + NAME)


def test_route_requires_login(client):
    resp = client.get("/user_avatars/" + NAME)
    assert resp.status_code == 302


def test_route_hit_is_cacheable_forever(authed_client):
    with patch("app.avatars.requests.get", return_value=_resp()):
        resp = authed_client.get("/user_avatars/" + NAME + "?version=2")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert resp.data == PNG
    assert "immutable" in resp.headers["Cache-Control"]


def test_route_miss_is_404_with_short_cache(authed_client):
    with patch("app.avatars.requests.get", return_value=_resp(status=404)):
        resp = authed_client.get("/user_avatars/" + NAME)
    assert resp.status_code == 404
    assert resp.headers["Cache-Control"] == "private, max-age=600"
