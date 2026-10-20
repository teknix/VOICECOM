"""Each signed-in Zulip user's own API key, kept server-side only while they're signed in.

Owner decision 2026-10-19: VoiceCom may keep a user's Zulip key so their uploads go
to Zulip as them, "only until log out". The browser only ever holds a random handle
(session["zk"]); the key itself stays in mongo and is deleted at logout. A key whose
session was never logged out (closed tab, cleared cookies) is dropped after MAX_AGE,
because nothing could ever use it again. Keys are never logged.
"""
import secrets
from datetime import timedelta

from flask import session

from .models import db
from .utils import now_utc

MAX_AGE = timedelta(days=7)


def save(email, api_key):
    sid = secrets.token_urlsafe(24)
    db.zulip_keys.insert_one({"_id": sid, "email": email, "api_key": api_key, "created_at": now_utc()})
    return sid


def current():
    """(email, api_key) for the signed-in user, or None (internal/Matrix users, expired, logged out)."""
    sid = session.get("zk")
    if not sid:
        return None
    doc = db.zulip_keys.find_one({"_id": sid})
    if not doc:
        return None
    if doc["created_at"].replace(tzinfo=now_utc().tzinfo) < now_utc() - MAX_AGE:
        db.zulip_keys.delete_one({"_id": sid})
        return None
    return doc["email"], doc["api_key"]


def drop(sid):
    if sid:
        db.zulip_keys.delete_one({"_id": sid})


def purge_stale():
    db.zulip_keys.delete_many({"created_at": {"$lt": now_utc() - MAX_AGE}})
