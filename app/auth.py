import os
import hmac
import uuid
import bcrypt
from flask import Blueprint, request, session, redirect, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .config import SUPER_ADMIN_EMAIL, SUPER_ADMIN_HASH
from .zulip import verify_zulip_credentials

auth_bp = Blueprint("auth", __name__)
limiter = Limiter(key_func=get_remote_address, storage_uri=os.environ.get("REDIS_URL", "memory://"))

# Legacy passphrases (kept for backward compatibility if needed, but primary is Zulip)
PASSPHRASE = os.environ.get("ACCESS_PASSPHRASE")

# Role priorities for hierarchical comparisons
ROLE_PRIORITY = {
    "admin": 100,
    "moderator": 50,
    "operator": 25,
    "member": 0
}


def authenticate(email, password):
    """
    Authenticate user via Super Admin bypass or Zulip Proxy.
    Returns (success, user_info)
    """
    # 1. Check Super Admin
    if email == SUPER_ADMIN_EMAIL and SUPER_ADMIN_HASH:
        if bcrypt.checkpw(password.encode('utf-8'), SUPER_ADMIN_HASH.encode('utf-8')):
            return True, {
                "user_id": "super-admin",
                "display_name": "System Administrator",
                "role": "admin",
                "avatar_url": None
            }

    # 2. Check Zulip Proxy
    success, profile = verify_zulip_credentials(email, password)
    if success:
        role = "member"
        if profile.get("is_admin") or profile.get("is_owner"):
            role = "admin"
        elif profile.get("is_moderator"):
            role = "moderator"
            
        return True, {
            "user_id": profile["user_id"],
            "display_name": profile["full_name"],
            "role": role,
            "avatar_url": profile["avatar_url"]
        }

    return False, None


@auth_bp.route("/auth/login", methods=["GET", "POST"])
@limiter.limit("5/minute")
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        sector = request.form.get("sector", "Sector 01")
        
        success, user_info = authenticate(email, password)
        if success:
            session.clear()
            session["user_id"] = user_info["user_id"]
            session["display_name"] = user_info["display_name"]
            session["role"] = user_info["role"]
            session["avatar_url"] = user_info["avatar_url"]
            session["sector"] = sector
            return redirect("/")
            
        return render_template("login.html", error="Invalid email or password.")
    return render_template("login.html")


@auth_bp.route("/auth/logout")
def logout():
    session.clear()
    return redirect("/auth/login")
