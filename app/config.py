import os

LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
LIVEKIT_HOST = os.environ.get("LIVEKIT_HOST", "ws://localhost:7880")
LIVEKIT_INTERNAL_URL = os.environ.get("LIVEKIT_INTERNAL_URL", "http://localhost:7880")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/voicesystem")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "/recordings")

# Zulip Integration
ZULIP_URL = os.environ.get("ZULIP_URL", "")
ZULIP_EMAIL = os.environ.get("ZULIP_EMAIL", "")
ZULIP_API_KEY = os.environ.get("ZULIP_API_KEY", "")
ENABLE_ZULIP_AUTH = os.environ.get("ENABLE_ZULIP_AUTH", "false").lower() == "true"

# Matrix Integration (federated login: '@user:homeserver' + password)
ENABLE_MATRIX_AUTH = os.environ.get("ENABLE_MATRIX_AUTH", "false").lower() == "true"
# Comma list of homeserver names allowed to log in; '*' allows any. Empty = federated
# login disabled. Without this the app accepts anyone holding any Matrix account anywhere.
MATRIX_ALLOWED_HOMESERVERS = {
    h.strip().lower()
    for h in os.environ.get("MATRIX_ALLOWED_HOMESERVERS", "").split(",")
    if h.strip()
}

# Branding / UI (per-deployment; defaults keep the original behaviour)
APP_NAME = os.environ.get("APP_NAME", "VoiceCom")
ENABLE_SECTORS = os.environ.get("ENABLE_SECTORS", "true").lower() == "true"

# Super Admin (Recovery)
SUPER_ADMIN_USERNAME = os.environ.get("SUPER_ADMIN_USERNAME", "admin")
SUPER_ADMIN_HASH = os.environ.get("SUPER_ADMIN_HASH", "") # bcrypt hash
