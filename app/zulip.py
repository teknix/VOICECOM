import logging
import os
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

ZULIP_URL = os.environ.get("ZULIP_URL", "")
ZULIP_EMAIL = os.environ.get("ZULIP_EMAIL", "")
ZULIP_API_KEY = os.environ.get("ZULIP_API_KEY", "")


def send_to_zulip(stream: str, topic: str, content: str):
    """Send a message to a Zulip stream/topic."""
    if not all([ZULIP_URL, ZULIP_EMAIL, ZULIP_API_KEY]):
        return False
        
    url = f"{ZULIP_URL.rstrip('/')}/api/v1/messages"
    data = {
        "type": "stream",
        "to": stream,
        "topic": topic,
        "content": content
    }
    
    try:
        resp = requests.post(
            url,
            data=data,
            auth=HTTPBasicAuth(ZULIP_EMAIL, ZULIP_API_KEY),
            timeout=5
        )
        return resp.status_code == 200
    except Exception:
        return False


ZULIP_ROLE_OWNER = 100
ZULIP_ROLE_ADMIN = 200
ZULIP_ROLE_MODERATOR = 300


def _profile_from_user(data: dict, fallback_user_id, email: str):
    """Map a Zulip user object onto the profile shape the app expects.

    Moderator MUST come from the integer `role` — Zulip's user object has
    is_admin/is_owner/is_guest but NO `is_moderator` field, so reading one only
    ever yielded False and every Zulip moderator arrived here as a plain member.
    The booleans are still honoured for admin/owner (they do exist), and `role`
    is checked too so a server that ever drops them still resolves correctly.
    """
    role = data.get("role")
    return {
        "zulip_role": role,
        "user_id": str(data.get("user_id", fallback_user_id)),
        "full_name": data.get("full_name", email),
        "avatar_url": data.get("avatar_url"),
        "is_admin": bool(data.get("is_admin", False)) or role == ZULIP_ROLE_ADMIN,
        "is_owner": bool(data.get("is_owner", False)) or role == ZULIP_ROLE_OWNER,
        "is_moderator": bool(data.get("is_moderator", False)) or role == ZULIP_ROLE_MODERATOR,
    }


def verify_zulip_credentials(email: str, password: str):
    """
    Verify email/password against Zulip and return profile info.
    Returns (success, profile_dict)
    """
    if not ZULIP_URL:
        return False, None

    base = ZULIP_URL.rstrip('/')

    # Step 1: exchange email+password for an API key via fetch_api_key
    try:
        resp = requests.post(
            f"{base}/api/v1/fetch_api_key",
            data={"username": email, "password": password},
            timeout=8
        )
        if resp.status_code == 400:
            # Zulip rejects non-email usernames — surface this specifically
            body = resp.json()
            if "valid email" in body.get("msg", "").lower():
                return False, {"hint": "email_required"}
            return False, None
        if resp.status_code != 200:
            return False, None
        key_data = resp.json()
        if key_data.get("result") != "success":
            return False, None
        api_key = key_data["api_key"]
        user_id = key_data["user_id"]
    except Exception:
        return False, None

    # Step 2: fetch full profile with the obtained API key
    try:
        resp = requests.get(
            f"{base}/api/v1/users/me",
            auth=HTTPBasicAuth(email, api_key),
            timeout=5
        )
        if resp.status_code == 200:
            return True, _profile_from_user(resp.json(), user_id, email)
        logger.warning("zulip users/me for user_id=%s -> HTTP %s; falling back to no privileges",
                       user_id, resp.status_code)
    except Exception as e:
        logger.warning("zulip users/me for user_id=%s failed: %s; falling back to no privileges",
                       user_id, e)

    # Authenticated but profile fetch failed — the user gets in, but with NO role
    # flags, so an admin/moderator silently lands as a plain member. Logged above
    # because it is otherwise indistinguishable from genuinely being a member.
    return True, {
        "zulip_role": None,
        "user_id": str(user_id),
        "full_name": email,
        "avatar_url": None,
        "is_admin": False,
        "is_owner": False,
        "is_moderator": False,
    }
