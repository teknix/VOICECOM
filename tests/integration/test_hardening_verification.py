import json
import pytest
from unittest.mock import patch, MagicMock

def test_shadow_speaker_fix_enforcement(mod_client, mock_mongo, sample_room):
    """
    D1: Verify that switching to broadcast mode triggers background enforcement
    to revoke publishing permissions from members who are not presenters.
    """
    # 1. Setup participants in the room
    # One presenter, one member talking (shadow speaker)
    mock_participants = [
        MagicMock(identity="presenter-1", metadata=json.dumps({"role": "member"})),
        MagicMock(identity="shadow-1", metadata=json.dumps({"role": "member"}))
    ]
    
    # Update DB to recognize presenter-1 as an explicit presenter
    mock_mongo.rooms.update_one(
        {"_id": sample_room},
        {"$set": {"presenter_ids": ["presenter-1"], "mode": "discussion"}}
    )

    with patch("app.rooms.lk.get_room_metadata", return_value="{}"), \
         patch("app.rooms.lk.update_room_metadata") as mock_update_meta, \
         patch("app.rooms.lk.list_participants", return_value=mock_participants), \
         patch("app.rooms.lk.update_participant") as mock_update_p, \
         patch("gevent.spawn") as mock_spawn:
        
        # Trigger mode change to broadcast
        resp = mod_client.post(f"/api/rooms/{sample_room}/mode", json={"mode": "broadcast"})
        assert resp.status_code == 200
        
        # Verify metadata broadcast
        mock_update_meta.assert_called_once()
        sent_meta = json.loads(mock_update_meta.call_args[0][1])
        assert sent_meta["mode"] == "broadcast"
        
        # Verify background task was spawned
        mock_spawn.assert_called_once()
        
        # Manually execute the spawned function to verify enforcement logic
        enforce_fn = mock_spawn.call_args[0][0]
        
        # We need to mock Pool in the local scope of enforce_mute
        # Since we are executing the function directly, we'll mock the Pool inside its closure if possible
        # or just let it run if we can patch Pool
        with patch("app.rooms.Pool") as mock_pool:
            enforce_fn()
            
            # Verify update_participant was called for the shadow speaker but NOT the presenter
            # spawned_calls will be list of arguments passed to spawn()
            # each call is ((fn, *args), {})
            spawned_identities = [call[0][2] for call in mock_pool.return_value.spawn.call_args_list]
            assert "shadow-1" in spawned_identities
            assert "presenter-1" not in spawned_identities

def test_hand_queue_persistence_in_metadata(mod_client, mock_mongo, sample_room):
    """
    D2: Verify that moderators can persist the hand queue in room metadata.
    """
    with patch("app.rooms.lk.update_room_metadata") as mock_update_meta:
        # 1. Update metadata with a hand queue
        queue_data = [
            {"user_id": "user-1", "display_name": "Alice", "raised_at": "2026-05-03T12:00:00Z"},
            {"user_id": "user-2", "display_name": "Bob", "raised_at": "2026-05-03T12:01:00Z"}
        ]
        meta_payload = json.dumps({"mode": "broadcast", "hand_queue": queue_data})
        
        resp = mod_client.post(f"/api/rooms/{sample_room}/metadata", json={"metadata": meta_payload})
        assert resp.status_code == 200
        
        # Verify LiveKit was called with the queue in metadata
        mock_update_meta.assert_called_once_with(sample_room, meta_payload)
