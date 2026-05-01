from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, session
from gevent.pool import Pool
from .middleware import login_required, mod_required
from .models import db
from .tokens import issue_token
from . import lk

rooms_bp = Blueprint("rooms", __name__)


@rooms_bp.route("/api/me")
@login_required
def me():
    return jsonify({
        "user_id": session["user_id"],
        "display_name": session["display_name"],
        "role": session["role"],
    })


@rooms_bp.route("/api/rooms")
@login_required
def list_rooms():
    rooms = list(db.rooms.find({"active": True}))
    participant_counts = lk.list_rooms_participants()
    for room in rooms:
        room["_id"] = str(room["_id"])
        room["participant_count"] = participant_counts.get(room["_id"], 0)
    return jsonify(rooms)


@rooms_bp.route("/api/token", methods=["POST"])
@login_required
def token():
    data = request.get_json(force=True)
    room_id = data.get("room_id", "").strip()
    if not room_id:
        return jsonify({"error": "room_id required"}), 400
    try:
        jwt = issue_token(
            user_id=session["user_id"],
            display_name=session["display_name"],
            room_id=room_id,
            role=session["role"],
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"token": jwt})


@rooms_bp.route("/api/rooms/<room_id>/mode", methods=["POST"])
@mod_required
def toggle_mode(room_id):
    data = request.get_json(force=True)
    new_mode = data.get("mode", "")
    if new_mode not in ("discussion", "broadcast"):
        return jsonify({"error": "mode must be 'discussion' or 'broadcast'"}), 400

    room = db.rooms.find_one({"_id": room_id})
    if not room:
        return jsonify({"error": "Room not found"}), 404

    presenter_ids = room.get("presenter_ids", [])

    try:
        participants = lk.list_participants(room_id)
    except Exception as e:
        return jsonify({"error": f"LiveKit unreachable: {e}"}), 502

    def can_publish_in_broadcast(identity):
        return identity in presenter_ids

    def update_one(participant):
        can_pub = True if new_mode == "discussion" else can_publish_in_broadcast(participant.identity)
        lk.update_participant(room_id, participant.identity, can_publish=can_pub)

    pool = Pool(10)
    try:
        pool.map(update_one, participants)
    except Exception as e:
        return jsonify({"error": f"LiveKit update failed: {e}"}), 502

    db.rooms.update_one({"_id": room_id}, {"$set": {"mode": new_mode}})
    _audit(room_id, "mode_change", session["user_id"], {"mode": new_mode})

    return jsonify({"mode": new_mode})


@rooms_bp.route("/api/rooms/<room_id>/mute", methods=["POST"])
@mod_required
def mute_participant(room_id):
    data = request.get_json(force=True)
    target_user_id = data.get("user_id", "").strip()
    muted = bool(data.get("muted", True))
    if not target_user_id:
        return jsonify({"error": "user_id required"}), 400

    try:
        lk.update_participant(room_id, target_user_id, can_publish=not muted)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    _audit(room_id, "participant_muted" if muted else "participant_unmuted",
           session["user_id"], {"target": target_user_id})
    return jsonify({"muted": muted})


@rooms_bp.route("/api/rooms/<room_id>/presenter", methods=["POST"])
@mod_required
def manage_presenter(room_id):
    data = request.get_json(force=True)
    target_user_id = data.get("user_id", "").strip()
    action = data.get("action", "")
    if not target_user_id or action not in ("grant", "revoke"):
        return jsonify({"error": "user_id and action (grant|revoke) required"}), 400

    if action == "grant":
        db.rooms.update_one({"_id": room_id}, {"$addToSet": {"presenter_ids": target_user_id}})
        can_publish = True
    else:
        db.rooms.update_one({"_id": room_id}, {"$pull": {"presenter_ids": target_user_id}})
        room = db.rooms.find_one({"_id": room_id})
        can_publish = room["mode"] == "discussion"

    try:
        lk.update_participant(room_id, target_user_id, can_publish=can_publish)
    except Exception:
        pass  # best-effort live update; DB is source of truth for next token

    _audit(room_id, f"presenter_{action}", session["user_id"], {"target": target_user_id})
    return jsonify({"action": action, "user_id": target_user_id})


def _audit(room_id, event, actor, meta=None):
    db.audit_log.insert_one({
        "event": event,
        "room_id": room_id,
        "actor": actor,
        "timestamp": datetime.now(timezone.utc),
        "meta": meta or {},
    })
