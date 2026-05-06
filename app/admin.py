import requests as http
from flask import Blueprint, render_template, request, jsonify
from .middleware import admin_required
from .models import db
from .config import LIVEKIT_INTERNAL_URL
from . import lk

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@admin_required
def dashboard():
    rooms = list(db.rooms.find({"active": True}))
    participant_counts = lk.list_rooms_participants()
    for room in rooms:
        room["participant_count"] = participant_counts.get(room["_id"], 0)

    active_recordings = list(db.recordings.find({"status": "active"}))
    recent_audit = list(db.audit_log.find().sort("timestamp", -1).limit(20))
    for entry in recent_audit:
        entry["_id"] = str(entry["_id"])
        if entry.get("timestamp"):
            entry["timestamp"] = entry["timestamp"].isoformat()

    try:
        resp = http.get(f"{LIVEKIT_INTERNAL_URL}/", timeout=2)
        lk_healthy = resp.status_code == 200
    except Exception:
        lk_healthy = False

    return render_template(
        "admin.html",
        rooms=rooms,
        active_recordings=active_recordings,
        recent_audit=recent_audit,
        lk_healthy=lk_healthy,
    )


@admin_bp.route("/api/admin/rooms/<room_id>/config", methods=["POST"])
@admin_required
def update_room_config(room_id):
    data = request.get_json(force=True)
    oppass = data.get("operator_passphrase", "").strip()
    locked = data.get("locked", False)
    
    db.rooms.update_one(
        {"_id": room_id},
        {"$set": {
            "operator_passphrase": oppass,
            "locked": locked
        }}
    )
    
    if locked:
        # If locking, also kick everyone
        lk.delete_room(room_id)
    
    return jsonify({"status": "updated"})


@admin_bp.route("/api/admin/rooms/<room_id>/kick-all", methods=["POST"])
@admin_required
def kick_all(room_id):
    lk.delete_room(room_id)
    return jsonify({"status": "kicked"})
