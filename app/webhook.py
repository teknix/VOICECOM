import json
import logging
from datetime import datetime, timezone
from flask import Blueprint, request
from livekit.api import WebhookReceiver, TokenVerifier
from .config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET
from .models import db
from . import lk

webhook_bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)

receiver = WebhookReceiver(TokenVerifier(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET))


def _now():
    return datetime.now(timezone.utc)


@webhook_bp.route("/livekit/webhook", methods=["POST"])
def livekit_webhook():
    try:
        # receive() expects the body as str (it hashes body.encode()); request.data
        # is bytes, which threw AttributeError and surfaced as a blanket 401.
        event = receiver.receive(request.get_data(as_text=True), request.headers.get("Authorization", ""))
    except Exception as e:
        logger.warning("webhook verification failed: %s", e)
        return "", 401

    event_type = event.event

    if event_type == "egress_ended":
        egress_id = event.egress_info.egress_id
        db.recordings.update_one(
            {"_id": egress_id},
            {"$set": {"status": "complete", "stopped_at": _now()}},
        )
        logger.info("egress_ended: %s marked complete", egress_id)

    elif event_type == "egress_started":
        egress_id = event.egress_info.egress_id
        if not db.recordings.find_one({"_id": egress_id}):
            logger.warning("egress_started for unknown egress %s — no DB record", egress_id)

    elif event_type == "participant_left":
        # Clear the speaking floor if its holder dropped. Server-side, so it works
        # with no mod/operator present to clear it from the client.
        room_name = getattr(getattr(event, "room", None), "name", None)
        identity = getattr(getattr(event, "participant", None), "identity", None)
        if room_name and identity:
            room = db.rooms.find_one({"_id": room_name})
            if room and room.get("floor_holder") == identity:
                db.rooms.update_one({"_id": room_name}, {"$set": {"floor_holder": None}})
                try:
                    raw = lk.get_room_metadata(room_name)
                    meta = json.loads(raw) if raw else {}
                    meta["floor"] = ""
                    lk.update_room_metadata(room_name, json.dumps(meta))
                except Exception:
                    logger.warning("failed to clear floor metadata for %s", room_name)

    db.audit_log.insert_one({
        "event": f"livekit_{event_type}",
        "room_id": getattr(getattr(event, "room", None), "name", None),
        "actor": "livekit",
        "timestamp": _now(),
        "meta": {"event_type": event_type},
    })

    return "", 200
