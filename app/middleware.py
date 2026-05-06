from functools import wraps
from flask import session, redirect, jsonify, request


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect("/auth/login")
        return f(*args, **kwargs)
    return decorated


def mod_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        
        # Room ID might be in kwargs or in JSON body
        room_id = kwargs.get("room_id")
        if not room_id and request.is_json:
            try:
                room_id = request.get_json(silent=True).get("room_id")
            except Exception: pass
            
        role = session.get("role")
        
        if role in ("moderator", "admin"):
            return f(*args, **kwargs)
            
        # Check for per-room operator
        if role == "operator" and room_id:
            # A: Access via room-specific passphrase (stored in session)
            if session.get("operator_room_id") == room_id:
                return f(*args, **kwargs)

            # B: Access via explicit user_id assignment (legacy support)
            from .models import db
            room = db.rooms.find_one({"_id": room_id, "operator_ids": session["user_id"]})
            if room:
                return f(*args, **kwargs)
                
        return jsonify({"error": "Forbidden"}), 403
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect("/auth/login")
        if session.get("role") != "admin":
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated
