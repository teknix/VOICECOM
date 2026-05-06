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

    # Zulip allows Basic Auth (email:password) for API calls
    url = f"{ZULIP_URL.rstrip('/')}/api/v1/users/me"
    try:
        resp = requests.get(
            url,
            auth=HTTPBasicAuth(email, password),
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            return True, {
                "user_id": str(data.get("user_id")),
                "full_name": data.get("full_name"),
                "avatar_url": data.get("avatar_url"),
                "is_admin": data.get("is_admin", False),
                "is_owner": data.get("is_owner", False),
                "is_moderator": data.get("is_moderator", False),
            }
        return False, None
    except Exception:
        return False, None
