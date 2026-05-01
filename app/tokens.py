from datetime import timedelta
from livekit import api
from .config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET
from .models import db

TOKEN_TTL = timedelta(hours=4)


def issue_token(user_id: str, display_name: str, room_id: str, role: str) -> str:
    room = db.rooms.find_one({"_id": room_id})
    if not room:
        raise ValueError(f"Room {room_id!r} not found")

    mode = room["mode"]
    presenter_ids = room.get("presenter_ids", [])

    grants = api.VideoGrants(room_join=True, room=room_id)

    if mode == "broadcast":
        is_presenter = role in ("admin", "moderator") or user_id in presenter_ids
        grants.can_publish = is_presenter
        grants.can_publish_data = is_presenter
        grants.can_subscribe = True
    else:
        grants.can_publish = True
        grants.can_subscribe = True
        grants.can_publish_data = True

    token = (
        api.AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
        .with_identity(user_id)
        .with_name(display_name)
        .with_grants(grants)
        .with_ttl(TOKEN_TTL)
        .to_jwt()
    )
    return token
