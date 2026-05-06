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


def init_db(app):
    with app.app_context():
        db = get_db()
        db.users.create_index([("email", ASCENDING)], unique=True)
        db.recordings.create_index([("room_id", ASCENDING)])
        db.recordings.create_index([("started_by", ASCENDING)])
        db.recordings.create_index([("status", ASCENDING)])
        db.audit_log.create_index([("room_id", ASCENDING), ("timestamp", DESCENDING)])


db = get_db()
