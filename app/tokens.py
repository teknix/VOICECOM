import json
from datetime import timedelta
from livekit import api
from .config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET
from .models import db

TOKEN_TTL = timedelta(hours=4)


def issue_token(user_id: str, display_name: str, room_id: str, role: str, sector: str = "Sector 01", avatar_url: str = None) -> str:
    room = db.rooms.find_one({"_id": room_id})
    if not room:
        raise ValueError(f"Room {room_id!r} not found")

    if room.get("locked") and role != "admin":
        raise ValueError(f"Room {room_id!r} is locked")

    mode = room.get("mode", "discussion")
    presenter_ids = room.get("presenter_ids", [])
    operator_ids = room.get("operator_ids", [])

    grants = api.VideoGrants(room_join=True, room=room_id)

    # Resolve actual role in this specific room
    actual_role = role
    if role == "operator" and user_id not in operator_ids:
        actual_role = "member"

    if mode == "broadcast":
        # Persistent presenters (lecturer/panel) plus the one transient floor
        # holder (a questioner promoted from the hand queue) both publish, so Q&A
        # is a real two-way conversation rather than turn-taking on one mic.
        is_presenter = (actual_role in ("admin", "moderator", "operator")
                        or user_id in presenter_ids
                        or user_id == room.get("floor_holder"))
        grants.can_publish = is_presenter
        grants.can_publish_data = is_presenter
        grants.can_subscribe = True
    else:
        grants.can_publish = True
        grants.can_subscribe = True
        grants.can_publish_data = True

    # Store role and sector in metadata for hierarchical enforcement and UI
    metadata = json.dumps({
        "role": actual_role, 
        "sector": sector,
        "avatar_url": avatar_url
    })

    token = (
        api.AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
        .with_identity(user_id)
        .with_name(display_name)
        .with_metadata(metadata)
        .with_grants(grants)
        .with_ttl(TOKEN_TTL)
        .to_jwt()
    )
    return token
