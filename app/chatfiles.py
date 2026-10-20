"""Files shared in channel chat: the paperclip uploads one file, chat gets its link.

A file lives for FILE_TTL (4 hours). After that the link answers "expired" and the
file is deleted from disk — by a sweep on every upload/download plus a background
loop, so nothing outlives its window by more than a few minutes.
"""
import logging
import mimetypes
import os
import re
import secrets
import threading
import time
from datetime import timedelta

from flask import Blueprint, jsonify, render_template, request, send_file, session

from .middleware import login_required
from .models import db
from .utils import audit_log, now_utc

chatfiles_bp = Blueprint("chatfiles", __name__)
logger = logging.getLogger(__name__)

FILES_DIR = os.environ.get("CHAT_FILES_DIR",
                           os.path.join(os.environ.get("RECORDINGS_DIR", "/recordings"), "chat-files"))
MAX_FILE_BYTES = 200 * 1024 * 1024  # 200 MB (owner, 2026-10-19)
FILE_TTL = timedelta(hours=4)
# Shown in the browser; everything else downloads (an uploaded .html must never run on our origin).
INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


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
            except Exception:
                logger.exception("chat file sweep failed")
    threading.Thread(target=loop, daemon=True, name="chat-file-sweeper").start()


@chatfiles_bp.route("/api/rooms/<room_id>/files", methods=["POST"])
@login_required
def upload_file(room_id):
    if not db.rooms.find_one({"_id": room_id}):
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
    resp.headers["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'"
    return resp
