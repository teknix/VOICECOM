"""Local store for Zulip avatars.

Zulip hands us a relative `avatar_url` (/user_avatars/<realm>/<sha1>.png) that
only resolves on the Zulip host. Fetch each one from Zulip once, keep the bytes
in mongo, and serve them ourselves. The filename is a content hash — a new
upload gets a new name — so a stored copy never goes stale and can be served
`immutable`.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

import requests
from bson.binary import Binary

from . import zulip
from .models import db

logger = logging.getLogger(__name__)

# Only paths shaped like a Zulip avatar are ever proxied — never an arbitrary
# path on the Zulip host.
_FILENAME = re.compile(r"^\d+/[0-9a-f]{16,64}(-medium)?\.png$")
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_BYTES = 2_000_000
# A failed fetch is remembered this long, so a missing avatar can't turn every
# page render into a Zulip request.
MISS_TTL = timedelta(minutes=10)


def valid_filename(filename: str) -> bool:
    return bool(_FILENAME.match(filename or ""))


def _fetch(filename: str):
    if not zulip.ZULIP_URL:
        return None
    url = f"{zulip.ZULIP_URL.rstrip('/')}/user_avatars/{filename}"
    try:
        resp = requests.get(url, timeout=5)
    except Exception as e:
        logger.warning("avatar fetch %s failed: %s", filename, e)
        return None
    ctype = resp.headers.get("content-type", "").split(";")[0].strip()
    if resp.status_code != 200 or ctype not in _IMAGE_TYPES or len(resp.content) > MAX_BYTES:
        logger.warning("avatar fetch %s -> HTTP %s %s %d bytes",
                       filename, resp.status_code, ctype, len(resp.content))
        return None
    return resp.content, ctype


def get_avatar(filename: str):
    """Return (bytes, content_type) for a stored avatar, fetching it on first use.
    None when the name is invalid or Zulip doesn't have it."""
    if not valid_filename(filename):
        return None
    now = datetime.now(timezone.utc)
    doc = db.avatars.find_one({"_id": filename})
    if doc and doc.get("data") is not None:
        return bytes(doc["data"]), doc["content_type"]
    if doc and doc.get("missing_at"):
        missing_at = doc["missing_at"]
        if missing_at.tzinfo is None:  # pymongo returns naive UTC by default
            missing_at = missing_at.replace(tzinfo=timezone.utc)
        if now - missing_at < MISS_TTL:
            return None

    got = _fetch(filename)
    if got is None:
        db.avatars.update_one({"_id": filename}, {"$set": {"missing_at": now}}, upsert=True)
        return None
    data, ctype = got
    db.avatars.update_one(
        {"_id": filename},
        {"$set": {"data": Binary(data), "content_type": ctype, "fetched_at": now},
         "$unset": {"missing_at": ""}},
        upsert=True,
    )
    return data, ctype


def prefetch(avatar_url):
    """Store a user's avatar at login so the first room render is already local.
    Best-effort: login never fails because of an avatar."""
    if not avatar_url or not avatar_url.startswith("/user_avatars/"):
        return
    try:
        get_avatar(avatar_url[len("/user_avatars/"):].split("?")[0])
    except Exception as e:
        logger.warning("avatar prefetch failed: %s", e)
