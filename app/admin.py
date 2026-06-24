import requests as http
from flask import Blueprint, render_template, request, jsonify
from .middleware import admin_required
from .models import db
from .config import LIVEKIT_INTERNAL_URL
from . import lk
import bcrypt

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@admin_required
def dashboard():
    rooms = list(db.rooms.find({"active": True}))
    participant_counts = lk.list_rooms_participants()
    for room in rooms:
        room["participant_count"] = participant_counts.get(room["_id"], 0)

    # Client-side recordings land as "complete" immediately (no "active" phase),
    # so show recent recordings, newest first.
    active_recordings = list(db.recordings.find().sort("started_at", -1).limit(50))
    for rec in active_recordings:
        if rec.get("started_at"):
            rec["started_at"] = rec["started_at"].isoformat()
        rec.setdefault("size", 0)
    recent_audit = list(db.audit_log.find().sort("timestamp", -1).limit(20))
    for entry in recent_audit:
        entry["_id"] = str(entry["_id"])
        if entry.get("timestamp"):
            entry["timestamp"] = entry["timestamp"].isoformat()

    users = list(db.users.find({}, {"password_hash": 0}))

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
        users=users
    )


@admin_bp.route("/api/admin/users", methods=["POST"])
@admin_required
def create_user():
    data = request.get_json(force=True)
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    display_name = data.get("display_name", "").strip()
    role = data.get("role", "member")

    if not all([username, password, display_name]):
        return jsonify({"error": "Missing required fields"}), 400

    if db.users.find_one({"username": username}):
        return jsonify({"error": "User already exists"}), 409

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode()
    db.users.insert_one({
        "username": username,
        "password_hash": password_hash,
        "display_name": display_name,
        "role": role,
        "avatar_url": None
    })

    return jsonify({"status": "created"})


@admin_bp.route("/api/admin/users/<user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    from bson import ObjectId
    db.users.delete_one({"_id": ObjectId(user_id)})
    return jsonify({"status": "deleted"})


@admin_bp.route("/api/admin/rooms", methods=["POST"])
@admin_required
def create_room():
    data = request.get_json(force=True)
    room_id = data.get("room_id", "").strip().lower().replace(" ", "-")
    display_name = data.get("display_name", "").strip()

    if not all([room_id, display_name]):
        return jsonify({"error": "Missing required fields"}), 400

    if db.rooms.find_one({"_id": room_id}):
        return jsonify({"error": "Room already exists"}), 409

    db.rooms.insert_one({
        "_id": room_id,
        "display_name": display_name,
        "active": True,
        "mode": "discussion",
        "locked": False,
        "operator_passphrase": "",
        "operator_ids": [],
        "presenter_ids": []
    })
    return jsonify({"status": "created", "room_id": room_id})


@admin_bp.route("/api/admin/rooms/<room_id>", methods=["DELETE"])
@admin_required
def delete_room(room_id):
    lk.delete_room(room_id)
    db.rooms.delete_one({"_id": room_id})
    return jsonify({"status": "deleted"})


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
