from unittest.mock import patch
import json

def test_sync_room_success(mod_client, mock_mongo, sample_room):
    # Set room mode in DB
    mock_mongo.rooms.update_one({"_id": sample_room}, {"$set": {"mode": "broadcast"}})
    
    with patch("app.rooms.lk.update_room_metadata") as mock_update:
        resp = mod_client.post(f"/api/rooms/{sample_room}/sync")
        
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "synced", "mode": "broadcast"}
        
        # Verify LiveKit was called with correct metadata
        mock_update.assert_called_once_with(sample_room, json.dumps({"mode": "broadcast"}))
        
        # Verify audit log
        audit = mock_mongo.audit_log.find_one({"event": "room_sync", "room_id": sample_room})
        assert audit is not None
        assert audit["meta"]["mode"] == "broadcast"

def test_sync_room_not_found(mod_client):
    resp = mod_client.post("/api/rooms/nonexistent/sync")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Room not found"

def test_sync_room_forbidden_for_member(authed_client, sample_room):
    resp = authed_client.post(f"/api/rooms/{sample_room}/sync")
    assert resp.status_code == 403

def test_sync_room_livekit_failure(mod_client, mock_mongo, sample_room):
    with patch("app.rooms.lk.update_room_metadata", side_effect=Exception("LK error")):
        resp = mod_client.post(f"/api/rooms/{sample_room}/sync")
        assert resp.status_code == 502
        assert "LiveKit update failed" in resp.get_json()["error"]
