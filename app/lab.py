"""Owner's mobile test lab at /teknix: does call audio survive app switching and a
locked screen, with and without Picture-in-Picture, wake lock and Media Session?

Only user ids listed in LAB_USER_IDS (env, comma-separated) can open it; everyone
else gets a 404, so the page doesn't advertise itself. Empty list = nobody (fails
closed). The lab uses its own LiveKit room (LAB_ROOM), outside the rooms collection,
so it never shows in the room list and needs no admin setup.
"""
import json
import os
import secrets
from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, render_template, request, session
from livekit import api

from .config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET
from .middleware import login_required
from .models import db
from .tokens import TOKEN_TTL

lab_bp = Blueprint("lab", __name__)

LAB_ROOM = "lab-teknix"
MAX_EVENTS = 5000


def lab_users():
    return {x.strip() for x in os.environ.get("LAB_USER_IDS", "").split(",") if x.strip()}


def require_lab():
    if str(session.get("user_id")) not in lab_users():
        abort(404)


@lab_bp.route("/teknix")
@login_required
def lab_page():
    require_lab()
    return render_template("lab.html", livekit_url=os.environ["LIVEKIT_HOST"],
                           me={"user_id": session["user_id"], "display_name": session.get("display_name")})


@lab_bp.route("/teknix/token", methods=["POST"])
@login_required
def lab_token():
    require_lab()
    device = "".join(c for c in (request.get_json(silent=True) or {}).get("device", "") if c.isalnum() or c in "-_")[:24]
    # One identity per device: LiveKit kicks a second connection with the same identity,
    # and the point of the lab is a phone and a computer in the room together.
    identity = f"{session['user_id']}~{device or 'dev'}~{secrets.token_hex(2)}"
    grants = api.VideoGrants(room_join=True, room=LAB_ROOM, can_publish=True,
                             can_subscribe=True, can_publish_data=True)
    token = (api.AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
             .with_identity(identity)
             .with_name(f"{session.get('display_name', '')} ({device or 'device'})")
             .with_metadata(json.dumps({"role": "member", "lab": True}))
             .with_grants(grants)
             .with_ttl(TOKEN_TTL)
             .to_jwt())
    return jsonify({"token": token, "room": LAB_ROOM, "identity": identity})


@lab_bp.route("/teknix/log", methods=["POST"])
@login_required
def lab_log():
    """Stores a device's event log so test runs can be read back afterwards."""
    require_lab()
    data = request.get_json(silent=True) or {}
    run = str(data.get("run", ""))[:40]
    events = data.get("events")
    if not run or not isinstance(events, list):
        return jsonify({"error": "run and events required"}), 400
    db.lab_logs.update_one(
        {"_id": run},
        {"$set": {"user_id": session["user_id"],
                  "device": str(data.get("device", ""))[:24],
                  "ua": request.headers.get("User-Agent", "")[:300],
                  "settings": data.get("settings") if isinstance(data.get("settings"), dict) else {},
                  "events": [str(e)[:300] for e in events[-MAX_EVENTS:]],
                  "updated": datetime.now(timezone.utc)}},
        upsert=True)
    return jsonify({"status": "saved", "events": min(len(events), MAX_EVENTS)})
