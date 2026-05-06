import json
import pytest
from unittest.mock import patch, MagicMock

def test_per_room_operator_passphrase(app, mock_mongo):
    """
    Verify that an admin can set a per-room passphrase and a user can log in with it.
    """
    room_id = "test-room-1"
    mock_mongo.rooms.insert_one({
        "_id": room_id,
        "display_name": "Test Room",
        "active": True,
        "mode": "discussion"
    })

    # 1. Admin sets the passphrase
    with app.test_client() as admin:
        with admin.session_transaction() as sess:
            sess["user_id"] = "admin-1"
            sess["role"] = "admin"
        
        resp = admin.post(f"/api/admin/rooms/{room_id}/config", json={
            "operator_passphrase": "room-secret-123"
        })
        assert resp.status_code == 200
        
        room = mock_mongo.rooms.find_one({"_id": room_id})
        assert room["operator_passphrase"] == "room-secret-123"

    # 2. User logs in with room passphrase
    with app.test_client() as op:
        resp = op.post("/auth/login", data={
            "display_name": "RoomOp",
            "passphrase": "room-secret-123",
            "sector": "Sector 01"
        }, follow_redirects=True)
        
        with op.session_transaction() as sess:
            assert sess["role"] == "operator"
            assert sess["operator_room_id"] == room_id

    # 3. Verify operator has rights in that room
    with app.test_client() as op:
        with op.session_transaction() as sess:
            sess["user_id"] = "op-1"
            sess["role"] = "operator"
            sess["operator_room_id"] = room_id
            
        with patch("app.rooms.lk.get_room_metadata", return_value="{}"), \
             patch("app.rooms.lk.update_room_metadata"):
            resp = op.post(f"/api/rooms/{room_id}/mode", json={"mode": "broadcast"})
            assert resp.status_code == 200

    # 4. Verify operator DOES NOT have rights in another room
    other_room = "other-room"
    mock_mongo.rooms.insert_one({"_id": other_room, "active": True})
    
    with app.test_client() as op:
        with op.session_transaction() as sess:
            sess["user_id"] = "op-1"
            sess["role"] = "operator"
            sess["operator_room_id"] = room_id
            
        resp = op.post(f"/api/rooms/{other_room}/mode", json={"mode": "broadcast"})
        assert resp.status_code == 403
