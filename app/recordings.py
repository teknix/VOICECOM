import os
import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, session, send_file
from .middleware import mod_required
from .models import db
from . import lk
from .utils import audit_log, now_utc

recordings_bp = Blueprint("recordings", __name__)
logger = logging.getLogger(__name__)


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


@recordings_bp.route("/api/recordings/start", methods=["POST"])
@mod_required
def start_recording():
    data = request.get_json(force=True)
    room_id = data.get("room_id", "").strip()
    if not room_id:
        return jsonify({"error": "room_id required"}), 400

    if db.recordings.find_one({"room_id": room_id, "status": "active"}):
        return jsonify({"error": "Recording already active for this room"}), 409

    filename = f"{room_id}_{int(now_utc().timestamp())}.mp4"
    filepath = f"/recordings/{filename}"

    try:
        egress_id = lk.start_egress(room_id, filepath)
    except Exception as e:
        return jsonify({"error": f"Failed to start egress: {e}"}), 502

    try:
        db.recordings.insert_one({
            "_id": egress_id,
            "room_id": room_id,
            "started_by": session["user_id"],
            "started_at": now_utc(),
            "stopped_at": None,
            "file_path": filepath,
            "status": "active",
        })
    except Exception as e:
        logger.error("MongoDB write failed after egress start — compensating with stop_egress: %s", e)
        try:
            lk.stop_egress(egress_id)
        except Exception as stop_err:
            logger.error("Compensation stop_egress also failed: %s", stop_err)
        return jsonify({"error": "Failed to record egress in database"}), 500

    audit_log(room_id, "recording_started", session["user_id"], {"egress_id": egress_id})
    return jsonify({"egress_id": egress_id}), 201


@recordings_bp.route("/api/recordings/stop", methods=["POST"])
@mod_required
def stop_recording():
    data = request.get_json(force=True)
    egress_id = data.get("egress_id", "").strip()
    if not egress_id:
        return jsonify({"error": "egress_id required"}), 400

    recording = db.recordings.find_one({"_id": egress_id})
    if not recording:
        return jsonify({"error": "Recording not found"}), 404

    try:
        lk.stop_egress(egress_id)
    except Exception as e:
        return jsonify({"error": f"Failed to stop egress: {e}"}), 502

    db.recordings.update_one(
        {"_id": egress_id},
        {"$set": {"status": "complete", "stopped_at": now_utc()}},
    )
    audit_log(recording["room_id"], "recording_stopped", session["user_id"], {"egress_id": egress_id})
    return jsonify({"status": "complete"})


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


@recordings_bp.route("/api/recordings/<egress_id>/download")
@mod_required
def download_recording(egress_id):
    recording = db.recordings.find_one({"_id": egress_id})
    if not recording:
        return jsonify({"error": "Not found"}), 404

    safe_name = os.path.basename(recording["file_path"])
    full_path = os.path.join(os.environ.get("RECORDINGS_DIR", "/recordings"), safe_name)

    if not os.path.exists(full_path):
        return jsonify({"error": "File not on disk yet"}), 404

    return send_file(full_path, as_attachment=True, download_name=safe_name)
