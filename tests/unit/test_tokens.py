import pytest


def test_issue_token_discussion(mock_mongo, sample_room):
    from app.tokens import issue_token
    token = issue_token("user-1", "Alice", sample_room, "member")
    assert isinstance(token, str) and len(token) > 20


def test_issue_token_broadcast_member(mock_mongo, sample_room):
    mock_mongo.rooms.update_one({"_id": sample_room}, {"$set": {"mode": "broadcast"}})
    from app.tokens import issue_token
    token = issue_token("user-1", "Alice", sample_room, "member")
    assert token  # member gets a token (subscribe-only, no publish)


def test_issue_token_broadcast_presenter(mock_mongo, sample_room):
    mock_mongo.rooms.update_one(
        {"_id": sample_room},
        {"$set": {"mode": "broadcast", "presenter_ids": ["user-presenter"]}}
    )
    from app.tokens import issue_token
    token = issue_token("user-presenter", "Bob", sample_room, "member")
    assert token


def test_issue_token_room_not_found(mock_mongo):
    from app.tokens import issue_token
    with pytest.raises(ValueError, match="not found"):
        issue_token("user-1", "Alice", "nonexistent-room", "member")


def test_issue_token_ttl_is_4_hours():
    from app.tokens import TOKEN_TTL
    from datetime import timedelta
    assert TOKEN_TTL == timedelta(hours=4)
