"""Files shared in channel chat: the paperclip uploads one file, chat gets its link.

Signed in with Zulip: the file goes to Zulip as that user, in a group DM to everyone
in the VoiceCom channel at that moment (owner 2026-10-19). Zulip only lets people who
can see a message open its file, so this keeps it private to them, with no time limit.
Anyone else (internal accounts), or if Zulip refuses the file: the VoiceCom copy below.

A VoiceCom copy lives for FILE_TTL (4 hours). After that the link answers "expired" and the
file is deleted from disk — by a sweep on every upload/download plus a background
loop, so nothing outlives its window by more than a few minutes.
"""
import logging
import mimetypes
import os
import re
import secrets
import json
import threading
import time
from datetime import timedelta

import requests
from flask import Blueprint, jsonify, render_template, request, send_file, session
from requests.auth import HTTPBasicAuth

from .middleware import login_required
from .models import db
from . import zulipkeys
from .lk import list_participants
from .utils import audit_log, now_utc

chatfiles_bp = Blueprint("chatfiles", __name__)
logger = logging.getLogger(__name__)

FILES_DIR = os.environ.get("CHAT_FILES_DIR",
                           os.path.join(os.environ.get("RECORDINGS_DIR", "/recordings"), "chat-files"))
MAX_FILE_BYTES = 200 * 1024 * 1024  # 200 MB (owner, 2026-10-19)
FILE_TTL = timedelta(hours=4)
# Shown in the browser; everything else downloads (an uploaded .html must never run on our origin).
INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp",
                "video/mp4", "video/webm", "audio/mpeg", "audio/ogg", "audio/wav", "audio/mp4"}


def safe_name(name):
    base = os.path.basename(name or "").strip() or "file"
    base = re.sub(r"[^\w.\- ()]+", "_", base)[:120]
    return base.lstrip(".") or "file"


def purge_expired():
    """Delete files whose 4 hours are up. Safe to run from several workers at once."""
    for doc in db.chat_files.find({"expires_at": {"$lte": now_utc()}}):
        try:
            os.remove(os.path.join(FILES_DIR, doc["_id"]))
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning("chat file %s not removed: %s", doc["_id"], e)
            continue
        db.chat_files.delete_one({"_id": doc["_id"]})


_sweeper_started = False


def start_sweeper(interval=300):
    global _sweeper_started
    if _sweeper_started:
        return
    _sweeper_started = True

    def loop():
        while True:
            time.sleep(interval)
            try:
                purge_expired()
                zulipkeys.purge_stale()
            except Exception:
                logger.exception("chat file sweep failed")
    threading.Thread(target=loop, daemon=True, name="chat-file-sweeper").start()


ZULIP_URL = os.environ.get("ZULIP_URL", "").rstrip("/")


def channel_zulip_ids(room_id, me):
    """Zulip user ids of everyone in the channel right now (Zulip users' identities are their ids)."""
    ids = {int(me)} if str(me).isdigit() else set()
    try:
        for p in list_participants(room_id):
            if p.identity.isdigit():
                ids.add(int(p.identity))
    except Exception as e:
        logger.warning("chat file: participant list for %s failed: %s", room_id, e)
    return sorted(ids)


def share_on_zulip(path, name, room, auth):
    """Upload as the user and DM it to the channel. Returns the file's Zulip URL, or None."""
    if not ZULIP_URL:
        return None
    email, key = auth
    try:
        with open(path, "rb") as fh:
            up = requests.post(f"{ZULIP_URL}/api/v1/user_uploads", files={"file": (name, fh)},
                               auth=HTTPBasicAuth(email, key), timeout=(5, 600))
        data = up.json() if up.headers.get("Content-Type", "").startswith("application/json") else {}
        rel = data.get("url") or data.get("uri")
        if up.status_code != 200 or not rel:
            logger.warning("chat file: Zulip upload refused (HTTP %s): %s", up.status_code, data.get("msg"))
            return None
        to = channel_zulip_ids(room["_id"], session["user_id"])
        if not to:
            return None
        msg = requests.post(f"{ZULIP_URL}/api/v1/messages", auth=HTTPBasicAuth(email, key), timeout=10, data={
            "type": "direct",
            "to": json.dumps(to),
            "content": f"📎 [{name}]({rel}) shared in the VoiceCom channel **{room.get('display_name', room['_id'])}**",
        })
        if msg.status_code != 200:
            logger.warning("chat file: Zulip DM refused (HTTP %s)", msg.status_code)
            return None
        return ZULIP_URL + rel
    except requests.RequestException as e:
        logger.warning("chat file: Zulip unreachable: %s", e)
        return None


@chatfiles_bp.route("/api/rooms/<room_id>/files", methods=["POST"])
@login_required
def upload_file(room_id):
    room = db.rooms.find_one({"_id": room_id})
    if not room:
        return jsonify({"error": "Channel not found"}), 404
    if request.content_length and request.content_length > MAX_FILE_BYTES + 1024 * 1024:
        return jsonify({"error": "That file is over 200 MB."}), 413
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Pick a file first."}), 400

    purge_expired()
    os.makedirs(FILES_DIR, exist_ok=True)
    file_id = secrets.token_urlsafe(16)
    path = os.path.join(FILES_DIR, file_id)
    f.save(path)
    size = os.path.getsize(path)
    if size == 0 or size > MAX_FILE_BYTES:
        os.remove(path)
        return jsonify({"error": "That file is empty." if size == 0 else "That file is over 200 MB."}), 413

    name = safe_name(f.filename)
    auth = zulipkeys.current()
    zulip_url = share_on_zulip(path, name, room, auth) if auth else None
    if zulip_url:
        os.remove(path)
        audit_log(room_id, "chat_file_shared", session["user_id"], {"file": name, "size": size, "where": "zulip"})
        return jsonify({"name": name, "size": size, "url": zulip_url, "zulip": True}), 201

    created = now_utc()
    doc = {
        "_id": file_id,
        "room_id": room_id,
        "name": name,
        "size": size,
        "mime": mimetypes.guess_type(name)[0] or "application/octet-stream",
        "uploaded_by": session["user_id"],
        "uploaded_by_name": session.get("display_name", ""),
        "created_at": created,
        "expires_at": created + FILE_TTL,
    }
    db.chat_files.insert_one(doc)
    audit_log(room_id, "chat_file_shared", session["user_id"], {"file": name, "size": size})
    return jsonify({
        "id": file_id,
        "name": name,
        "size": size,
        "url": f"/files/{file_id}/{name}",
        "expires_at": doc["expires_at"].isoformat(),
        "zulip_fallback": bool(auth),  # was meant for Zulip but Zulip refused or was unreachable
    }), 201


@chatfiles_bp.route("/files/<file_id>/<path:name>")
@login_required
def download_file(file_id, name):
    purge_expired()
    doc = db.chat_files.find_one({"_id": file_id})
    path = os.path.join(FILES_DIR, os.path.basename(file_id))
    if not doc or doc["expires_at"].replace(tzinfo=now_utc().tzinfo) <= now_utc() or not os.path.exists(path):
        return render_template("file_gone.html"), 410
    inline = doc["mime"] in INLINE_TYPES
    resp = send_file(path, mimetype=doc["mime"] if inline else "application/octet-stream",
                     as_attachment=not inline, download_name=doc["name"], max_age=0)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; media-src 'self'"
    return resp
