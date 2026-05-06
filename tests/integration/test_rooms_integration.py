from unittest.mock import patch


def test_token_fetches_mode_from_db(authed_client, mock_mongo, sample_room):
    mock_mongo.rooms.update_one({"_id": sample_room}, {"$set": {"mode": "broadcast"}})
    resp = authed_client.post("/api/token", json={"room_id": sample_room})
    assert resp.status_code == 200
    assert "token" in resp.get_json()


def test_token_unknown_room_returns_404(authed_client):
    resp = authed_client.post("/api/token", json={"room_id": "no-such-room"})
    assert resp.status_code == 404


def test_mode_toggle_livekit_first_db_unchanged_on_livekit_failure(mod_client, mock_mongo, sample_room):
    with patch("app.rooms.lk.update_room_metadata", side_effect=Exception("LK down")):
        resp = mod_client.post(f"/api/rooms/{sample_room}/mode", json={"mode": "broadcast"})
    assert resp.status_code == 502
    room = mock_mongo.rooms.find_one({"_id": sample_room})
    assert room["mode"] == "discussion"  # DB was NOT updated


def test_mode_toggle_updates_db_on_success(mod_client, mock_mongo, sample_room):
    with patch("app.rooms.lk.update_room_metadata"):
        resp = mod_client.post(f"/api/rooms/{sample_room}/mode", json={"mode": "broadcast"})
    assert resp.status_code == 200
    room = mock_mongo.rooms.find_one({"_id": sample_room})
    assert room["mode"] == "broadcast"


def test_presenter_grant_updates_db(mod_client, mock_mongo, sample_room):
    with patch("app.rooms.lk.update_participant"):
        resp = mod_client.post(
            f"/api/rooms/{sample_room}/presenter",
            json={"user_id": "user-presenter", "action": "grant"},
        )
    assert resp.status_code == 200
    room = mock_mongo.rooms.find_one({"_id": sample_room})
    assert "user-presenter" in room["presenter_ids"]


def test_member_cannot_toggle_mode(authed_client, sample_room):
    resp = authed_client.post(f"/api/rooms/{sample_room}/mode", json={"mode": "broadcast"})
    assert resp.status_code == 403
