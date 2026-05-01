import json
import pytest
from unittest.mock import MagicMock, patch


def _make_event(event_type, egress_id=None):
    event = MagicMock()
    event.event = event_type
    if egress_id:
        event.egress_info = MagicMock()
        event.egress_info.egress_id = egress_id
    # MagicMock(name=...) sets the mock's repr name, NOT the .name attribute.
    # Set .name explicitly so getattr(event.room, "name") returns a plain string.
    event.room = MagicMock()
    event.room.name = "sector-test"
    return event


def test_webhook_bad_signature(client):
    resp = client.post(
        "/livekit/webhook",
        data=b'{"event":"room_finished"}',
        headers={"Authorization": "bad-sig"},
        content_type="application/octet-stream",
    )
    assert resp.status_code == 401


def test_webhook_egress_ended_updates_recording(client, mock_mongo):
    mock_mongo.recordings.insert_one({
        "_id": "egress-abc",
        "room_id": "sector-test",
        "status": "active",
        "started_by": "user-1",
    })
    good_event = _make_event("egress_ended", egress_id="egress-abc")
    with patch("app.webhook.receiver") as mock_receiver:
        mock_receiver.receive.return_value = good_event
        resp = client.post(
            "/livekit/webhook",
            data=b"fake-body",
            headers={"Authorization": "valid"},
            content_type="application/octet-stream",
        )
    assert resp.status_code == 200
    rec = mock_mongo.recordings.find_one({"_id": "egress-abc"})
    assert rec["status"] == "complete"
    assert rec["stopped_at"] is not None
