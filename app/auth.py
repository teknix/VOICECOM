import logging
import os
import hmac
import uuid
import bcrypt
from flask import Blueprint, request, session, redirect, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .config import (SUPER_ADMIN_USERNAME, SUPER_ADMIN_HASH, ENABLE_ZULIP_AUTH,
                     ENABLE_MATRIX_AUTH)
from .zulip import verify_zulip_credentials
from .matrix import verify_matrix_credentials
from .models import db

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)
limiter = Limiter(key_func=get_remote_address, storage_uri=os.environ.get("REDIS_URL", "memory://"))

# Role priorities for hierarchical comparisons
ROLE_PRIORITY = {
    "admin": 100,
    "moderator": 50,
    "operator": 25,
    "member": 0
}


def can_join(role, room):
    """Per-room role gate. `min_role` (absent = open to everyone) is the lowest
    global role allowed in; unknown values fail closed at admin-only rather than
    silently opening the room. `locked` stays a separate admin-only override."""
    min_role = room.get("min_role")
    if not min_role:
        return True
    return ROLE_PRIORITY.get(role, 0) >= ROLE_PRIORITY.get(min_role, 100)


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
    fallback_error = None
    if ENABLE_ZULIP_AUTH:
        success, profile = verify_zulip_credentials(username, password)
        if not success and isinstance(profile, dict) and profile.get("hint") == "email_required":
            # Zulip rejects non-email usernames, but an internal-DB account may
            # legitimately have one — so keep going and only show this hint if
            # nothing else matches. Returning here locked those users out entirely.
            fallback_error = {"error": "Use your full email address (e.g. you@example.com) to sign in with The Server."}
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

            # Logged because "why is this person only a member?" is otherwise
            # unanswerable after the fact — the role never lands in the DB.
            logger.warning("zulip login: user_id=%s zulip_role=%s -> app role %r",
                           profile["user_id"], profile.get("zulip_role"), role)

            return True, {
                "user_id": profile["user_id"],
                "display_name": profile["full_name"],
                "role": role,
                "avatar_url": profile["avatar_url"]
            }

    # 2b. Check Matrix (Optional) — '@user:homeserver' + password, verified by that homeserver.
    # The colon guard keeps plain local usernames off the network path entirely.
    if ENABLE_MATRIX_AUTH and ":" in username:
        success, profile = verify_matrix_credentials(username, password)
        if not success and isinstance(profile, dict):
            # Same rule as the Zulip path above: record the hint but keep going, so an
            # internal-DB account with this literal username isn't locked out. The hint
            # is only surfaced if nothing else matches.
            if profile.get("hint") == "mxid_required":
                fallback_error = {"error": "Sign in with your full Matrix ID, e.g. @you:turbulent.net"}
            if profile.get("hint") == "homeserver_not_allowed":
                fallback_error = {"error": f"Logins from '{profile.get('server')}' are not enabled here."}
        if success:
            # Matrix's client API exposes no admin flag (that lives behind Synapse's admin
            # API), so everyone arrives as a member and elevation comes from the internal DB.
            # Matched on the FULL MXID only — matching the localpart would let
            # @ingo:evil.example inherit the local 'ingo' account's role.
            role = "member"
            internal = db.users.find_one({"username": profile["user_id"]})
            if internal:
                role = internal.get("role", "member")

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

    return False, fallback_error


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

        error = "Invalid username or password."
        if isinstance(user_info, dict) and user_info.get("error"):
            error = user_info["error"]
        return render_template("login.html", error=error)
    return render_template("login.html")


@auth_bp.route("/auth/logout")
def logout():
    session.clear()
    return redirect("/auth/login")
