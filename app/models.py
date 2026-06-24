from pymongo import MongoClient, ASCENDING, DESCENDING
from .config import MONGO_URI

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client.get_default_database()
    return _db


# System rooms the app code depends on existing (clients auto-connect on load).
# Seeded on startup so a deploy never relies on an admin having created them by hand.
SYSTEM_ROOMS = [
    {
        "_id": "global-announcement",
        "display_name": "Global Announcement",
        "active": True,
        "mode": "broadcast",  # only admins/mods/presenters publish; everyone listens
        "locked": False,
        "operator_passphrase": "",
        "operator_ids": [],
        "presenter_ids": [],
        "floor_holder": "",
    },
]


def init_db(app):
    with app.app_context():
        db = get_db()
        db.users.create_index([("username", ASCENDING)], unique=True)
        db.recordings.create_index([("room_id", ASCENDING)])
        db.recordings.create_index([("started_by", ASCENDING)])
        db.recordings.create_index([("status", ASCENDING)])
        db.audit_log.create_index([("room_id", ASCENDING), ("timestamp", DESCENDING)])
        for room in SYSTEM_ROOMS:
            # $setOnInsert: create if missing, never overwrite later admin edits.
            db.rooms.update_one({"_id": room["_id"]}, {"$setOnInsert": room}, upsert=True)


db = get_db()
