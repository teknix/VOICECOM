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
        if session.get("role") not in ("moderator", "admin"):
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
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
