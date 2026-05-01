import os
import hmac
import uuid
from flask import Blueprint, request, session, redirect, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

auth_bp = Blueprint("auth", __name__)
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")

PASSPHRASE = os.environ.get("ACCESS_PASSPHRASE")
if not PASSPHRASE or not PASSPHRASE.strip():
    raise RuntimeError("ACCESS_PASSPHRASE must be set to a non-empty value. Refusing to start.")

PRIVILEGED_USERS = {}

# Load privileged users from env: PRIVILEGED_USERS=username1:role1,username2:role2
_raw = os.environ.get("PRIVILEGED_USERS", "")
for entry in _raw.split(","):
    entry = entry.strip()
    if ":" in entry:
        name, role = entry.split(":", 1)
        if role in ("admin", "moderator"):
            PRIVILEGED_USERS[name.strip()] = role.strip()


def resolve_role(display_name: str) -> str:
    return PRIVILEGED_USERS.get(display_name, "member")


@auth_bp.route("/auth/login", methods=["GET", "POST"])
@limiter.limit("5/minute")
def login():
    if request.method == "POST":
        submitted = request.form.get("passphrase", "")
        if hmac.compare_digest(submitted, PASSPHRASE):
            display_name = request.form.get("display_name", "Anonymous").strip() or "Anonymous"
            session.clear()
            session["user_id"] = str(uuid.uuid4())
            session["display_name"] = display_name
            session["role"] = resolve_role(display_name)
            return redirect("/")
        return render_template("login.html", error="Invalid passphrase.")
    return render_template("login.html")


@auth_bp.route("/auth/logout")
def logout():
    session.clear()
    return redirect("/auth/login")
