import os
import hmac
import uuid
from flask import Blueprint, request, session, redirect, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

auth_bp = Blueprint("auth", __name__)
limiter = Limiter(key_func=get_remote_address, storage_uri=os.environ.get("REDIS_URL", "memory://"))

PASSPHRASE = os.environ.get("ACCESS_PASSPHRASE")
MOD_PASSPHRASE = os.environ.get("MOD_PASSPHRASE")
ADMIN_PASSPHRASE = os.environ.get("ADMIN_PASSPHRASE")
OPERATOR_PASSPHRASE = os.environ.get("OPERATOR_PASSPHRASE")

if not PASSPHRASE or not PASSPHRASE.strip():
    raise RuntimeError("ACCESS_PASSPHRASE must be set. Refusing to start.")

# Role priorities for hierarchical comparisons
ROLE_PRIORITY = {
    "admin": 100,
    "moderator": 50,
    "operator": 25,
    "member": 0
}


def resolve_role(passphrase: str) -> str:
    """Return the highest role matching the provided passphrase."""
    if ADMIN_PASSPHRASE and hmac.compare_digest(passphrase, ADMIN_PASSPHRASE):
        return "admin"
    if MOD_PASSPHRASE and hmac.compare_digest(passphrase, MOD_PASSPHRASE):
        return "moderator"
    if OPERATOR_PASSPHRASE and hmac.compare_digest(passphrase, OPERATOR_PASSPHRASE):
        return "operator"
    if PASSPHRASE and hmac.compare_digest(passphrase, PASSPHRASE):
        return "member"
    return ""


@auth_bp.route("/auth/login", methods=["GET", "POST"])
@limiter.limit("5/minute")
def login():
    if request.method == "POST":
        submitted = request.form.get("passphrase", "")
        display_name = request.form.get("display_name", "Anonymous").strip() or "Anonymous"
        sector = request.form.get("sector", "Sector 01")
        
        role = resolve_role(submitted)
        if role:
            session.clear()
            session["user_id"] = str(uuid.uuid4())
            session["display_name"] = display_name
            session["role"] = role
            session["sector"] = sector
            return redirect("/")
            
        return render_template("login.html", error="Invalid passphrase.")
    return render_template("login.html")


@auth_bp.route("/auth/logout")
def logout():
    session.clear()
    return redirect("/auth/login")
