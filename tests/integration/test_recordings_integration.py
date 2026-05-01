from unittest.mock import patch


def test_start_recording(mod_client, mock_mongo, sample_room):
    with patch("app.recordings.lk.start_egress", return_value="egress-001"):
        resp = mod_client.post("/api/recordings/start", json={"room_id": sample_room})
    assert resp.status_code == 201
    assert resp.get_json()["egress_id"] == "egress-001"
    rec = mock_mongo.recordings.find_one({"_id": "egress-001"})
    assert rec is not None
    assert rec["status"] == "active"


def test_recording_orphan_compensation(mod_client, mock_mongo, sample_room):
    stop_calls = []
    def fake_stop(egress_id):
        stop_calls.append(egress_id)

    with patch("app.recordings.lk.start_egress", return_value="egress-orphan"), \
         patch("app.recordings.db") as mock_db, \
         patch("app.recordings.lk.stop_egress", side_effect=fake_stop):
        mock_db.recordings.find_one.return_value = None
        mock_db.recordings.insert_one.side_effect = Exception("DB write failed")
        resp = mod_client.post("/api/recordings/start", json={"room_id": sample_room})

    assert resp.status_code == 500
    assert "egress-orphan" in stop_calls


def test_duplicate_recording_returns_409(mod_client, mock_mongo, sample_room):
    mock_mongo.recordings.insert_one({
        "_id": "egress-existing",
        "room_id": sample_room,
        "status": "active",
        "started_by": "mod-001",
    })
    with patch("app.recordings.lk.start_egress", return_value="egress-new"):
        resp = mod_client.post("/api/recordings/start", json={"room_id": sample_room})
    assert resp.status_code == 409


def test_stop_recording(mod_client, mock_mongo):
    mock_mongo.recordings.insert_one({
        "_id": "egress-stop",
        "room_id": "sector-test",
        "status": "active",
        "started_by": "mod-001",
    })
    with patch("app.recordings.lk.stop_egress"):
        resp = mod_client.post("/api/recordings/stop", json={"egress_id": "egress-stop"})
    assert resp.status_code == 200
    rec = mock_mongo.recordings.find_one({"_id": "egress-stop"})
    assert rec["status"] == "complete"


def test_member_cannot_start_recording(authed_client, sample_room):
    resp = authed_client.post("/api/recordings/start", json={"room_id": sample_room})
    assert resp.status_code == 403


def test_download_path_traversal_blocked(mod_client, mock_mongo, tmp_path):
    safe_file = tmp_path / "sector-test_1234.mp4"
    safe_file.write_bytes(b"fake mp4")
    mock_mongo.recordings.insert_one({
        "_id": "egress-dl",
        "room_id": "sector-test",
        "status": "complete",
        "file_path": "../../etc/passwd",  # attacker-controlled
        "started_by": "mod-001",
    })
    import os
    with patch("app.recordings.os.path.join", side_effect=os.path.join), \
         patch("app.recordings.os.path.exists", return_value=False):
        resp = mod_client.get("/api/recordings/egress-dl/download")
    assert resp.status_code == 404  # basename("../../etc/passwd") = "passwd", doesn't exist
