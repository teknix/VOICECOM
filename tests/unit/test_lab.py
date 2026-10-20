"""Owner's phone lab at /teknix: allowlist-only, own LiveKit room, logs saved per run."""
import jwt as pyjwt
import pytest


def login(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["display_name"] = "Tester"
        sess["role"] = "member"


@pytest.fixture(autouse=True)
def lab_env(monkeypatch):
    monkeypatch.setenv("LAB_USER_IDS", "1378, 42")


def test_signed_out_goes_to_login(client):
    r = client.get("/teknix")
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_not_on_list_gets_404(client):
    login(client, "user-001")
    assert client.get("/teknix").status_code == 404
    assert client.post("/teknix/token", json={}).status_code == 404
    assert client.post("/teknix/log", json={"run": "x", "events": []}).status_code == 404


def test_empty_list_lets_nobody_in(client, monkeypatch):
    monkeypatch.setenv("LAB_USER_IDS", "")
    login(client, 1378)
    assert client.get("/teknix").status_code == 404


def test_listed_user_gets_page(client):
    login(client, 1378)                      # Zulip ids arrive as ints
    r = client.get("/teknix")
    assert r.status_code == 200
    assert b"Phone lab" in r.data and b"lab.js" in r.data


def test_token_is_for_lab_room_with_per_device_identity(client):
    login(client, "42")
    a = client.post("/teknix/token", json={"device": "phone<script>"}).get_json()
    b = client.post("/teknix/token", json={"device": "phone"}).get_json()
    claims = pyjwt.decode(a["token"], options={"verify_signature": False})
    assert claims["video"]["room"] == "lab-teknix" and claims["video"]["roomJoin"] is True
    assert a["identity"].startswith("42~phonescript~")
    assert a["identity"] != b["identity"]    # two devices never kick each other


def test_log_saved_and_updated_per_run(client, mock_mongo):
    login(client, 1378)
    r = client.post("/teknix/log", json={"run": "run1", "device": "phone", "settings": {"wakelock": True},
                                         "events": ["a", "b"]})
    assert r.status_code == 200
    client.post("/teknix/log", json={"run": "run1", "device": "phone", "events": ["a", "b", "c"]})
    doc = mock_mongo.lab_logs.find_one({"_id": "run1"})
    assert doc["events"] == ["a", "b", "c"] and doc["user_id"] == 1378
    assert client.post("/teknix/log", json={"run": "", "events": []}).status_code == 400
