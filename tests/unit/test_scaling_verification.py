import pytest
from app.lk import update_room_metadata

def test_update_room_metadata_mock(monkeypatch):
    # Verify O(1) signaling path
    called = False
    def mock_lk_run(coro):
        nonlocal called
        called = True
        return None
        
    monkeypatch.setattr("app.lk.lk_run", mock_lk_run)
    update_room_metadata("test-room", '{"mode": "broadcast"}')
    assert called
