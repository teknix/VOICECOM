import logging
from datetime import datetime, timezone
from flask import Blueprint, request
from livekit.api import WebhookReceiver, TokenVerifier
from .config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET
from .models import db

webhook_bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)

receiver = WebhookReceiver(TokenVerifier(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET))


def _now():
    return datetime.now(timezone.utc)


@webhook_bp.route("/livekit/webhook", methods=["POST"])
def livekit_webhook():
    try:
        event = receiver.receive(request.data, request.headers.get("Authorization", ""))
    except Exception:
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

    db.audit_log.insert_one({
        "event": f"livekit_{event_type}",
        "room_id": getattr(getattr(event, "room", None), "name", None),
        "actor": "livekit",
        "timestamp": _now(),
        "meta": {"event_type": event_type},
    })

    return "", 200
