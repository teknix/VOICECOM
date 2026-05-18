import os
import requests
from requests.auth import HTTPBasicAuth

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
            data = resp.json()
            return True, {
                "user_id": str(data.get("user_id", user_id)),
                "full_name": data.get("full_name", email),
                "avatar_url": data.get("avatar_url"),
                "is_admin": data.get("is_admin", False),
                "is_owner": data.get("is_owner", False),
                "is_moderator": data.get("is_moderator", False),
            }
    except Exception:
        pass

    # Authenticated but profile fetch failed — return minimal info
    return True, {
        "user_id": str(user_id),
        "full_name": email,
        "avatar_url": None,
        "is_admin": False,
        "is_owner": False,
        "is_moderator": False,
    }
