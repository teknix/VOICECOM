import json
from datetime import datetime, timezone
from .models import db

def now_utc():
    return datetime.now(timezone.utc)

def audit_log(room_id, event, actor, meta=None):
    db.audit_log.insert_one({
        "event": event,
        "room_id": room_id,
        "actor": actor,
        "timestamp": now_utc(),
        "meta": meta or {},
    })
