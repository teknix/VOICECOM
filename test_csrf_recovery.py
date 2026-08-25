"""Self-check for CSRF login recovery. Run: python3 test_csrf_recovery.py

Regression guard for the 2026-08-24 report "Bad Request / The CSRF session token
is missing" on the login page.

A successful login calls session.clear() (app/auth.py), which drops Flask-WTF's
csrf_token along with the rest of the session. A login form that was NOT freshly
fetched -- back button, bfcache, restored tab -- then posts a token against a
session that carries none, and Flask-WTF dead-ends the user on a bare 400 page
with no way forward. The handler in app/__init__.py re-renders the login form
(which mints a fresh token) or, if the session is already authenticated, sends
the user to the app.

Mongo is faked out; no network, no DB.
"""
import os
import re
import sys

os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-not-a-real-key")
os.environ.setdefault("LIVEKIT_HOST", "wss://livekit.invalid")

from app import models

models.init_db = lambda app: None  # index creation would need a live mongo

from app import create_app
from app.auth import limiter

limiter.enabled = False  # /auth/login is 5/min and the limit counts GETs

app = create_app()
app.config["SERVER_NAME"] = "voicecom.test"


@app.post("/_csrf_probe")
def _csrf_probe():  # a protected non-login route, to prove the handler is scoped
    return "ok"


TOKEN_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def fresh_token(client):
    r = client.get("/auth/login")
    assert r.status_code == 200, f"login page returned {r.status_code}"
    m = TOKEN_RE.search(r.get_data(as_text=True))
    assert m, "login page rendered no csrf_token field"
    return m.group(1)


def drop_session_csrf(client, **extra):
    """Reproduce session.clear(): the cookie survives, csrf_token does not."""
    with client.session_transaction() as s:
        s.pop("csrf_token", None)
        s.update(extra)


def test_stale_form_gets_a_usable_login_page_back():
    client = app.test_client()
    token = fresh_token(client)
    drop_session_csrf(client)

    r = client.post("/auth/login", data={"csrf_token": token,
                                         "username": "someone",
                                         "password": "whatever"})
    body = r.get_data(as_text=True)
    assert r.status_code == 400, f"expected 400, got {r.status_code}"
    assert "The CSRF session token is missing" not in body, \
        "still the raw Flask-WTF dead-end page"
    assert "Your session expired" in body, "no recovery message rendered"
    assert TOKEN_RE.search(body), "recovery page carries no fresh csrf_token"


def test_recovery_page_token_actually_works():
    client = app.test_client()
    token = fresh_token(client)
    drop_session_csrf(client)

    r = client.post("/auth/login", data={"csrf_token": token,
                                         "username": "someone",
                                         "password": "whatever"})
    m = TOKEN_RE.search(r.get_data(as_text=True))
    assert m, "the rejected POST returned no login form to retry from"
    new_token = m.group(1)
    assert new_token != token, "recovery page reused the dead token"

    r2 = client.post("/auth/login", data={"csrf_token": new_token,
                                          "username": "someone",
                                          "password": "whatever"})
    body2 = r2.get_data(as_text=True)
    # Which credential error comes back depends on the deployment's auth backend,
    # so assert only that CSRF let the request through to the view.
    assert r2.status_code == 200, f"retry rejected with {r2.status_code}"
    assert "The CSRF session token is missing" not in body2
    assert "Your session expired" not in body2, "fresh token was rejected too"


def test_already_logged_in_goes_to_the_app():
    client = app.test_client()
    token = fresh_token(client)
    # The reported case: login succeeded, session.clear() ran, user hit Back.
    drop_session_csrf(client, user_id="u1", display_name="U", role="member")

    r = client.post("/auth/login", data={"csrf_token": token,
                                         "username": "someone",
                                         "password": "whatever"})
    assert r.status_code == 302, f"expected redirect, got {r.status_code}"
    assert r.headers["Location"].endswith("/"), r.headers["Location"]


def test_handler_is_scoped_to_login():
    client = app.test_client()
    fresh_token(client)
    drop_session_csrf(client)

    r = client.post("/_csrf_probe", data={"csrf_token": "anything"})
    body = r.get_data(as_text=True)
    assert r.status_code == 400, f"expected 400, got {r.status_code}"
    assert "Your session expired" not in body, \
        "login recovery leaked onto a non-login route"


if __name__ == "__main__":
    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # a crash is a failure, and must not abort the run
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
