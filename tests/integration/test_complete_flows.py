import json
import pytest
from unittest.mock import patch, MagicMock

def test_recording_lifecycle(mod_client, mock_mongo, sample_room):
    """
    Verify start, list, and stop recording flow.
    """
    with patch("app.recordings.lk.start_egress", return_value="egress-123") as mock_start, \
         patch("app.recordings.lk.stop_egress") as mock_stop:
        
        # 1. Start
        resp = mod_client.post("/api/recordings/start", json={"room_id": sample_room})
        assert resp.status_code == 201
        assert resp.get_json()["egress_id"] == "egress-123"
        
        # 2. List
        resp = mod_client.get(f"/api/recordings?room_id={sample_room}")
        assert resp.status_code == 200
        recs = resp.get_json()
        assert len(recs) == 1
        assert recs[0]["_id"] == "egress-123"
        assert recs[0]["status"] == "active"
        
        # 3. Stop
        resp = mod_client.post("/api/recordings/stop", json={"egress_id": "egress-123"})
        assert resp.status_code == 200
        
        # Verify DB update
        rec = mock_mongo.recordings.find_one({"_id": "egress-123"})
        assert rec["status"] == "complete"
        assert rec["stopped_at"] is not None

def test_sync_state_flow(mod_client, mock_mongo, sample_room):
    """
    Verify the sync state endpoint correctly reconciles DB and LiveKit.
    """
    # Force DB to broadcast mode
    mock_mongo.rooms.update_one({"_id": sample_room}, {"$set": {"mode": "broadcast"}})
    
    with patch("app.rooms.lk.get_room_metadata", return_value='{"mode": "discussion"}'), \
         patch("app.rooms.lk.update_room_metadata") as mock_update_meta, \
         patch("app.rooms.lk.list_participants", return_value=[]), \
         patch("app.rooms.gevent.spawn") as mock_spawn:
        
        resp = mod_client.post(f"/api/rooms/{sample_room}/sync")
        assert resp.status_code == 200
        
        # Verify it pushed 'broadcast' (from DB) to LiveKit
        mock_update_meta.assert_called_once()
        sent_meta = json.loads(mock_update_meta.call_args[0][1])
        assert sent_meta["mode"] == "broadcast"
        
        # Verify background enforcement was triggered because mode is broadcast
        mock_spawn.assert_called_once()

def test_zulip_bridge_smoke(mod_client, sample_room):
    """
    Verify the Zulip chat bridge doesn't crash (even if deferred).
    """
    resp = mod_client.post(f"/api/rooms/{sample_room}/chat", json={"message": "Hello world"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "sent"
