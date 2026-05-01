def test_login_success_sets_session(client):
    resp = client.post("/auth/login", data={
        "display_name": "Alice",
        "passphrase": "testpass",
    }, follow_redirects=False)
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" in sess
        assert sess["display_name"] == "Alice"
        assert sess["role"] == "member"


def test_login_wrong_passphrase(client):
    resp = client.post("/auth/login", data={
        "display_name": "Alice",
        "passphrase": "wrong",
    })
    assert resp.status_code == 200
    assert b"Invalid passphrase" in resp.data


def test_login_session_fixation(client):
    # pre-login session should differ from post-login session id
    with client.session_transaction() as sess:
        sess["pre_login"] = "marker"

    client.post("/auth/login", data={"display_name": "Alice", "passphrase": "testpass"})

    with client.session_transaction() as sess:
        assert "pre_login" not in sess  # session.clear() wiped old data


def test_login_rate_limit(app):
    # Flask-Limiter with memory storage — reset between tests
    from flask_limiter import Limiter
    test_client = app.test_client()
    for _ in range(5):
        test_client.post("/auth/login", data={"display_name": "X", "passphrase": "wrong"})
    resp = test_client.post("/auth/login", data={"display_name": "X", "passphrase": "wrong"})
    assert resp.status_code == 429


def test_protected_route_redirects_without_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_api_route_returns_401_without_login(client):
    resp = client.get("/api/me")
    assert resp.status_code == 401
