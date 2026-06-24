import os
import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, session, send_file
from .middleware import mod_required, login_required
from .models import db
from .utils import audit_log, now_utc

recordings_bp = Blueprint("recordings", __name__)
logger = logging.getLogger(__name__)

RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "/recordings")
MAX_RECORDING_BYTES = 500 * 1024 * 1024  # 500 MB


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


# ponytail: client-side recording. The browser mixes all room audio and uploads
# one file here on stop — no Chrome/egress. Presenter-only gating in broadcast is
# enforced UI-side; server requires login and that the room exists.
@recordings_bp.route("/api/recordings/upload", methods=["POST"])
@login_required
def upload_recording():
    room_id = (request.form.get("room_id") or "").strip()
    if not room_id:
        return jsonify({"error": "room_id required"}), 400
    if not db.rooms.find_one({"_id": room_id}):
        return jsonify({"error": "Unknown room"}), 404

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "file required"}), 400
    if request.content_length and request.content_length > MAX_RECORDING_BYTES:
        return jsonify({"error": "Recording too large"}), 413

    started_ms = (request.form.get("started_ms") or "").strip()
    filename = f"{room_id}_{started_ms or int(now_utc().timestamp())}.webm"
    safe_name = os.path.basename(filename)
    full_path = os.path.join(RECORDINGS_DIR, safe_name)

    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    f.save(full_path)
    size = os.path.getsize(full_path)
    if size == 0 or size > MAX_RECORDING_BYTES:
        os.remove(full_path)
        return jsonify({"error": "Empty or oversized recording"}), 413

    rec_id = safe_name
    db.recordings.insert_one({
        "_id": rec_id,
        "room_id": room_id,
        "started_by": session["user_id"],
        "started_at": now_utc(),
        "stopped_at": now_utc(),
        "file_path": full_path,
        "size": size,
        "status": "complete",
    })
    audit_log(room_id, "recording_uploaded", session["user_id"], {"file": safe_name, "size": size})
    return jsonify({"id": rec_id, "size": size}), 201


@recordings_bp.route("/api/recordings")
@mod_required
def list_recordings():
    room_id = request.args.get("room_id", "").strip()
    query = {"room_id": room_id} if room_id else {}
    recs = list(db.recordings.find(query).sort("started_at", -1).limit(50))
    for r in recs:
        r["started_at"] = r["started_at"].isoformat() if r.get("started_at") else None
        r["stopped_at"] = r["stopped_at"].isoformat() if r.get("stopped_at") else None
    return jsonify(recs)


@recordings_bp.route("/api/recordings/<rec_id>/download")
@mod_required
def download_recording(rec_id):
    recording = db.recordings.find_one({"_id": rec_id})
    if not recording:
        return jsonify({"error": "Not found"}), 404

    safe_name = os.path.basename(recording["file_path"])
    full_path = os.path.join(RECORDINGS_DIR, safe_name)

    if not os.path.exists(full_path):
        return jsonify({"error": "File not on disk yet"}), 404

    # Inline by default so an <audio> element can stream it; ?dl=1 forces a download.
    return send_file(full_path, as_attachment=request.args.get("dl") == "1",
                     download_name=safe_name, conditional=True)


@recordings_bp.route("/api/recordings/<rec_id>", methods=["DELETE"])
@mod_required
def delete_recording(rec_id):
    recording = db.recordings.find_one({"_id": rec_id})
    if not recording:
        return jsonify({"error": "Not found"}), 404

    full_path = os.path.join(RECORDINGS_DIR, os.path.basename(recording["file_path"]))
    try:
        if os.path.exists(full_path):
            os.remove(full_path)
    except OSError as e:
        logger.error("Failed to delete recording file %s: %s", full_path, e)
        return jsonify({"error": "Failed to delete file"}), 500

    db.recordings.delete_one({"_id": rec_id})
    audit_log(recording["room_id"], "recording_deleted", session["user_id"], {"file": os.path.basename(full_path)})
    return jsonify({"status": "deleted"})
