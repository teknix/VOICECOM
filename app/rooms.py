from datetime import datetime, timezone
import json
import gevent
from flask import Blueprint, jsonify, request, session
from gevent.pool import Pool
from .middleware import login_required, mod_required
from .models import db
from .tokens import issue_token
from . import lk
from .auth import ROLE_PRIORITY
from .utils import audit_log

rooms_bp = Blueprint("rooms", __name__)


@rooms_bp.route("/api/rooms/<room_id>/chat", methods=["POST"])
@login_required
def send_chat(room_id):
    """Bridge text chat to Zulip."""
    data = request.get_json(force=True)
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "message required"}), 400

    room = db.rooms.find_one({"_id": room_id})
    if not room:
        return jsonify({"error": "Room not found"}), 404

    # Bridge to Zulip (Deferred to v2.0)
    # stream = room.get("zulip_stream", "voicecom")
    # topic = room.get("zulip_topic", room["display_name"])
    # content = f"**{session['display_name']}**: {message}"
    # send_to_zulip(stream, topic, content)

    # Note: Client also publishes to LiveKit data channel for real-time UI update
    return jsonify({"status": "sent"})


@rooms_bp.route("/api/me")
@login_required
def me():
    return jsonify({
        "user_id": session["user_id"],
        "display_name": session["display_name"],
        "role": session["role"],
        "avatar_url": session.get("avatar_url")
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
            sector=session.get("sector", "Sector 01"),
            avatar_url=session.get("avatar_url")
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"token": jwt})


def _set_room_mode(room_id, room, new_mode):
    # 1. Update LiveKit Room Metadata (O(1) Broadcast Signal)
    current_meta = {}
    try:
        try:
            raw_meta = lk.get_room_metadata(room_id)
            current_meta = json.loads(raw_meta) if raw_meta else {}
        except: pass # Best effort for existing meta
        
        current_meta["mode"] = new_mode
        lk.update_room_metadata(room_id, json.dumps(current_meta))
    except Exception as e:
        return {"error": f"LiveKit update failed: {e}"}, 502

    # 2. Update DB (Source of Truth)
    db.rooms.update_one({"_id": room_id}, {"$set": {"mode": new_mode}})

    # 3. Security Enforcement (O(N) Background Mute)
    if new_mode == "broadcast":
        def enforce_mute():
            try:
                participants = lk.list_participants(room_id)
                presenter_ids = set(room.get("presenter_ids", []))
                pool = Pool(10)
                for p in participants:
                    p_meta = json.loads(p.metadata) if p.metadata else {}
                    role = p_meta.get("role", "member")
                    if role == "member" and p.identity not in presenter_ids:
                        pool.spawn(lk.update_participant, room_id, p.identity, can_publish=False)
                pool.join()
            except Exception as e:
                print(f"Background enforcement failed: {e}")
        gevent.spawn(enforce_mute)

    return {"mode": new_mode}, 200


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

    res, status = _set_room_mode(room_id, room, new_mode)
    if status == 200:
        audit_log(room_id, "mode_change", session["user_id"], {"mode": new_mode})
    return jsonify(res), status


@rooms_bp.route("/api/rooms/<room_id>/sync", methods=["POST"])
@mod_required
def sync_room(room_id):
    room = db.rooms.find_one({"_id": room_id})
    if not room:
        return jsonify({"error": "Room not found"}), 404

    mode = room.get("mode", "discussion")
    res, status = _set_room_mode(room_id, room, mode)
    
    if status != 200:
        return jsonify(res), status

    audit_log(room_id, "room_sync", session["user_id"], {"mode": mode})
    return jsonify({"status": "synced", "mode": mode}), 200


@rooms_bp.route("/api/rooms/<room_id>/metadata", methods=["POST"])
@mod_required
def update_room_metadata(room_id):
    data = request.get_json(force=True)
    metadata = data.get("metadata", "")
    try:
        lk.update_room_metadata(room_id, metadata)
        return jsonify({"status": "updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@rooms_bp.route("/api/rooms/<room_id>/mute", methods=["POST"])
@mod_required
def mute_participant(room_id):
    data = request.get_json(force=True)
    target_user_id = data.get("user_id", "").strip()
    muted = bool(data.get("muted", True))
    if not target_user_id:
        return jsonify({"error": "user_id required"}), 400

    # Hierarchical Check: Fetch target role from LiveKit metadata
    try:
        participants = lk.list_participants(room_id)
        target = next((p for p in participants if p.identity == target_user_id), None)
        if target and target.metadata:
            target_meta = json.loads(target.metadata)
            target_role = target_meta.get("role", "member")
            
            current_role = session.get("role", "member")
            if ROLE_PRIORITY.get(current_role, 0) < ROLE_PRIORITY.get(target_role, 0):
                return jsonify({"error": f"Cannot mute higher role: {target_role}"}), 403
    except Exception as e:
        return jsonify({"error": f"Role verification failed: {e}"}), 502

    try:
        lk.update_participant(room_id, target_user_id, can_publish=not muted)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    audit_log(room_id, "participant_muted" if muted else "participant_unmuted",
           session["user_id"], {"target": target_user_id})
    return jsonify({"muted": muted})


@rooms_bp.route("/api/rooms/<room_id>/operator", methods=["POST"])
@mod_required
def manage_operator(room_id):
    """Admin/Mod only: Assign per-room operator status."""
    if session.get("role") not in ("admin", "moderator"):
        return jsonify({"error": "Global Moderator or Admin rights required"}), 403
        
    data = request.get_json(force=True)
    target_user_id = data.get("user_id", "").strip()
    action = data.get("action", "")
    if not target_user_id or action not in ("grant", "revoke"):
        return jsonify({"error": "user_id and action (grant|revoke) required"}), 400

    if action == "grant":
        db.rooms.update_one({"_id": room_id}, {"$addToSet": {"operator_ids": target_user_id}})
    else:
        db.rooms.update_one({"_id": room_id}, {"$pull": {"operator_ids": target_user_id}})

    audit_log(room_id, f"operator_{action}", session["user_id"], {"target": target_user_id})
    return jsonify({"action": action, "user_id": target_user_id})


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

    audit_log(room_id, f"presenter_{action}", session["user_id"], {"target": target_user_id})
    return jsonify({"action": action, "user_id": target_user_id})


def audit_log(room_id, event, actor, meta=None):
    db.audit_log.insert_one({
        "event": event,
        "room_id": room_id,
        "actor": actor,
        "timestamp": datetime.now(timezone.utc),
        "meta": meta or {},
    })
