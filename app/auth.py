import os
import hmac
import uuid
import bcrypt
from flask import Blueprint, request, session, redirect, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .config import SUPER_ADMIN_USERNAME, SUPER_ADMIN_HASH, ENABLE_ZULIP_AUTH
from .zulip import verify_zulip_credentials
from .models import db

auth_bp = Blueprint("auth", __name__)
limiter = Limiter(key_func=get_remote_address, storage_uri=os.environ.get("REDIS_URL", "memory://"))

# Role priorities for hierarchical comparisons
ROLE_PRIORITY = {
    "admin": 100,
    "moderator": 50,
    "operator": 25,
    "member": 0
}


def authenticate(username, password):
    """
    Authenticate user via Super Admin bypass, Zulip Proxy, or Internal DB.
    Returns (success, user_info)
    """
    # 1. Check Super Admin
    if username == SUPER_ADMIN_USERNAME and SUPER_ADMIN_HASH:
        if bcrypt.checkpw(password.encode('utf-8'), SUPER_ADMIN_HASH.encode('utf-8')):
            return True, {
                "user_id": "super-admin",
                "display_name": "System Administrator",
                "role": "admin",
                "avatar_url": None
            }

    # 2. Check Zulip Proxy (Optional)
    if ENABLE_ZULIP_AUTH:
        success, profile = verify_zulip_credentials(username, password)
        if success:
            role = "member"
            if profile.get("is_admin") or profile.get("is_owner"):
                role = "admin"
            elif profile.get("is_moderator"):
                role = "moderator"

            # Check if an internal DB record exists for this user and take the higher role.
            # Match on full login string or the local part of an email address.
            candidates = [username]
            if "@" in username:
                candidates.append(username.split("@")[0])
            for candidate in candidates:
                internal = db.users.find_one({"username": candidate})
                if internal:
                    internal_role = internal.get("role", "member")
                    if ROLE_PRIORITY.get(internal_role, 0) > ROLE_PRIORITY.get(role, 0):
                        role = internal_role
                    break

            return True, {
                "user_id": profile["user_id"],
                "display_name": profile["full_name"],
                "role": role,
                "avatar_url": profile["avatar_url"]
            }

    # 3. Check Internal DB
    user = db.users.find_one({"username": username})
    if user and bcrypt.checkpw(password.encode('utf-8'), user["password_hash"].encode('utf-8')):
        return True, {
            "user_id": str(user["_id"]),
            "display_name": user["display_name"],
            "role": user.get("role", "member"),
            "avatar_url": user.get("avatar_url")
        }

    return False, None


@auth_bp.route("/auth/login", methods=["GET", "POST"])
@limiter.limit("5/minute")
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        sector = request.form.get("sector", "Sector 01")

        success, user_info = authenticate(username, password)
        if success:
            session.clear()
            session["user_id"] = user_info["user_id"]
            session["display_name"] = user_info["display_name"]
            session["role"] = user_info["role"]
            session["avatar_url"] = user_info["avatar_url"]
            session["sector"] = sector
            return redirect("/")
            
        return render_template("login.html", error="Invalid username or password.")
    return render_template("login.html")


@auth_bp.route("/auth/logout")
def logout():
    session.clear()
    return redirect("/auth/login")
