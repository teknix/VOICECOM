"""Chat file share: upload limits, 4-hour expiry, safe serving."""
import io
from datetime import timedelta

import pytest

from app import chatfiles
from app.utils import now_utc


def login(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
        sess["display_name"] = "Tester"
        sess["role"] = "member"


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch, mock_mongo):
    monkeypatch.setattr(chatfiles, "FILES_DIR", str(tmp_path))
    mock_mongo.rooms.insert_one({"_id": "front-desk", "display_name": "Front desk", "active": True})
    return tmp_path


def upload(client, data=b"hello", name="notes.txt"):
    return client.post("/api/rooms/front-desk/files", data={"file": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def test_signed_out_cannot_upload(client):
    assert upload(client).status_code == 401


def test_upload_returns_link_that_expires_in_4_hours(client, files_dir, mock_mongo):
    login(client)
    r = upload(client)
    assert r.status_code == 201
    j = r.get_json()
    assert j["url"] == f"/files/{j['id']}/notes.txt" and j["size"] == 5
    doc = mock_mongo.chat_files.find_one({"_id": j["id"]})
    assert timedelta(hours=3, minutes=59) < doc["expires_at"] - doc["created_at"] <= timedelta(hours=4)
    got = client.get(j["url"])
    assert got.status_code == 200 and got.data == b"hello"
    assert "attachment" in got.headers["Content-Disposition"]  # text/html etc. never render inline
    assert got.headers["X-Content-Type-Options"] == "nosniff"


def test_unknown_channel_and_empty_file(client):
    login(client)
    assert client.post("/api/rooms/nope/files", data={"file": (io.BytesIO(b"x"), "a")},
                       content_type="multipart/form-data").status_code == 404
    assert upload(client, b"").status_code == 413


def test_over_200_mb_refused(client, monkeypatch):
    login(client)
    monkeypatch.setattr(chatfiles, "MAX_FILE_BYTES", 10)
    assert upload(client, b"x" * 11).status_code == 413


def test_expired_link_says_so_and_file_is_removed(client, files_dir, mock_mongo):
    login(client)
    j = upload(client).get_json()
    mock_mongo.chat_files.update_one({"_id": j["id"]}, {"$set": {"expires_at": now_utc() - timedelta(seconds=1)}})
    r = client.get(j["url"])
    assert r.status_code == 410 and b"expired" in r.data
    assert not (files_dir / j["id"]).exists()
    assert mock_mongo.chat_files.find_one({"_id": j["id"]}) is None


def test_names_are_made_safe():
    assert chatfiles.safe_name("../../etc/passwd") == "passwd"
    assert chatfiles.safe_name(".env") == "env"
    assert chatfiles.safe_name("") == "file"
